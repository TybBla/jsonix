"""Sektor A: PDF -> Document.

Wersja bazowa: warstwa tekstowa przez pypdf. TODO(A): czyszczenie tekstu, OCR fallback
dla stron bez tekstu (Tesseract/rapidocr, bez GPU), ewentualnie pdfplumber dla układu.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from odw2json.contracts import Document


def load(path: Path) -> Document:
    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return Document(path=Path(path), text="\n\n".join(pages), pages=pages, ocr_used=False)
