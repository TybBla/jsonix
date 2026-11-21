"""Odporność ingestu na uszkodzone i nietypowe pliki PDF (fixture'y z scripts/make_broken_fixtures.py)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from odw2json import pipeline
from odw2json.contracts import Document, IngestError
from odw2json.ingest import load

REPO_ROOT = Path(__file__).resolve().parent.parent
BROKEN_DIR = REPO_ROOT / "tests" / "fixtures" / "broken"
POLISH_NAME = "zażółć gęślą jaźń.pdf"
BROKEN_NAMES = [
    "empty.pdf",
    "html_udajacy.pdf",
    "zaszyfrowany.pdf",
    "uciety.pdf",
    "pusta_strona.pdf",
    POLISH_NAME,
]


def _fixture(name: str) -> Path:
    path = BROKEN_DIR / name
    if not path.exists():
        pytest.skip(f"brak fixture'a {name}; uruchom scripts/make_broken_fixtures.py")
    return path


def _copy_all_to(dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in BROKEN_NAMES:
        shutil.copyfile(_fixture(name), dst / name)


@pytest.mark.parametrize("name", ["empty.pdf", "html_udajacy.pdf", "zaszyfrowany.pdf"])
def test_unreadable_file_raises_ingest_error(name: str) -> None:
    with pytest.raises(IngestError) as exc:
        load(_fixture(name))
    assert str(exc.value).strip()


def test_truncated_file_raises_ingest_error_or_returns_document() -> None:
    # Obserwacja (T6): loader rzuca IngestError ("Nie udało się wczytać PDF żadnym backendem").
    try:
        doc = load(_fixture("uciety.pdf"))
    except IngestError as exc:
        assert str(exc).strip()
    else:
        assert isinstance(doc, Document)


def test_blank_page_returns_document_with_warnings_or_ingest_error() -> None:
    # Obserwacja (T6): loader zwraca Document z pustym tekstem i ostrzeżeniami (wszystkie backendy
    # zwróciły pusty tekst), nie rzuca IngestError.
    try:
        doc = load(_fixture("pusta_strona.pdf"))
    except IngestError as exc:
        assert str(exc).strip()
    else:
        assert isinstance(doc, Document)
        assert doc.warnings


def test_polish_name_file_loads_with_text() -> None:
    doc = load(_fixture(POLISH_NAME))
    assert isinstance(doc, Document)
    assert doc.text.strip()


def test_pipeline_continues_past_broken_files(tmp_path: Path) -> None:
    inp = tmp_path / "input" / "case1"
    out = tmp_path / "out"
    _copy_all_to(inp)

    report = pipeline.run(
        tmp_path / "input",
        out,
        app_cfg={"unknown_output": "empty_object", "write_trace": False},
    )

    assert (out / "case1" / "zażółć gęślą jaźń.json").exists()
    failed = {Path(e.path).name for e in report.errors}
    assert {"empty.pdf", "html_udajacy.pdf", "zaszyfrowany.pdf"} <= failed


def test_cli_run_exits_zero_on_broken_inputs(tmp_path: Path) -> None:
    inp = tmp_path / "input"
    out = tmp_path / "out"
    _copy_all_to(inp)

    result = subprocess.run(
        [sys.executable, "-m", "odw2json", "run", str(inp), str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
