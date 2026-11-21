"""Sektor A: PDF -> Document.

Backend ekstrakcji tekstu wybierany konfiguracją (``config/app.yaml`` -> ``ingest``) lub argumentem,
z fallbackiem na kolejne backendy. Rozpoznaje pliki, których nie da się wczytać (``IngestError``).
Tekst dokumentu = strony złączone ``"\\n\\f\\n"``; ``page_offsets`` wskazują początek każdej strony.

TODO(T5): OCR dla stron bez tekstu.
"""

from __future__ import annotations

from pathlib import Path

from odw2json.config_loader import load_app_config
from odw2json.contracts import Document, IngestError
from odw2json.ingest import backends

PAGE_SEPARATOR = "\n\f\n"
DEFAULT_BACKEND = "pypdf"
_HEADER_SCAN_BYTES = 1024
_BOM = b"\xef\xbb\xbf"


def _check_file(path: Path) -> None:
    """Wstępna walidacja pliku; rzuca IngestError z komunikatem po polsku."""
    try:
        with path.open("rb") as fh:
            head = fh.read(_HEADER_SCAN_BYTES)
    except OSError as e:
        raise IngestError(f"Nie można odczytać pliku: {e}") from e
    if not head:
        raise IngestError("Plik jest pusty (0 B)")
    start = head.removeprefix(_BOM).lstrip()
    if not start.startswith(b"%PDF-"):
        raise IngestError("Plik nie jest PDF-em (brak nagłówka %PDF-)")
    _check_pypdf_structure(path)


def _check_pypdf_structure(path: Path) -> None:
    """Szyfrowanie i liczba stron. Gdy pypdf nie potrafi sparsować pliku, decyzję zostawiamy backendom."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception as e:
                raise IngestError(
                    f"Plik zaszyfrowany – nie udało się odszyfrować ({type(e).__name__})"
                ) from e
            if not ok:
                raise IngestError("Plik zaszyfrowany – brak hasła")
        if len(reader.pages) == 0:
            raise IngestError("PDF bez stron")
    except IngestError:
        raise
    except Exception:  # uszkodzony plik: niech zdecydują backendy (fallback)
        return


def _backend_chain(primary: str, fallbacks: list[str]) -> list[str]:
    chain = [primary]
    chain += [b for b in fallbacks if b not in chain]
    return chain


def _extract(path: Path, primary: str, fallbacks: list[str], warnings: list[str]) -> tuple[str, list[str]]:
    """Pierwszy backend z tekstem; gdy żaden go nie da, pusty wynik pierwszego, który czytał strony."""
    errors: list[str] = []
    empty: tuple[str, list[str]] | None = None
    for name in _backend_chain(primary, fallbacks):
        fn = backends.BACKENDS.get(name)
        if fn is None:
            msg = f"nieznany backend '{name}'"
            errors.append(msg)
            warnings.append(f"Ingest: {msg}")
            continue
        try:
            pages = fn(path)
        except Exception as e:  # każdy błąd backendu = próba kolejnego
            errors.append(f"{name}: {type(e).__name__}: {e}")
            warnings.append(f"Ingest: backend {name} zawiódł ({type(e).__name__}: {e}), próbuję kolejny")
            continue
        if not pages:
            errors.append(f"{name}: brak stron")
            warnings.append(f"Ingest: backend {name} nie zwrócił stron, próbuję kolejny")
            continue
        if not any(p.strip() for p in pages):
            warnings.append(f"Ingest: backend {name} zwrócił pusty tekst, próbuję kolejny")
            if empty is None:
                empty = (name, pages)
            continue
        return name, pages
    if empty is not None:
        warnings.append("Ingest: żaden backend nie wyciągnął tekstu (skan bez warstwy tekstowej?)")
        return empty
    if errors and all("brak stron" in e for e in errors):
        raise IngestError("PDF bez stron")
    raise IngestError("Nie udało się wczytać PDF żadnym backendem: " + "; ".join(errors))


def _clean_pages(pages: list[str], steps: list[str], warnings: list[str]) -> list[str]:
    if not steps:
        return pages
    try:
        from odw2json.ingest.clean import clean_text
    except ImportError:
        warnings.append(
            "Ingest: moduł czyszczenia niedostępny, pominięto kroki czyszczenia: " + ", ".join(steps)
        )
        return pages
    return [clean_text(p, steps) for p in pages]


def _join(pages: list[str]) -> tuple[str, list[int]]:
    offsets: list[int] = []
    pos = 0
    for p in pages:
        offsets.append(pos)
        pos += len(p) + len(PAGE_SEPARATOR)
    return PAGE_SEPARATOR.join(pages), offsets


def load(path: Path, backend: str | None = None, cfg: dict | None = None) -> Document:
    path = Path(path)
    if cfg is None:
        cfg = load_app_config().get("ingest", {}) or {}
    primary = backend or cfg.get("backend") or DEFAULT_BACKEND
    _check_file(path)
    warnings: list[str] = []
    used, pages = _extract(path, primary, list(cfg.get("fallback_backends") or []), warnings)
    pages = _clean_pages(pages, list(cfg.get("clean") or []), warnings)
    text, offsets = _join(pages)
    return Document(
        path=path,
        text=text,
        pages=pages,
        ocr_used=False,
        page_offsets=offsets,
        backend=used,
        warnings=warnings,
    )
