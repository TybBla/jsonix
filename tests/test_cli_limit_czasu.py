"""Limit czasu UZP (kryteria pkt 5a): częściowe wyniki przetrwają przerwanie przebiegu CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from odw2json import cli, pipeline

ROOT = Path(__file__).resolve().parents[1]
P01 = ROOT / "data" / "train" / "przyklad_01"
NAMES = ("odwolanie.pdf", "pelnomocnictwo.pdf", "potwierdzenie_przelewu.pdf")


def _input(tmp_path: Path) -> tuple[Path, Path]:
    case = tmp_path / "in" / "sprawa"
    case.mkdir(parents=True)
    for name in NAMES:
        shutil.copy(P01 / name, case / name)
    return tmp_path / "in", tmp_path / "out"


def test_unprocessed_files_have_empty_object_after_interruption(tmp_path, monkeypatch):
    inp, out = _input(tmp_path)
    real = pipeline.process_file_ex
    done = []

    def stop_after_first(pdf, *a, **k):
        if done:
            raise KeyboardInterrupt  # jak zatrzymanie procesu po przekroczeniu czasu
        done.append(Path(pdf).with_suffix(".json").name)
        return real(pdf, *a, **k)

    monkeypatch.setattr(pipeline, "process_file_ex", stop_after_first)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["run", str(inp), str(out)])
    results = {p.name: p.read_text(encoding="utf-8") for p in (out / "sprawa").glob("*.json")}
    assert set(results) == {n.replace(".pdf", ".json") for n in NAMES}, "plik wynikowy dla każdego PDF"
    assert results[done[0]] != "{}", "przetworzony plik ma pełny wynik"
    assert all(v == "{}" for k, v in results.items() if k != done[0])


def test_full_run_overwrites_placeholders(tmp_path):
    inp, out = _input(tmp_path)
    assert cli.main(["run", str(inp), str(out)]) == 0
    assert all((out / "sprawa" / n.replace(".pdf", ".json")).read_text("utf-8") != "{}" for n in NAMES)


def test_placeholders_follow_unknown_output_setting(tmp_path):
    inp, out = _input(tmp_path)
    pdfs = sorted(inp.rglob("*.pdf"))
    cli.write_placeholders(pdfs, inp, out, {"unknown_output": "none"})
    assert not list(out.rglob("*.json")), "tryb 'none': nieprzetworzony plik nie dostaje wyniku"
    cli.write_placeholders(pdfs, inp, out, {"unknown_output": "empty_file"})
    assert all(p.read_text("utf-8") == "" for p in out.rglob("*.json"))


def test_cli_uses_pipeline_list_inputs(tmp_path, monkeypatch):
    inp, out = _input(tmp_path)
    calls = []
    real = pipeline.list_inputs

    def spy(*a, **k):
        calls.append(a[0])
        return real(*a, **k)

    monkeypatch.setattr(pipeline, "list_inputs", spy)
    assert cli.main(["run", str(inp), str(out)]) == 0
    assert len(calls) == 2, "lista wejść z jednej funkcji: placeholdery w CLI i przebieg w pipeline.run"
