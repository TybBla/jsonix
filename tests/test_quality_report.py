"""Raport jakości (scripts/quality_report.py): tabela F1 per zbiór/typ/pole i czas na dokument."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("quality_report", ROOT / "scripts" / "quality_report.py")
qr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qr)


def _metrics(f1: float, field_f1: float) -> dict:
    return {
        "f1": f1,
        "precision": 0.9,
        "recall": 0.8,
        "f1_by_type": {"odwolanie": f1, "przelew": 1.0},
        "f1_by_field": {"OdwolanieKIO.data": 1.0, "przelew_bankowy.na_rachunek": field_f1},
        "neg_correct": 12,
        "neg_total": 12,
        "classification_errors": 1,
        "classification_error_files": ["case/x.pdf"],
    }


def test_render_has_summary_types_fields_and_time():
    runs = [
        qr.Run("dev", "tekst", _metrics(0.999, 0.95), docs=40, seconds=20.0, exit_code=0),
        qr.Run("holdout", "skan", _metrics(0.9, 0.5), docs=10, seconds=50.0, exit_code=0),
    ]
    md = qr.render(runs, {"python": "3.13.1"}, "zimny (pusty `output/.cache/ocr`)")
    assert "| dev | tekst | **99.9%** |" in md
    assert "0.50 s" in md and "5.00 s" in md, "czas na dokument"
    assert "| odwolanie | 99.9% | 90.0% |" in md
    assert "**przelew_bankowy.na_rachunek**" in md, "pole z F1 < 0.85 wyróżnione"
    assert "| OdwolanieKIO.data |" in md
    assert "`case/x.pdf`" in md
    assert "zimny" in md and "python: 3.13.1" in md


def test_render_without_documents_or_fields():
    md = qr.render(
        [qr.Run("dev", "skan", {"f1": None}, docs=0, seconds=0.0, exit_code=2)], {}, "brak cache OCR"
    )
    assert "| dev | skan | **—** |" in md
    assert "F1 per pole" not in md


def test_report_runs_on_real_gate_for_one_section(tmp_path):
    out = tmp_path / "raport.md"
    assert qr.main(["--split", "dev", "--source", "tekst", "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert "| dev | tekst |" in md
    assert out.with_suffix(".json").is_file()
