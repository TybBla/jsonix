"""Sektor B: ekstrakcja pól wg konfiguracji typu dokumentu.

Wersja bazowa: zwraca szablon z nullami + pola 'derived' (lookupy).
TODO(B): reguły regex, LLM dla pól semantycznych, merge, normalizacja, walidacja.
"""

from __future__ import annotations

from typing import Any

from odw2json.config_loader import DocTypeConfig, load_lookup
from odw2json.contracts import Document, ExtractionResult, FieldResult


def get_path(data: dict, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def set_path(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


def apply_derived(data: dict, cfg: DocTypeConfig) -> list[FieldResult]:
    """Pola wyliczane z innych pól, np. czynnosc_opis = lookup[czynnosc_powod_id]."""
    trace: list[FieldResult] = []
    for path, spec in cfg.fields.items():
        d = (spec or {}).get("derived")
        if not d or "lookup" not in d:
            continue
        key = get_path(data, d["from"])
        value = load_lookup(d["lookup"], cfg.config_dir).get(key) if key is not None else None
        set_path(data, path, value)
        trace.append(FieldResult(path=path, value=value, method="derived"))
    return trace


def extract(doc: Document, cfg: DocTypeConfig) -> ExtractionResult:
    data = cfg.template()
    trace = apply_derived(data, cfg)
    return ExtractionResult(doc_type=cfg.id, data=data, trace=trace)
