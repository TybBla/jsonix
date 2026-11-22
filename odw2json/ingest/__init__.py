"""Sektor A: PDF -> Document.

Backend ekstrakcji tekstu wybierany konfiguracją (``config/app.yaml`` -> ``ingest``) lub argumentem,
z fallbackiem na kolejne backendy. Rozpoznaje pliki, których nie da się wczytać (``IngestError``).
Tekst dokumentu = strony złączone ``"\\n\\f\\n"``; ``page_offsets`` wskazują początek każdej strony.

OCR (obowiązkowy w requirements, ``ingest.ocr``): strona z tekstem krótszym niż
``min_chars_per_page`` przechodzi przez
``ocr.ocr_page``; brak pakietu OCR daje ostrzeżenie, a nie wyjątek.
"""

from __future__ import annotations

from pathlib import Path

from odw2json.config_loader import load_app_config
from odw2json.contracts import Document, IngestError
from odw2json.ingest import backends, clean, ocr

PAGE_SEPARATOR = "\n\f\n"
_NO_TEXT_WARNING = "Ingest: żaden backend nie wyciągnął tekstu (skan bez warstwy tekstowej?)"
DEFAULT_BACKEND = "pypdfium2"  # decyzja: docs/decyzje/E2-backend-pdf.md
_HEADER_SCAN_BYTES = 1024


def validate_ingest_cfg(cfg: dict) -> None:
    """Fail fast: błędna konfiguracja ingestu (``ValueError`` po polsku) przerywa uruchomienie."""
    cfg = cfg or {}
    available = sorted(backends.BACKENDS)
    primary = cfg.get("backend")
    if primary is not None and primary not in backends.BACKENDS:
        raise ValueError(
            f"Błąd konfiguracji ingest: nieznany backend '{primary}' (ingest.backend). "
            f"Dostępne: {', '.join(available)}"
        )
    for name in cfg.get("fallback_backends") or []:
        if name not in backends.BACKENDS:
            raise ValueError(
                f"Błąd konfiguracji ingest: nieznany backend zapasowy '{name}' "
                f"(ingest.fallback_backends). Dostępne: {', '.join(available)}"
            )
    unknown = [s for s in cfg.get("clean") or [] if s not in clean.CLEAN_STEPS]
    if unknown:
        raise ValueError(
            f"Błąd konfiguracji ingest: nieznane kroki czyszczenia (ingest.clean): {', '.join(unknown)}. "
            f"Dostępne: {', '.join(sorted(clean.CLEAN_STEPS))}"
        )
    _validate_ocr_cfg(cfg.get("ocr"))


def _validate_ocr_cfg(ocr_cfg: object) -> None:
    if ocr_cfg is None:
        return
    if not isinstance(ocr_cfg, dict):
        raise ValueError("Błąd konfiguracji ingest: sekcja ingest.ocr musi być słownikiem")
    engine = ocr_cfg.get("engine")
    if engine is not None and engine not in ocr.OCR_ENGINES:
        raise ValueError(
            f"Błąd konfiguracji ingest: nieznany silnik OCR '{engine}' (ingest.ocr.engine). "
            f"Dostępne: {', '.join(sorted(ocr.OCR_ENGINES))}"
        )
    for key in ("min_chars_per_page", "dpi"):
        val = ocr_cfg.get(key)
        if val is not None and (isinstance(val, bool) or not isinstance(val, int) or val <= 0):
            raise ValueError(
                f"Błąd konfiguracji ingest: ocr.{key} musi być dodatnią liczbą całkowitą (jest {val!r})"
            )
    procs = ocr_cfg.get("max_concurrent_processes")
    if procs is not None and (isinstance(procs, bool) or not isinstance(procs, int) or procs < 0):
        raise ValueError(
            "Błąd konfiguracji ingest: ocr.max_concurrent_processes musi być liczbą całkowitą >= 0 "
            f"(0 = bez limitu; jest {procs!r})"
        )
    timeout = ocr_cfg.get("slot_timeout_s")
    if timeout is not None and (
        isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0
    ):
        raise ValueError(
            f"Błąd konfiguracji ingest: ocr.slot_timeout_s musi być dodatnią liczbą sekund (jest {timeout!r})"
        )
    params = ocr_cfg.get("engine_params")
    if params is not None:
        if not isinstance(params, dict):
            raise ValueError(
                "Błąd konfiguracji ingest: ocr.engine_params musi być słownikiem parametrów silnika"
            )
        for k, v in params.items():
            if not isinstance(k, str) or "." not in k.strip(".") or k.startswith(".") or k.endswith("."):
                raise ValueError(
                    f"Błąd konfiguracji ingest: ocr.engine_params: klucz {k!r} "
                    "musi mieć postać 'Sekcja.parametr'"
                )
            if isinstance(v, dict | list):
                raise ValueError(
                    f"Błąd konfiguracji ingest: ocr.engine_params[{k!r}] "
                    f"musi być wartością skalarną (jest {v!r})"
                )
    post = ocr_cfg.get("postprocess")
    if post is not None:
        if not isinstance(post, list) or not all(isinstance(x, str) for x in post):
            raise ValueError(
                "Błąd konfiguracji ingest: ocr.postprocess musi być listą nazw kroków czyszczenia"
            )
        bad = [x for x in post if x not in clean.CLEAN_STEPS]
        if bad:
            raise ValueError(
                f"Błąd konfiguracji ingest: nieznane kroki czyszczenia (ingest.ocr.postprocess): "
                f"{', '.join(bad)}. Dostępne: {', '.join(sorted(clean.CLEAN_STEPS))}"
            )
    enabled = ocr_cfg.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise ValueError(
            f"Błąd konfiguracji ingest: ingest.ocr.enabled musi być true lub false (jest: {enabled!r})"
        )


def _check_file(path: Path) -> None:
    """Wstępna walidacja pliku; rzuca IngestError z komunikatem po polsku."""
    try:
        with path.open("rb") as fh:
            head = fh.read(_HEADER_SCAN_BYTES)
    except OSError as e:
        raise IngestError(f"Nie można odczytać pliku: {e}") from e
    if not head:
        raise IngestError("Plik jest pusty (0 B)")
    if b"%PDF-" not in head:  # śmieci lub BOM przed nagłówkiem są dozwolone (jak w czytnikach PDF)
        raise IngestError("Plik nie jest PDF-em (brak nagłówka %PDF- w pierwszym kilobajcie)")
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
        warnings.append(_NO_TEXT_WARNING)
        return empty
    if errors and all("brak stron" in e for e in errors):
        raise IngestError("PDF bez stron")
    raise IngestError("Nie udało się wczytać PDF żadnym backendem: " + "; ".join(errors))


def _clean_pages(pages: list[str], steps: list[str]) -> list[str]:
    """Czyszczenie na całym dokumencie (strony złączone ``\\f``), żeby kroki widziały powtórzenia stron."""
    if not steps:
        return pages
    cleaned = clean.clean_text("\f".join(pages), steps).split("\f")
    if len(cleaned) != len(pages):
        raise RuntimeError(
            f"Czyszczenie zmieniło liczbę stron ({len(pages)} -> {len(cleaned)}); "
            "żaden krok nie może usuwać znaku końca strony"
        )
    return cleaned


def _apply_ocr(
    path: Path, pages: list[str], ocr_cfg: dict, warnings: list[str]
) -> tuple[list[str], str | None]:
    """OCR stron bez wystarczającej warstwy tekstowej. Zwraca strony i nazwę silnika (gdy coś rozpoznano).

    Strony z tekstem (>= ``min_chars_per_page`` znaków) nigdy nie trafiają do OCR. Rozpoznany tekst
    zastępuje stronę tylko wtedy, gdy jest dłuższy od tego, co już było. Kroki ``ocr.postprocess``
    (np. ``ocr_artifacts``) dotyczą wyłącznie tekstu z OCR i są stosowane przed ogólnym czyszczeniem.
    """
    if not ocr_cfg.get("enabled"):
        return pages, None
    threshold = int(ocr_cfg.get("min_chars_per_page", 30))
    todo = [i for i, p in enumerate(pages) if len(p.strip()) < threshold]
    if not todo:
        return pages, None
    engine = ocr_cfg.get("engine") or ocr.DEFAULT_ENGINE
    if not ocr.ocr_available(engine):
        warnings.extend(f"OCR niedostępny – strona {i + 1} bez tekstu" for i in todo)
        return pages, None
    pages = list(pages)
    post = list(ocr_cfg.get("postprocess") or [])
    used = False
    for i in todo:
        try:
            text = ocr.ocr_page(path, i, ocr_cfg)
        except Exception as e:  # błąd OCR jednej strony (już po ponowieniach) nie przerywa wczytywania
            warnings.append(f"OCR nieudany – strona {i + 1} ({ocr.short_error(e)})")
            continue
        if post:
            text = clean.clean_text(text, post)
        if len(text.strip()) > len(pages[i].strip()):
            pages[i] = text
            used = True
            warnings.append(f"OCR strony {i + 1}")
        else:
            warnings.append(f"OCR strony {i + 1}: nie rozpoznano tekstu")
    return pages, (engine if used else None)


def _join(pages: list[str]) -> tuple[str, list[int]]:
    offsets: list[int] = []
    pos = 0
    for p in pages:
        offsets.append(pos)
        pos += len(p) + len(PAGE_SEPARATOR)
    return PAGE_SEPARATOR.join(pages), offsets


def load(path: Path, backend: str | None = None, cfg: dict | None = None) -> Document:
    path = Path(path)
    file_cfg = load_app_config().get("ingest", {}) or {}
    cfg = file_cfg if cfg is None else {**file_cfg, **cfg}  # brakujące klucze z config/app.yaml
    validate_ingest_cfg(cfg)
    primary = backend or cfg.get("backend") or DEFAULT_BACKEND
    _check_file(path)
    warnings: list[str] = []
    used, pages = _extract(path, primary, list(cfg.get("fallback_backends") or []), warnings)
    pages, ocr_engine = _apply_ocr(path, pages, cfg.get("ocr") or {}, warnings)
    if ocr_engine and all(p.strip() for p in pages) and _NO_TEXT_WARNING in warnings:
        warnings.remove(_NO_TEXT_WARNING)  # OCR odzyskał tekst wszystkich stron: ostrzeżenie nieaktualne
    pages = [p.replace("\f", "\n") for p in pages]  # \f jest zarezerwowany jako separator stron
    pages = _clean_pages(pages, list(cfg.get("clean") or []))
    text, offsets = _join(pages)
    return Document(
        path=path,
        text=text,
        pages=pages,
        ocr_used=ocr_engine is not None,
        page_offsets=offsets,
        backend=f"{used}+ocr:{ocr_engine}" if ocr_engine else used,
        warnings=warnings,
    )
