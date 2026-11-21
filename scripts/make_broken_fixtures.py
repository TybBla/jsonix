"""Generuje uszkodzone / nietypowe pliki PDF do testów odporności ingestu.

Uruchomienie (z korzenia repo): python scripts/make_broken_fixtures.py
Wynik: tests/fixtures/broken/
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PDF = REPO_ROOT / "data" / "train" / "przyklad_01" / "odwolanie.pdf"
OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "broken"
ENCRYPT_PASSWORD = "test"


def _write_empty(out: Path) -> None:
    out.write_bytes(b"")


def _write_html(out: Path) -> None:
    out.write_text("<html><body>to nie jest PDF</body></html>", encoding="utf-8")


def _write_truncated(out: Path, source: bytes) -> None:
    out.write_bytes(source[: len(source) // 2])


def _write_encrypted(out: Path) -> None:
    reader = PdfReader(str(SOURCE_PDF))
    writer = PdfWriter(clone_from=reader)
    writer.encrypt(ENCRYPT_PASSWORD)
    with out.open("wb") as fh:
        writer.write(fh)


def _write_blank(out: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with out.open("wb") as fh:
        writer.write(fh)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source = SOURCE_PDF.read_bytes()

    _write_empty(OUT_DIR / "empty.pdf")
    _write_html(OUT_DIR / "html_udajacy.pdf")
    _write_truncated(OUT_DIR / "uciety.pdf", source)
    _write_encrypted(OUT_DIR / "zaszyfrowany.pdf")
    _write_blank(OUT_DIR / "pusta_strona.pdf")
    shutil.copyfile(SOURCE_PDF, OUT_DIR / "zażółć gęślą jaźń.pdf")

    for path in sorted(OUT_DIR.iterdir()):
        print(f"{path.name}: {path.stat().st_size} B")


if __name__ == "__main__":
    main()
