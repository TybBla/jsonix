"""Backendy ekstrakcji tekstu z PDF: ``extract_pages(path) -> list[str]`` (tekst per strona).

Biblioteki importowane leniwie, żeby brak jednej nie psuł pozostałych.
Wybór backendu i kolejność fallbacku: ``config/app.yaml`` -> ``ingest``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def _pypdf(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    return [(p.extract_text() or "") for p in reader.pages]


def _pdfplumber(path: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def _fix_pdfium_text(text: str) -> str:
    """Końce wierszy do ``\\n``; usuwa U+FFFE (znacznik miękkiego łącznika), więc wyraz się skleja."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("￾", "")


def _pypdfium2(path: Path) -> list[str]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        pages: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            try:
                text = textpage.get_text_range()
            finally:
                textpage.close()
                page.close()
            pages.append(_fix_pdfium_text(text))
        return pages
    finally:
        pdf.close()


BACKENDS: dict[str, Callable[[Path], list[str]]] = {
    "pypdf": _pypdf,
    "pdfplumber": _pdfplumber,
    "pypdfium2": _pypdfium2,
}
