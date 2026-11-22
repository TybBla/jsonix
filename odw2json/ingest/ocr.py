"""OCR dla stron bez warstwy tekstowej (opcjonalny; brak pakietu nie psuje aplikacji).

Strona PDF jest renderowana przez pypdfium2 (domyślnie 200 DPI, produkcyjnie 150), a obraz trafia
do silnika wybranego w ``config/app.yaml`` -> ``ingest.ocr.engine``. Silniki siedzą w rejestrze
``OCR_ENGINES``; ich
biblioteki są importowane leniwie, a ``ocr_available`` sprawdza obecność pakietów bez importu.

Domyślny silnik ``rapidocr`` (obowiązkowy: ``requirements.txt``) używa modelu PP-OCRv6 "multi"
dołączonego do paczki (bez pobierania modeli w czasie działania), który obsługuje m.in. język polski.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.metadata
import importlib.util
import json
import logging
import os
import tempfile
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from odw2json import config_loader

DEFAULT_ENGINE = "rapidocr"
DEFAULT_DPI = 200
OCR_CACHE_VERSION = (
    "2"  # podbić przy zmianie renderowania/składania wierszy/parametrów, żeby unieważnić stary cache
)
MEMO_MAX = 256

# Stabilność pod obciążeniem (docs/decyzje/E2b-ocr-wydajnosc.md, „Stabilność pod obciążeniem”): przy braku
# pamięci onnxruntime rzuca ``bad allocation``, a numpy ``MemoryError``. Strona jest wtedy ponawiana po
# przerwie (szczyt pamięci innych procesów mija). Mniej wątków ORT NIE obniża szczytu (zmierzone: 990 MB
# przy 1 i 4 wątkach), a osobna instancja silnika kosztowałaby kolejne ok. 600 MB, więc ponowienia
# używają tej samej konfiguracji.
OCR_ATTEMPTS = 5
RETRY_DELAYS_S = (2.0, 5.0, 10.0, 20.0)  # przerwa przed kolejnymi próbami (razem maks. 37 s na stronę)

log = logging.getLogger(__name__)

# Silnik sam wątkuje (intra_op_num_threads), więc równoległe wywołania w jednym procesie tylko mnożą
# szczytowe zużycie pamięci i nadsubskrybują CPU; RapidOCR nie deklaruje też bezpieczeństwa wątkowego.
_ENGINE_LOCK = threading.Lock()


# Limit procesów OCR-ujących naraz na maszynie (``ingest.ocr.max_concurrent_processes``; 0 = bez limitu).
# Każdy proces z silnikiem trzyma ok. 600 MB, a przy stronie dochodzi ok. 400 MB szczytu; równoległe szczyty
# kilku procesów wyczerpywały limit pamięci (commit). Slot = blokada pliku w katalogu tymczasowym systemu,
# zwalniana przez system także po awarii procesu.
DEFAULT_SLOT_TIMEOUT_S = 900.0
SLOT_DIR = Path(tempfile.gettempdir()) / "odw2json-ocr-slots"


def _lock_fd(fd: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _try_acquire_slot(lock_dir: Path, slots: int) -> int | None:
    """Deskryptor zablokowanego pliku slotu albo ``None``, gdy wszystkie ``slots`` są zajęte."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    for k in range(slots):
        fd = os.open(lock_dir / f"slot-{k}.lock", os.O_RDWR | os.O_CREAT, 0o644)
        if _lock_fd(fd):
            return fd
        os.close(fd)
    return None


def _release_slot(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        os.close(fd)


@contextmanager
def _ocr_slot(cfg: dict, lock_dir: Path | None = None, poll_s: float = 0.2) -> Iterator[None]:
    """Czeka na wolny slot OCR na maszynie; po ``slot_timeout_s`` przetwarza mimo wszystko (z logiem)."""
    slots = cfg.get("max_concurrent_processes") or 0  # brak klucza = bez limitu; produkcyjnie 1 w app.yaml
    if not slots:
        yield
        return
    timeout = float(cfg.get("slot_timeout_s") or DEFAULT_SLOT_TIMEOUT_S)
    lock_dir = lock_dir or SLOT_DIR
    deadline = time.monotonic() + timeout
    fd = None
    try:
        fd = _try_acquire_slot(lock_dir, int(slots))
        while fd is None and time.monotonic() < deadline:
            time.sleep(poll_s)
            fd = _try_acquire_slot(lock_dir, int(slots))
    except OSError as e:  # brak dostępu do katalogu blokad nie może zatrzymać OCR
        log.warning("OCR: slot międzyprocesowy niedostępny (%s), przetwarzam bez limitu", short_error(e))
    if fd is None:
        log.warning("OCR: brak wolnego slotu po %.0f s, przetwarzam bez limitu", timeout)
    try:
        yield
    finally:
        if fd is not None:
            _release_slot(fd)


class OcrError(RuntimeError):
    """OCR strony nie powiódł się mimo ponowień (komunikat jednowierszowy, po polsku)."""


def short_error(e: BaseException, limit: int = 200) -> str:
    """``Typ: ostatni niepusty wiersz komunikatu`` (bez tracebacku ORT), przycięte do ``limit`` znaków."""
    lines = [ln.strip() for ln in str(e).splitlines() if ln.strip()]
    msg = lines[-1] if lines else ""
    out = f"{type(e).__name__}: {msg}" if msg else type(e).__name__
    return out if len(out) <= limit else out[: limit - 1] + "…"


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


def _params_key(params: dict | None) -> str:
    """Kanoniczny zapis ``engine_params`` (kolejność kluczy nie ma znaczenia); pusty = brak parametrów."""
    return json.dumps(params, sort_keys=True, ensure_ascii=True, default=str) if params else ""


def _params_tag(params: dict | None) -> str:
    """Krótki skrót parametrów silnika do nazwy pliku cache i klucza pamięci procesu."""
    key = _params_key(params)
    return hashlib.sha1(key.encode()).hexdigest()[:8] if key else "p0"


@lru_cache(maxsize=4)
def _rapidocr_engine(params_key: str = ""):
    from rapidocr import RapidOCR

    return RapidOCR(params=json.loads(params_key) if params_key else None)


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

    engine = _rapidocr_engine(_params_key(cfg.get("engine_params")))
    result = engine(np.asarray(image.convert("RGB")))
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

    ``cfg`` = sekcja ``ingest.ocr`` (``engine``, opcjonalnie ``dpi``, ``engine_params`` (płaski słownik
    parametrów silnika, np. RapidOCR ``Global.use_cls``) i ``cache_dir``: katalog z wynikami OCR
    kluczowanymi hashem pliku, DPI, parametrami silnika, wersją cache i wersją pakietu OCR;
    względny ``cache_dir`` liczony od korzenia repozytorium). Wynik jest też pamiętany w procesie
    (LRU; klucz: hash zawartości pliku, więc kopie pliku też trafiają). Rzuca wyjątek, gdy silnik
    jest nieznany lub niezainstalowany; wołający powinien wcześniej sprawdzić ``ocr_available``.
    """
    cfg = cfg or {}
    name = cfg.get("engine") or DEFAULT_ENGINE
    engine = _engine(name)
    dpi = int(cfg.get("dpi") or DEFAULT_DPI)
    digest = _file_digest(Path(path))
    ptag = _params_tag(cfg.get("engine_params"))
    key = (digest, page_index, name, dpi, ptag)
    hit = _memo_get(key)
    if hit is not None:
        return hit
    cache = None
    if cfg.get("cache_dir"):
        tag = f"v{OCR_CACHE_VERSION}.{_package_version()}"
        cache = resolve_cache_dir(cfg["cache_dir"]) / f"{digest}.{page_index}.{name}.{dpi}.{ptag}.{tag}.txt"
        cached = _read_cache(cache)
        if cached is not None:
            _memo_put(key, cached)
            return cached
    with _ENGINE_LOCK:
        hit = _memo_get(key)  # inny wątek mógł policzyć tę stronę, gdy czekaliśmy na blokadę
        if hit is not None:
            return hit
        text = _run_with_retries(engine, Path(path), page_index, dpi, cfg)
    if text.strip():  # pusty wynik nie trafia do pamięci ani cache: kolejne wywołanie spróbuje ponownie
        _memo_put(key, text)
        if cache is not None:
            _write_cache(cache, text)
    return text


def _run_with_retries(engine: OcrEngine, path: Path, page_index: int, dpi: int, cfg: dict) -> str:
    """Render + silnik z ponowieniami; po ``OCR_ATTEMPTS`` nieudanych próbach rzuca ``OcrError``."""
    last: BaseException | None = None
    for attempt in range(OCR_ATTEMPTS):
        try:
            with _ocr_slot(cfg):
                return engine.run(render_page(path, page_index, dpi), cfg)
        except Exception as e:  # bad allocation (ORT), MemoryError (numpy) i inne błędy przejściowe
            last = e
            log.warning(
                "OCR %s strona %d: próba %d/%d nieudana (%s)",
                path.name,
                page_index + 1,
                attempt + 1,
                OCR_ATTEMPTS,
                short_error(e),
            )
            if attempt < OCR_ATTEMPTS - 1:
                gc.collect()
                time.sleep(RETRY_DELAYS_S[min(attempt, len(RETRY_DELAYS_S) - 1)])
    assert last is not None
    raise OcrError(f"{OCR_ATTEMPTS} próby, ostatni błąd {short_error(last)}") from last
