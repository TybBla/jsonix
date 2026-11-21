"""Instalacja na maszynie jury: Python 3.13+ (także najnowszy), start.bat przygotowuje środowisko."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OCR_PACKAGES = ("rapidocr", "onnxruntime")


def _requirements() -> dict[str, str]:
    reqs = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            name = re.split(r"[<>=!~;\s\[]", line, maxsplit=1)[0].lower()
            reqs[name] = line
    return reqs


def test_ocr_packages_are_skipped_on_python_without_wheels():
    """onnxruntime/pyclipper nie mają paczek dla 3.15: bez znacznika cała instalacja się wywraca."""
    reqs = _requirements()
    for name in OCR_PACKAGES:
        assert name in reqs, name
        assert re.search(r';\s*python_version\s*<\s*"3\.15"', reqs[name]), reqs[name]
    for name, line in reqs.items():
        if name not in OCR_PACKAGES:
            assert "python_version" not in line, f"{name}: rdzeń instaluje się na każdym Pythonie 3.13+"


def test_start_scripts_prepare_environment():
    setup = (ROOT / "scripts" / "setup-env.bat").read_text(encoding="utf-8")
    assert "py -%%V" in setup and "3.13 3.14" in setup, "preferuje Pythona z paczkami OCR"
    assert "requirements.txt" in setup and "-m venv" in setup
    assert "(3, 13)" in setup, "sprawdza minimalną wersję"
    for name in ("start.bat", "start-gui.bat"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "setup-env.bat" in text and "%JSONIX_PY%" in text, name
        assert not re.search(r"^\s*python ", text, re.M), f"{name}: nie wołaj gołego python"


def test_batch_files_use_crlf_in_repo():
    """Etykiety i goto w .bat bywają zawodne z samym LF; .gitattributes wymusza CRLF."""
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\.bat\s+text\s+eol=crlf", attrs, re.M)


def test_start_sh_picks_python_313_or_newer():
    text = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "python3.13" in text and "(3, 13)" in text


def test_ci_runs_on_python_313_and_314():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert '"3.13", "3.14"' in ci


def _lock() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, version = line.partition("==")
            assert version, f"wpis bez przypiętej wersji: {line}"
            pins[name.lower().replace("_", "-")] = version
    return pins


def test_every_requirement_has_pinned_version_in_lock():
    pins = _lock()
    for name in _requirements():
        assert name.replace("_", "-") in pins, f"{name}: brak wersji w requirements-lock.txt"


def test_lock_is_used_wherever_dependencies_are_installed():
    files = {
        "Dockerfile": ROOT / "Dockerfile",
        "setup-env.bat": ROOT / "scripts" / "setup-env.bat",
        "smoke.ps1": ROOT / "scripts" / "smoke.ps1",
        "smoke.sh": ROOT / "scripts" / "smoke.sh",
        "ci.yml": ROOT / ".github" / "workflows" / "ci.yml",
    }
    for label, path in files.items():
        assert "-c" in (text := path.read_text(encoding="utf-8")) and "requirements-lock.txt" in text, label
