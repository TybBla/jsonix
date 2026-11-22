"""Klient LLM (OpenAI-kompatybilny). Dostawca/model wyłącznie z konfiguracji (.env / config/llm.yaml).

Tryby (env LLM_MODE albo config/llm.yaml: mode; env wygrywa):
- live   - tylko sieć, bez kaset,
- record - sieć + zapis kasety,
- replay - tylko kaseta; brak kasety -> CassetteMissing,
- auto   - kaseta, jeśli jest; inaczej sieć i zapis (domyślnie; w pytest domyślnie replay).
Kasety: <cassette_dir>/<sha256>.json - powtarzalność wyników, testy bez sieci i oszczędność tokenów.
Katalog kaset: env LLM_CASSETTE_DIR wygrywa nad config/llm.yaml (np. osobny katalog dla pomiarów).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from odw2json.config_loader import ROOT_DIR, load_llm_config

MODES = ("live", "record", "replay", "auto")
# LLM_API_KEY dostawcy bez klucza (np. OVHcloud AI Endpoints, dostęp anonimowy): bez nagłówka Authorization
ANONYMOUS_KEYS = frozenset({"anonim", "anonymous", "none"})
DEFAULT_CASSETTE_DIR = "tests/cassettes"


class CassetteMissing(RuntimeError):
    """Tryb replay: brak kasety dla danego zapytania."""


class CassetteCorrupt(RuntimeError):
    """Kaseta istnieje, ale nie jest poprawnym JSON-em."""


def cassette_key(model: str, system: str, user: str, temperature: float) -> str:
    raw = json.dumps([model, system, user, float(temperature)], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_mode(config_mode: str | None = None) -> str:
    env = os.getenv("LLM_MODE")
    mode = (env or config_mode or "auto").strip().lower()
    if mode not in MODES:
        raise RuntimeError(f"Nieznany tryb LLM '{mode}'; dozwolone: {', '.join(MODES)}")
    if mode == "auto" and not env and os.getenv("PYTEST_CURRENT_TEST"):
        return "replay"
    return mode


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str = "",
        api_key: str | None = None,
        temperature: float = 0,
        max_tokens: int = 2000,
        timeout_s: float = 120,
        retries: int = 2,
        mode: str = "auto",
        cassette_dir: str | None = DEFAULT_CASSETTE_DIR,
        json_mode: bool = True,
        client=None,
        min_interval_s: float = 0,
        extra_body: dict | None = None,
    ):
        if mode not in MODES:
            raise RuntimeError(f"Nieznany tryb LLM '{mode}'; dozwolone: {', '.join(MODES)}")
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.mode, self.json_mode = mode, json_mode
        self.cassette_dir = ROOT_DIR / (cassette_dir or DEFAULT_CASSETTE_DIR)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0, "cached_calls": 0}
        self._conn = (base_url, api_key, timeout_s, retries)
        self.client = client
        self.extra_body = dict(extra_body or {})  # parametry dostawcy, np. {"reasoning_effort": "low"}
        self.anonymous = (api_key or "").strip().lower() in ANONYMOUS_KEYS
        self.min_interval_s = float(min_interval_s or 0)  # limit zapytań dostawcy (darmowy Mistral: 1/s)
        self._last_call: float | None = None

    @classmethod
    def from_config(cls) -> LLMClient:
        load_dotenv(ROOT_DIR / ".env")
        c = load_llm_config()
        mode = resolve_mode(c.get("mode"))
        base_url = os.getenv("LLM_BASE_URL") or c.get("base_url")
        model = os.getenv("LLM_MODEL") or c.get("model") or ""
        key = os.getenv("LLM_API_KEY")
        if mode != "replay":
            missing = [
                n
                for n, v in (("LLM_BASE_URL", base_url), ("LLM_MODEL", model), ("LLM_API_KEY", key))
                if not v
            ]
            if missing and mode in ("live", "record"):
                raise RuntimeError(
                    f"Brak konfiguracji LLM dla trybu '{mode}': ustaw {', '.join(missing)} w .env"
                )
        return cls(
            base_url,
            model,
            key,
            float(os.getenv("LLM_TEMPERATURE") or c.get("temperature", 0)),
            c.get("max_tokens", 2000),
            c.get("timeout_s", 120),
            c.get("retries", 2),
            mode=mode,
            cassette_dir=os.getenv("LLM_CASSETTE_DIR") or c.get("cassette_dir", DEFAULT_CASSETTE_DIR),
            json_mode=c.get("json_mode", True),
            min_interval_s=os.getenv("LLM_MIN_INTERVAL_S") or c.get("min_interval_s", 0),
            extra_body=json.loads(os.getenv("LLM_EXTRA_BODY") or "null") or c.get("extra_body") or {},
        )

    def usage_report(self) -> dict:
        return dict(self.usage)

    def _network_client(self):
        if self.client is None:
            base_url, api_key, timeout_s, retries = self._conn
            missing = [n for n, v in (("LLM_BASE_URL", base_url), ("LLM_API_KEY", api_key)) if not v]
            if missing:
                raise RuntimeError(
                    f"Brak konfiguracji LLM dla trybu '{self.mode}': ustaw {', '.join(missing)} w .env"
                )
            from openai import OpenAI

            self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=retries)
        return self.client

    def _throttle(self) -> None:
        if self.min_interval_s and self._last_call is not None:
            wait = self.min_interval_s - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)

    def _cassette_path(self, key: str) -> Path:
        return self.cassette_dir / f"{key}.json"

    def complete_json(self, system: str, user: str) -> dict:
        key = cassette_key(self.model, system, user, self.temperature)
        path = self._cassette_path(key)
        if self.mode in ("replay", "auto") and path.exists():
            self.usage["cached_calls"] += 1
            try:
                return json.loads(path.read_text(encoding="utf-8"))["response"]
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise CassetteCorrupt(
                    f"Uszkodzona kaseta {path}: {e}. Usun ja i nagraj ponownie (LLM_MODE=record)."
                ) from e
        if self.mode == "replay":
            raise CassetteMissing(
                f"Brak kasety {key} w {self.cassette_dir}. Nagraj ją: LLM_MODE=record (wymaga kluczy w .env)."
            )
        kwargs = {}
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        if self.anonymous:
            from openai import Omit

            kwargs["extra_headers"] = {"Authorization": Omit()}
        client = self._network_client()
        self._throttle()
        try:
            resp = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                **kwargs,
            )
        finally:
            self._last_call = time.monotonic()
        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "length":  # modele „reasoning” zjadają max_tokens
            self.usage["truncated"] = self.usage.get("truncated", 0) + 1
            raise RuntimeError(f"Odpowiedź ucięta na max_tokens={self.max_tokens} (bez kasety)")
        out = json.loads(choice.message.content or "{}")
        u = getattr(resp, "usage", None)
        pt = int(getattr(u, "prompt_tokens", 0) or 0)
        ct = int(getattr(u, "completion_tokens", 0) or 0)
        self.usage["prompt_tokens"] += pt
        self.usage["completion_tokens"] += ct
        self.usage["calls"] += 1
        if self.mode in ("record", "auto"):
            self.cassette_dir.mkdir(parents=True, exist_ok=True)
            cassette = {
                "model": self.model,
                "system": system,
                "user": user,
                "temperature": self.temperature,
                "response": out,
                "usage": {"prompt_tokens": pt, "completion_tokens": ct},
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(cassette, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        return out
