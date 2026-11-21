"""OCR dla stron bez warstwy tekstowej (opcjonalny; brak pakietu nie psuje aplikacji).

Strona PDF jest renderowana przez pypdfium2 (~200 DPI), a obraz trafia do silnika wybranego w
``config/app.yaml`` -> ``ingest.ocr.engine``. Silniki siedzą w rejestrze ``OCR_ENGINES``; ich
biblioteki są importowane leniwie, a ``ocr_available`` sprawdza obecność pakietów bez importu.

Domyślny silnik ``rapidocr`` (``pip install -r requirements-ocr.txt``) używa modelu PP-OCRv6 "multi"
dołączonego do paczki (bez pobierania modeli w czasie działania), który obsługuje m.in. język polski.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import os
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from odw2json import config_loader

DEFAULT_ENGINE = "rapidocr"
DEFAULT_DPI = 200
OCR_CACHE_VERSION = "1"  # podbić przy zmianie renderowania/składania wierszy, żeby unieważnić stary cache
MEMO_MAX = 256


@dataclass(frozen=True)
class OcrEngine:
    """Silnik OCR: ``available()`` bez ciężkich importów, ``run(image, cfg)`` zwraca tekst strony."""

    available: Callable[[], bool]
    run: Callable[[Any, dict], str]


def _has_modules(*names: str) -> bool:
    try:
        return all(importlib.util.find_spec(n) is not None for n in names)
    except (ImportError, ValueError):
        return False


# --- RapidOCR -----------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _rapidocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def _group_lines(boxes, texts) -> str:
    """Składa rozpoznane fragmenty w wiersze: z góry na dół, w wierszu od lewej do prawej."""
    items = []
    for box, txt in zip(boxes, texts, strict=False):
        if not txt or not str(txt).strip():
            continue
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        items.append((sum(ys) / len(ys), max(ys) - min(ys), min(xs), str(txt).strip()))
    items.sort(key=lambda t: t[0])
    lines: list[list[tuple[float, float, str]]] = []
    centers: list[float] = []
    heights: list[float] = []
    for cy, h, x, txt in items:
        if lines and abs(cy - centers[-1]) <= 0.5 * max(h, heights[-1]):
            lines[-1].append((x, h, txt))
            n = len(lines[-1])
            centers[-1] += (cy - centers[-1]) / n
            heights[-1] = max(heights[-1], h)
        else:
            lines.append([(x, h, txt)])
            centers.append(cy)
            heights.append(h)
    return "\n".join(" ".join(t for _, _, t in sorted(line)) for line in lines)


def _rapidocr_run(image, cfg: dict) -> str:
    import numpy as np

    result = _rapidocr_engine()(np.asarray(image.convert("RGB")))
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    if boxes is None or texts is None:
        return ""
    return _group_lines(boxes, texts)


OCR_ENGINES: dict[str, OcrEngine] = {
    "rapidocr": OcrEngine(
        available=lambda: _has_modules("rapidocr", "onnxruntime"),
        run=_rapidocr_run,
    ),
}


# --- API ----------------------------------------------------------------------------------------


def _engine(name: str | None) -> OcrEngine:
    name = name or DEFAULT_ENGINE
    try:
        return OCR_ENGINES[name]
    except KeyError:
        raise ValueError(
            f"Nieznany silnik OCR '{name}' (ingest.ocr.engine). Dostępne: {', '.join(sorted(OCR_ENGINES))}"
        ) from None


def ocr_available(engine: str | None = None) -> bool:
    """Czy pakiety wybranego silnika (domyślnie ``rapidocr``) są zainstalowane. Nie rzuca wyjątków."""
    eng = OCR_ENGINES.get(engine or DEFAULT_ENGINE)
    return bool(eng and eng.available())


def render_page(path: Path, page_index: int, dpi: int = DEFAULT_DPI):
    """Strona PDF -> obraz PIL (pypdfium2)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[page_index]
        try:
            return page.render(scale=dpi / 72).to_pil()
        finally:
            page.close()
    finally:
        pdf.close()


_MEMO: OrderedDict[tuple, str] = OrderedDict()  # LRU w obrębie procesu (max ``MEMO_MAX`` stron)


def _memo_get(key: tuple) -> str | None:
    if key in _MEMO:
        _MEMO.move_to_end(key)
        return _MEMO[key]
    return None


def _memo_put(key: tuple, text: str) -> None:
    _MEMO[key] = text
    _MEMO.move_to_end(key)
    while len(_MEMO) > MEMO_MAX:
        _MEMO.popitem(last=False)


def _hash_file(path: str) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=64)
def _digest_cached(path: str, mtime_ns: int, size: int) -> str:
    return _hash_file(path)


def _file_digest(path: Path) -> str:
    """Hash zawartości pliku, liczony raz na (ścieżka, mtime, rozmiar), nie przy każdej stronie."""
    st = Path(path).stat()
    return _digest_cached(str(path), st.st_mtime_ns, st.st_size)


_file_digest.cache_clear = _digest_cached.cache_clear  # type: ignore[attr-defined]


@lru_cache(maxsize=1)
def _package_version() -> str:
    try:
        return importlib.metadata.version("rapidocr")
    except Exception:
        return "na"


def resolve_cache_dir(cache_dir: str | os.PathLike) -> Path:
    """Względny ``cache_dir`` liczony od korzenia repozytorium (nie od cwd); bezwzględny bez zmian."""
    p = Path(cache_dir)
    return p if p.is_absolute() else config_loader.ROOT_DIR / p


def _read_cache(path: Path) -> str | None:
    """Zawartość pliku cache albo ``None`` (brak, uszkodzony lub pusty = miss)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return text if text.strip() else None


def _write_cache(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ocr_page(path: Path, page_index: int, cfg: dict | None = None) -> str:
    """Tekst strony ``page_index`` (0-based) pliku ``path`` rozpoznany OCR-em.

    ``cfg`` = sekcja ``ingest.ocr`` (``engine``, opcjonalnie ``dpi`` i ``cache_dir``: katalog z
    wynikami OCR kluczowanymi hashem pliku, wersją cache i wersją pakietu OCR; względny ``cache_dir``
    liczony od korzenia repozytorium). Wynik jest też pamiętany w procesie (LRU; klucz: hash
    zawartości pliku, więc kopie pliku też trafiają). Rzuca wyjątek, gdy silnik jest nieznany lub
    niezainstalowany; wołający powinien wcześniej sprawdzić ``ocr_available``.
    """
    cfg = cfg or {}
    name = cfg.get("engine") or DEFAULT_ENGINE
    engine = _engine(name)
    dpi = int(cfg.get("dpi") or DEFAULT_DPI)
    digest = _file_digest(Path(path))
    key = (digest, page_index, name, dpi)
    hit = _memo_get(key)
    if hit is not None:
        return hit
    cache = None
    if cfg.get("cache_dir"):
        tag = f"v{OCR_CACHE_VERSION}.{_package_version()}"
        cache = resolve_cache_dir(cfg["cache_dir"]) / f"{digest}.{page_index}.{name}.{dpi}.{tag}.txt"
        cached = _read_cache(cache)
        if cached is not None:
            _memo_put(key, cached)
            return cached
    text = engine.run(render_page(Path(path), page_index, dpi), cfg)
    _memo_put(key, text)
    if cache is not None:
        _write_cache(cache, text)
    return text
