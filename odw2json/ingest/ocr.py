"""OCR dla stron bez warstwy tekstowej (opcjonalny; brak pakietu nie psuje aplikacji).

Strona PDF jest renderowana przez pypdfium2 (~200 DPI), a obraz trafia do silnika wybranego w
``config/app.yaml`` -> ``ingest.ocr.engine``. Silniki siedzą w rejestrze ``OCR_ENGINES``; ich
biblioteki są importowane leniwie, a ``ocr_available`` sprawdza obecność pakietów bez importu.

Domyślny silnik ``rapidocr`` (``pip install -r requirements-ocr.txt``) używa modelu PP-OCRv6 "multi"
dołączonego do paczki (bez pobierania modeli w czasie działania), który obsługuje m.in. język polski.
"""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_ENGINE = "rapidocr"
DEFAULT_DPI = 200


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


_MEMO: dict[tuple, str] = {}  # wyniki w obrębie procesu: ta sama treść pliku = jeden OCR strony


def ocr_page(path: Path, page_index: int, cfg: dict | None = None) -> str:
    """Tekst strony ``page_index`` (0-based) pliku ``path`` rozpoznany OCR-em.

    ``cfg`` = sekcja ``ingest.ocr`` (``engine``, opcjonalnie ``dpi`` i ``cache_dir``: katalog z
    wynikami OCR kluczowanymi hashem pliku, żeby kolejne uruchomienia nie liczyły strony drugi raz).
    Wynik jest też pamiętany w procesie (klucz: hash zawartości pliku, więc kopie pliku też trafiają).
    Rzuca wyjątek, gdy silnik jest nieznany lub niezainstalowany; wołający powinien wcześniej
    sprawdzić ``ocr_available``.
    """
    cfg = cfg or {}
    name = cfg.get("engine") or DEFAULT_ENGINE
    engine = _engine(name)
    dpi = int(cfg.get("dpi") or DEFAULT_DPI)
    digest = hashlib.sha1(Path(path).read_bytes()).hexdigest()
    key = (digest, page_index, name, dpi)
    if key in _MEMO:
        return _MEMO[key]
    cache = None
    if cfg.get("cache_dir"):
        cache = Path(cfg["cache_dir"]) / f"{digest}.{page_index}.{name}.{dpi}.txt"
        if cache.is_file():
            _MEMO[key] = cache.read_text(encoding="utf-8")
            return _MEMO[key]
    text = engine.run(render_page(Path(path), page_index, dpi), cfg)
    _MEMO[key] = text
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    return text
