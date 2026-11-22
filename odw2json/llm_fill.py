"""Wariant hybrydowy (pomiar E6): reguły + LLM tylko dla pól, w których reguły dały ``null``.

Włączany flagą ``config/app.yaml: llm_enabled`` (domyślnie ``false``; rozwiązanie oddawane jest bez LLM,
docs/decyzje/E6-bez-llm.md). Przebieg dla jednego dokumentu:

1. reguły (``extract.extract``) dają wynik; zbieramy ścieżki liści ``null`` (bez pól wyliczanych),
2. pole jest pytane tylko, gdy opisuje je prompt typu (``config/prompts/<typ>.md``, nagłówek YAML ``pola``)
   i w tekście jest któraś z jego fraz ``szukaj`` (pusta lista = pole z nagłówka dokumentu),
3. **wycinek**: początek dokumentu + okna wokół trafień fraz, z limitem znaków (nie cały dokument),
4. jedno zapytanie do LLM na dokument; odpowiedź przechodzi normalizatory i walidatory pola z YAML
   oraz kontrolę „jest w tekście” (cyfry numerów i rdzenie słów muszą wystąpić w wycinku),
5. błąd LLM (sieć, limit zapytań, zły JSON) nie psuje dokumentu - zostaje wynik reguł.

Pola uzupełnione przez model mają w trace ``method="llm"``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import yaml

from odw2json.config_loader import ROOT_DIR, DocTypeConfig, load_llm_config
from odw2json.contracts import Document, ExtractionResult, FieldResult
from odw2json.extract import engine

log = logging.getLogger("odw2json")

COMMON_PROMPT = "prompts/wspolne.md"
DEFAULTS = {
    "head_chars": 800,  # początek dokumentu zawsze w wycinku (nagłówek, strony postępowania)
    "window_before": 200,
    "window_after": 400,
    "max_hits_per_field": 3,
    "max_chars": 6000,  # limit długości wycinka
}
_IDX = re.compile(r"\[\d+\]")
_GAP = "\n[…]\n"

# Liczniki wszystkich wypełniaczy w procesie (scripts/bench_hybryda.py zeruje je przed przebiegiem).
STATS: Counter = Counter()


@dataclass
class FieldHint:
    opis: str
    szukaj: list[str] = field(default_factory=list)
    wartosci: list | None = None  # zamknięta lista dozwolonych wartości (np. typ mocodawcy)


@dataclass
class PromptSpec:
    system: str
    fields: dict[str, FieldHint]


def _split_front_matter(raw: str) -> tuple[dict, str]:
    if raw.startswith("---"):
        _, head, body = raw.split("---", 2)
        return yaml.safe_load(head) or {}, body.strip()
    return {}, raw.strip()


_PROMPTS: dict[tuple[str, str], PromptSpec] = {}


def load_prompt(cfg: DocTypeConfig) -> PromptSpec:
    """Prompt typu: wspólne zasady (``prompts/wspolne.md``) + część typu; ``pola`` z nagłówka YAML."""
    key = (str(cfg.config_dir), cfg.id)
    if key in _PROMPTS:
        return _PROMPTS[key]
    raw = cfg.prompt_text() or ""
    meta, body = _split_front_matter(raw)
    common = cfg.config_dir / COMMON_PROMPT
    system = (common.read_text(encoding="utf-8").strip() + "\n\n" if common.exists() else "") + body
    fields = {
        path: FieldHint(
            opis=str(v.get("opis", "")), szukaj=list(v.get("szukaj") or []), wartosci=v.get("wartosci")
        )
        for path, v in (meta.get("pola") or {}).items()
    }
    _PROMPTS[key] = spec = PromptSpec(system=system, fields=fields)
    return spec


def dsl_path(concrete: str) -> str:
    """``Odwolujacy[0].nip`` -> ``Odwolujacy[].nip`` (klucz pola w YAML)."""
    return _IDX.sub(engine.LIST_MARK, concrete)


def _leaves(v: Any, path: str = "") -> dict[str, Any]:
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        for k, x in v.items():
            out.update(_leaves(x, f"{path}.{k}" if path else k))
        return out
    if isinstance(v, list):
        out = {}
        for i, x in enumerate(v):
            out.update(_leaves(x, f"{path}[{i}]"))
        return out
    return {path: v}


def null_paths(data: dict, cfg: DocTypeConfig) -> list[str]:
    """Ścieżki liści ``null`` (konkretne indeksy), z pominięciem pól wyliczanych (``derived``)."""
    out = []
    for path, value in _leaves(data).items():
        spec = cfg.fields.get(dsl_path(path))
        if value is None and spec is not None and spec.derived is None:
            out.append(path)
    return out


def _set(data: dict, concrete: str, value: Any) -> None:
    cur: Any = data
    parts = re.findall(r"[^.\[\]]+|\[\d+\]", concrete)
    for part, nxt in zip(parts, parts[1:] + [None], strict=True):
        key: Any = int(part[1:-1]) if part.startswith("[") else part
        if nxt is None:
            cur[key] = value
        else:
            cur = cur[key]


def _union_len(spans: list[tuple[int, int]]) -> int:
    total, end = 0, -1
    for a, b in sorted(spans):
        if b <= end:
            continue
        total += b - max(a, end)
        end = b
    return total


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _ws(s: str) -> str:
    return " ".join(engine.fold(s).split())


def _words_present(words: list[str], folded_src: str, prefix: int) -> bool:
    """Każde słowo jako początek słowa w tekście; ``prefix`` znaków (odmiana: Kowalski -> Kowalskiego)."""
    return all(
        re.search(r"(?<![a-z0-9])" + re.escape(w[: max(2, min(prefix, len(w) - 1))]), folded_src)
        for w in words
    )


def _candidates(source: str, pattern: str, normalizer: str) -> set:
    """Wartości z tekstu po tej samej normalizacji co pole (np. wszystkie daty wycinka w ISO)."""
    out = set()
    for m in re.finditer(pattern, source, re.IGNORECASE):
        v = engine.NORMALIZERS[normalizer](m.group())
        if v is not None:
            out.add(v)
    return out


def grounded(value: Any, source: str, spec: Any = None, raw: Any = None, allowed: list | None = None) -> bool:
    """Czy wartość „jest w tekście” wycinka (ochrona przed zmyśleniem):

    - zamknięta lista wartości (``allowed``): tylko przynależność do listy,
    - data / kwota: równa którejś dacie / kwocie z wycinka po tej samej normalizacji,
    - e-mail: dokładnie w tekście; numery (same cyfry, IBAN): wszystkie cyfry jednym ciągiem,
    - imię i nazwisko: każde słowo jako początek słowa w tekście (prefiks 3 znaków - odmiana),
    - krótkie identyfikatory (≤ 3 słowa): dokładnie w tekście (wartość albo surowa odpowiedź) albo cyfry
      jednym ciągiem i słowa w tekście; numer TED: każdy ciąg cyfr (zapis 2025/S 123-641651),
    - nazwy i dłuższe teksty: słowa (prefiks 4) i ciągi cyfr (≥ 3) w tekście,
    - liczby całkowite: krótkie (0/1, id 1-12) zawsze, dłuższe - w strumieniu cyfr.
    """
    if allowed is not None:
        return value in allowed
    typ = getattr(spec, "type", None) or "str"
    chain = getattr(spec, "normalize", None)
    chain = list(chain if chain is not None else engine.TYPES.get(typ, engine.TYPES["str"]).normalize)
    if isinstance(value, bool):
        return True
    src_digits = _digits(source)
    if typ == "date":
        return value in _candidates(source, engine.DATE_PATTERN, "date")
    if typ == "amount":
        return value in _candidates(source, engine.AMOUNT_PATTERN, "amount")
    if isinstance(value, int):
        return len(str(abs(value))) < 3 or str(abs(value)) in src_digits
    folded_src = engine.fold(source)
    ws_src = " ".join(folded_src.split())
    texts = [str(value)] + ([raw] if isinstance(raw, str) else [])
    if typ == "email":
        return any(_ws(t) in ws_src for t in texts)
    folded_val = engine.fold(str(value))
    runs = re.findall(r"\d+", folded_val)
    words = [w for w in re.findall(r"[a-z]+", folded_val) if len(w) >= 3]
    if "ted" in chain:  # 641651-2025 zapisane w tekście jako 2025/S 123-641651
        return bool(runs) and all(r in src_digits for r in runs)
    if typ in ("digits", "iban") or (runs and not re.search(r"[a-z]", folded_val)):
        return bool(runs) and _digits(folded_val) in src_digits
    if typ == "name":
        return bool(words) and _words_present(words, folded_src, 3)
    if typ != "company" and len(folded_val.split()) <= 3:
        if any(_ws(t) in ws_src for t in texts):
            return True
        return bool(runs) and _digits(folded_val) in src_digits and _words_present(words, folded_src, 4)
    if any(r not in src_digits for r in runs if len(r) >= 3):
        return False
    return bool(words) and _words_present(words, folded_src, 4)


def _prepare(raw: Any, spec: Any, allowed: list | None = None) -> Any:
    """Wartość z LLM -> wartość pola (normalizatory i walidatory z YAML); ``None`` = odrzut."""
    if raw is None or isinstance(raw, (dict, list)):
        return None
    if isinstance(raw, bool):
        raw = int(raw)
    if spec.type == "int" and isinstance(raw, float):
        if not raw.is_integer():
            return None
        raw = int(raw)  # 1.0 -> 1 (n_int na str(1.0) dałby 10)
    if isinstance(raw, (int, float)) and spec.type != "int":
        raw = f"{raw:.2f}" if spec.type == "amount" else str(raw)
    if isinstance(raw, str) and not raw.strip():
        return None
    if allowed is not None:
        return raw if raw in allowed else None
    chain = spec.normalize if spec.normalize is not None else list(engine.TYPES[spec.type].normalize)
    value = engine._normalize(raw, chain)
    if value is None or not engine._valid(value, spec.validate_):
        return None
    return value


def _snippet(source: str, value: Any) -> str | None:
    """Linia wycinka z wartością (trace, podświetlenie w GUI); ``None``, gdy nie da się wskazać."""
    probe = str(value)
    i = source.find(probe)
    if i < 0:
        return None
    ls = source.rfind("\n", 0, i) + 1
    le = source.find("\n", i)
    return source[ls : le if le >= 0 else len(source)].strip()[: engine.SNIPPET_MAX] or None


class LLMFiller:
    """Uzupełnia pola ``null`` wyniku reguł odpowiedzią LLM (``client.complete_json``)."""

    def __init__(self, client: Any, settings: dict | None = None):
        self.client = client
        self.s = {**DEFAULTS, **(settings or {})}
        self.stats: Counter = Counter()
        self.on_fill = None  # opcjonalnie fn(doc, path, value) po każdym uzupełnieniu (pomiar)

    def _count(self, key: str, n: int = 1) -> None:
        self.stats[key] += n
        STATS[key] += n

    def build_slice(self, text: str, hints: dict[str, list[str]]) -> tuple[str, set[str]]:
        """Wycinek tekstu i zbiór pól, dla których coś znaleziono (pola z pustym ``szukaj`` zawsze)."""
        folded = engine.fold(text)
        n = len(text)
        head = (0, min(n, self.s["head_chars"]))
        found: set[str] = set()
        per_field: dict[str, list[tuple[int, int]]] = {}
        for path, phrases in hints.items():
            if not phrases:
                found.add(path)
                continue
            spans: list[tuple[int, int]] = []
            for p in phrases:
                for m in engine.phrase_pattern(p).finditer(folded):
                    spans.append(
                        (
                            max(0, m.start() - self.s["window_before"]),
                            min(n, m.end() + self.s["window_after"]),
                        )
                    )
            spans = sorted(set(spans))[: self.s["max_hits_per_field"]]
            if spans:
                per_field[path] = spans
        # kolejność dokładania okien: nagłówek, pierwsze trafienia wszystkich pól, potem kolejne;
        # pole jest pytane tylko, gdy choć jedno jego okno zmieściło się w limicie znaków
        chosen = [head]
        for rank in range(self.s["max_hits_per_field"]):
            for path, spans in per_field.items():
                if rank < len(spans) and _union_len([*chosen, spans[rank]]) <= self.s["max_chars"]:
                    chosen.append(spans[rank])
                    found.add(path)
        dropped = len(set(per_field) - found)
        if dropped:
            self._count("fields_dropped_budget", dropped)
        return _GAP.join(text[a:b].strip() for a, b in _merge(chosen)), found

    def fill(self, doc: Document, res: ExtractionResult, cfg: DocTypeConfig) -> list[str]:
        """Uzupełnia ``res.data`` w miejscu; zwraca ścieżki uzupełnionych pól."""
        prompt = load_prompt(cfg)
        candidates = [p for p in null_paths(res.data, cfg) if dsl_path(p) in prompt.fields]
        if not candidates:
            return []
        text = doc.text or ""
        hints = {p: prompt.fields[dsl_path(p)].szukaj for p in candidates}
        wycinek, found = self.build_slice(text, hints)
        asked = [p for p in candidates if p in found]
        if not asked:
            return []
        known = {k: v for k, v in _leaves(res.data).items() if v is not None}
        user = json.dumps(
            {
                "typ_dokumentu": cfg.id,
                "znane_wartosci": known,
                "pola": [{"pole": p, "opis": prompt.fields[dsl_path(p)].opis} for p in asked],
                "wycinek": wycinek,
            },
            ensure_ascii=False,
            indent=1,
        )
        self._count("docs_asked")
        self._count("fields_asked", len(asked))
        self._count("slice_chars", len(wycinek))
        self._count("doc_chars", len(text))
        usage_before = dict(getattr(self.client, "usage", None) or {})
        t0 = time.perf_counter()
        try:
            answer = self.client.complete_json(prompt.system, user)
        except Exception as e:  # sieć, limit zapytań, zły JSON: zostaje wynik reguł
            self._count("errors")
            log.warning("LLM: %s: %s", doc.path.name, e, extra={"event": "llm_error", "file": doc.path.name})
            return []
        finally:
            self._count("llm_ms", round((time.perf_counter() - t0) * 1000))
            for k, v in (getattr(self.client, "usage", None) or {}).items():
                if isinstance(v, (int, float)) and v != usage_before.get(k, 0):
                    self._count(f"usage_{k}", v - usage_before.get(k, 0))
        if not isinstance(answer, dict):
            self._count("errors")
            return []
        derived_before = _leaves(res.data)
        filled: list[str] = []
        for path in asked:
            raw = answer.get(path)
            if raw is None:
                continue
            spec = cfg.fields[dsl_path(path)]
            allowed = prompt.fields[dsl_path(path)].wartosci
            value = _prepare(raw, spec, allowed)
            if value is None or not grounded(value, wycinek, spec, raw, allowed):
                self._count("rejected")
                continue
            _set(res.data, path, value)
            res.trace.append(
                FieldResult(path=path, value=value, method="llm", source_snippet=_snippet(wycinek, raw))
            )
            filled.append(path)
            if self.on_fill is not None:
                self.on_fill(doc, path, value)
        if filled:
            for fr in engine.apply_derived(res.data, cfg):
                if fr.value != derived_before.get(fr.path):
                    res.trace.append(FieldResult(path=fr.path, value=fr.value, method="derived"))
        self._count("filled", len(filled))
        return filled


def from_app_config(app_cfg: dict) -> LLMFiller | None:
    """Wypełniacz, gdy ``llm_enabled: true``; inaczej ``None`` (domyślnie - rozwiązanie bez LLM)."""
    if not app_cfg.get("llm_enabled"):
        return None
    from odw2json.llm import LLMClient

    settings = load_llm_config().get("hybryda") or {}
    client = LLMClient.from_config()
    if settings.get("cassette_dir") and not os.getenv("LLM_CASSETTE_DIR"):
        client.cassette_dir = ROOT_DIR / settings["cassette_dir"]  # kasety pomiaru poza tests/ (gitignore)
    return LLMFiller(client, settings)
