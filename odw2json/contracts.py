"""Wspólne kontrakty między sektorami A/B/C.

ZMIANY TYLKO PRZEZ PR DO main Z AKCEPTACJĄ CAŁEGO ZESPOŁU.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Document:
    """Wynik sektora A (ingest): tekst dokumentu."""

    path: Path
    text: str
    pages: list[str]  # tekst stron po czyszczeniu
    ocr_used: bool = False
    page_offsets: list[int] = field(default_factory=list)  # offset początku strony i w `text`
    backend: str = ""  # np. "pypdfium2", "pypdf", "pypdfium2+ocr:rapidocr"
    warnings: list[str] = field(default_factory=list)

    def page_of(self, offset: int) -> int | None:
        """Numer strony (0-based) dla offsetu w `text`; None poza tekstem lub bez offsetów."""
        if not self.page_offsets or offset < 0 or offset >= len(self.text):
            return None
        return bisect_right(self.page_offsets, offset) - 1


class IngestError(Exception):
    """Plik nie do wczytania (uszkodzony, zaszyfrowany, nie-PDF); komunikat czytelny dla człowieka."""


@dataclass
class Classification:
    """Wynik sektora A (classify). doc_type=None oznacza dokument nieznany."""

    doc_type: str | None
    confidence: float
    method: str  # "keywords" | "llm" | ...
    scores: dict[str, float] = field(default_factory=dict)
    # trafione cechy (dlaczego ten typ / dlaczego odrzucono)
    evidence: list[str] = field(default_factory=list)


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
