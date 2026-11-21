"""Wspólne kontrakty między sektorami A/B/C.

ZMIANY TYLKO PRZEZ PR DO main Z AKCEPTACJĄ CAŁEGO ZESPOŁU.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    """Wynik sektora A (ingest): tekst dokumentu."""

    path: Path
    text: str
    pages: list[str]
    ocr_used: bool = False


@dataclass
class Classification:
    """Wynik sektora A (classify). doc_type=None oznacza dokument nieznany."""

    doc_type: str | None
    confidence: float
    method: str  # "keywords" | "llm" | ...
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class FieldResult:
    """Pochodzenie jednej wartości (transparentność) — NIE trafia do wynikowego JSON."""

    path: str  # np. "Odwolujacy[0].nip"
    value: Any
    method: str  # "regex" | "llm" | "derived" | "default"
    source_snippet: str | None = None
    page: int | None = None


@dataclass
class ExtractionResult:
    """Wynik sektora B. data ma DOKŁADNIE kształt szablonu z config/schemas."""

    doc_type: str
    data: dict
    trace: list[FieldResult] = field(default_factory=list)
