"""Klient LLM (OpenAI-kompatybilny). Dostawca/model wyłącznie z konfiguracji (.env / config/llm.yaml).

Cache odpowiedzi na dysku -> powtarzalność wyników i oszczędność tokenów.
"""

from __future__ import annotations

import hashlib
import json
import os

from dotenv import load_dotenv

from odw2json.config_loader import ROOT_DIR, load_llm_config


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float = 0,
        max_tokens: int = 2000,
        timeout_s: float = 120,
        retries: int = 2,
        cache_dir: str | None = None,
    ):
        from openai import OpenAI

        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=retries)
        self.cache = (ROOT_DIR / cache_dir) if cache_dir else None

    @classmethod
    def from_config(cls) -> LLMClient:
        load_dotenv(ROOT_DIR / ".env")
        c = load_llm_config()
        base_url = os.getenv("LLM_BASE_URL") or c.get("base_url")
        model = os.getenv("LLM_MODEL") or c.get("model")
        key = os.getenv("LLM_API_KEY")
        if not (base_url and model and key):
            raise RuntimeError("Brak konfiguracji LLM: ustaw LLM_BASE_URL, LLM_MODEL, LLM_API_KEY w .env")
        return cls(
            base_url,
            model,
            key,
            c.get("temperature", 0),
            c.get("max_tokens", 2000),
            c.get("timeout_s", 120),
            c.get("retries", 2),
            c.get("cache_dir"),
        )

    def complete_json(self, system: str, user: str) -> dict:
        key = hashlib.sha256(f"{self.model}\n{system}\n{user}".encode()).hexdigest()
        if self.cache and (hit := self.cache / f"{key}.json").exists():
            return json.loads(hit.read_text(encoding="utf-8"))
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        out = json.loads(resp.choices[0].message.content or "{}")
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
            (self.cache / f"{key}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out
