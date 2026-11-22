"""Statyczne sprawdzenie scripts/setup-env.bat: gotowe środowisko na Pythonie 3.13/3.14 musi mieć też OCR."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP = (ROOT / "scripts" / "setup-env.bat").read_text(encoding="utf-8")


def test_ocr_modules_checked_for_ready_environment():
    m = re.search(r'set "JSONIX_OCR_DEPS=([^"]+)"', SETUP)
    assert m, "osobna lista modułów OCR"
    assert "rapidocr" in m.group(1) and "onnxruntime" in m.group(1)


def test_ocr_not_required_on_python_315_plus():
    assert "(3, 15)" in SETUP, "wersja 3.15+ rozpoznawana osobno"
    usable = SETUP.rsplit(":usable", 1)[1]
    assert "JSONIX_OCR_DEPS" in usable and "(3, 15)" in usable


def test_existing_venv_without_ocr_is_repaired():
    assert "JSONIX_NOOCR_PY" in SETUP
    assert "requirements-lock.txt" in SETUP
    assert SETUP.count("pip install") >= 2, "doinstalowanie OCR w istniejącym venv"


def test_setup_env_stays_ascii():
    SETUP.encode("ascii")
