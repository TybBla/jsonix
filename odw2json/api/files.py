"""Walidacja i bezpieczne nazwy wgrywanych plików (API pod GUI)."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

PDF_MAGIC = b"%PDF-"
HEADER_WINDOW = 1024

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE = re.compile(r"[^\w.\- ]", re.UNICODE)
_NON_DECOMPOSABLE = str.maketrans({"ł": "l", "Ł": "L"})
_RESERVED = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(10)}


def has_pdf_header(head: bytes) -> bool:
    """Czy w pierwszych 1024 B jest sygnatura `%PDF-` (tak sprawdzają to czytniki PDF)."""
    return PDF_MAGIC in head[:HEADER_WINDOW]


def display_name(raw: str | None) -> str:
    """Nazwa do wyświetlenia: bez ścieżki i znaków sterujących, polskie znaki zachowane."""
    name = unicodedata.normalize("NFC", raw or "")
    name = re.split(r"[\\/]", name)[-1]
    name = _CONTROL.sub("", name).strip().lstrip(".").strip()
    return name or "dokument.pdf"


def storage_name(display: str, taken: set[str]) -> str:
    """Nazwa pliku na dysku i w URL: tylko litery/cyfry/`._- `, bez `..`, unikalna w jobie."""
    safe = _UNSAFE.sub("_", display)
    safe = re.sub(r"\.{2,}", ".", safe).strip(" .") or "dokument"
    stem, dot, ext = safe.rpartition(".")
    if not dot:
        stem, ext = safe, ""
    stem = stem[:120] or "dokument"
    if stem.casefold() in _RESERVED:
        stem = f"_{stem}"
    candidate = f"{stem}.{ext}" if ext else stem
    n = 2
    while candidate.casefold() in {t.casefold() for t in taken}:
        candidate = f"{stem}_{n}.{ext}" if ext else f"{stem}_{n}"
        n += 1
    return candidate


def json_name(display: str) -> str:
    """Nazwa wynikowego JSON jak nazwa PDF (rozszerzenie zamienione na .json)."""
    stem = display[: -len(".pdf")] if display.lower().endswith(".pdf") else display.rsplit(".", 1)[0]
    return f"{stem or 'dokument'}.json"


def content_disposition(filename: str) -> str:
    """Nagłówek `attachment` z nazwą ASCII (fallback) i pełną nazwą UTF-8 (RFC 6266/5987)."""
    ascii_name = filename.translate(_NON_DECOMPOSABLE)
    ascii_name = unicodedata.normalize("NFKD", ascii_name).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r'["\\\r\n]', "_", ascii_name) or "plik"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
