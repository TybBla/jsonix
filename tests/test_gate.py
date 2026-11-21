"""Testy bramki F1 (eval.gate) na malym podzbiorze: 2 sprawy + 1 negatyw."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval import gate
from odw2json import classify as classify_mod
from odw2json import extract as extract_mod
from odw2json.contracts import Classification

pytestmark = pytest.mark.slow

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train"
CASES = ["przyklad_01", "przyklad_02"]
NEGATIVES = ["KIO_KIO 2617-21.pdf"]
KWOTA = "przelew_bankowy.kwota"


@pytest.fixture
def run(tmp_path):
    def _run(split: str = "dev", **kw):
        kw.setdefault("baseline_path", tmp_path / "baseline.json")
        kw.setdefault("gate_dir", tmp_path / "gate")
        kw.setdefault("cases", CASES)
        kw.setdefault("negatives", NEGATIVES)
        kw.setdefault("train_dir", TRAIN)
        return gate.run_gate(split, **kw)

    return _run


def _patch_kwota(monkeypatch, delta: float = 0.0, extra_key: bool = False):
    """extract: wypelnia kwote przelewu z GT (+ delta) i opcjonalnie dodaje obcy klucz."""
    real = extract_mod.extract

    def fake(doc, cfg):
        res = real(doc, cfg)
        if cfg.id == "przelew":
            gt = json.loads((TRAIN / doc.path.parent.name / "przelew.json").read_text(encoding="utf-8"))
            res.data["przelew_bankowy"]["kwota"] = gt["przelew_bankowy"]["kwota"] + delta
        if extra_key:
            res.data["obcy_klucz"] = 1
        return res

    monkeypatch.setattr(extract_mod, "extract", fake)


def test_update_then_run_is_green(run):
    first = run(update=True)
    assert first.exit_code == 0
    assert first.metrics["pipeline_errors"] == 0
    assert first.metrics["schema_errors"] == 0
    assert first.metrics["neg_total"] == 1
    second = run()
    assert second.exit_code == 0
    assert second.regressions == []


def test_baseline_file_shape(run, tmp_path):
    run(update=True)
    data = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    sec = data["dev"]
    for key in (
        "f1",
        "precision",
        "recall",
        "f1_by_type",
        "f1_by_field",
        "neg_correct",
        "neg_total",
        "schema_errors",
        "classification_errors",
        "pipeline_errors",
        "updated",
        "commit",
    ):
        assert key in sec
    assert set(sec["f1_by_type"]) == {"odwolanie", "pelnomocnictwo", "przelew"}
    assert list(sec["f1_by_field"]) == sorted(sec["f1_by_field"])
    # wynik gate zapisany tez do gate_dir
    assert (tmp_path / "gate" / "dev.json").is_file()


def test_field_regression_is_detected(run, monkeypatch):
    _patch_kwota(monkeypatch)  # kwota poprawna
    good = run(update=True)
    assert good.metrics["f1_by_field"][KWOTA] == 1.0
    _patch_kwota(monkeypatch, delta=1.0)  # kwota zla
    bad = run()
    assert bad.exit_code == 1
    assert any(KWOTA in r for r in bad.regressions)
    assert bad.metrics["f1_by_field"][KWOTA] < 1.0


def test_tolerance_absorbs_drop(run, monkeypatch):
    _patch_kwota(monkeypatch)
    run(update=True)
    _patch_kwota(monkeypatch, delta=1.0)
    res = run(tolerance=1.0)
    assert res.exit_code == 0
    assert res.regressions == []


def test_extra_key_is_schema_error(run, monkeypatch):
    run(update=True)  # dobry baseline
    _patch_kwota(monkeypatch, extra_key=True)
    res = run()
    assert res.metrics["schema_errors"] > 0
    assert res.exit_code == 1
    assert any("schema_errors" in r for r in res.regressions)


def test_update_refused_on_schema_errors(run, monkeypatch, tmp_path):
    _patch_kwota(monkeypatch, extra_key=True)
    res = run(update=True)
    assert res.exit_code == 1
    assert not (tmp_path / "baseline.json").exists()


def test_negative_misclassified(run, monkeypatch):
    base = run(update=True)
    assert base.metrics["neg_correct"] == base.metrics["neg_total"] == 1
    monkeypatch.setattr(
        classify_mod, "classify", lambda doc, registry: Classification("odwolanie", 1.0, "patched")
    )
    res = run()
    assert res.metrics["classification_errors"] > base.metrics["classification_errors"]
    assert res.metrics["neg_correct"] == 0
    assert res.exit_code == 1


def test_pipeline_exception_is_failure(run, monkeypatch):
    run(update=True)

    def boom(doc, cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(extract_mod, "extract", boom)
    res = run()
    assert res.metrics["pipeline_errors"] > 0
    assert res.exit_code == 1


def test_missing_baseline_section_is_exit_2(run, tmp_path):
    res = run()
    assert res.exit_code == 2
    assert not (tmp_path / "baseline.json").exists()


def test_update_writes_only_selected_section(run, tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"holdout": {"f1": 0.5}}), encoding="utf-8")
    res = run(update=True)
    assert res.exit_code == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["holdout"] == {"f1": 0.5}
    assert "dev" in data
    assert list(data) == ["dev", "holdout"] or set(data) == {"dev", "holdout"}


def test_unknown_case_is_usage_error(run):
    with pytest.raises(ValueError):
        run(cases=["nie_ma_takiej_sprawy"])


def test_compare_epsilon_and_new_metrics():
    base = {
        "f1": 0.5,
        "precision": 0.5,
        "recall": 0.5,
        "f1_by_type": {"a": 0.5},
        "f1_by_field": {"a.x": 0.5},
        "neg_correct": 1,
        "neg_total": 1,
        "schema_errors": 0,
        "classification_errors": 0,
        "pipeline_errors": 0,
    }
    cur = json.loads(json.dumps(base))
    rows, reg = gate.compare_metrics(base, cur, 0.0)
    assert reg == []
    # spadek rowny tolerancji przechodzi, wiekszy nie
    cur["f1"] = 0.4
    assert gate.compare_metrics(base, cur, 0.1)[1] == []
    assert gate.compare_metrics(base, cur, 0.0999)[1] != []
    # spadek o 1e-12 (szum) jest pomijany, o 1e-6 nie
    cur["f1"] = 0.5 - 1e-12
    assert gate.compare_metrics(base, cur, 0.0)[1] == []
    cur["f1"] = 0.5 - 1e-6
    assert gate.compare_metrics(base, cur, 0.0)[1] != []
    # nowe pole/typ nie jest bledem, a znika z baseline'u tez nie
    cur = json.loads(json.dumps(base))
    cur["f1_by_field"]["b.y"] = 0.0
    cur["f1_by_type"]["b"] = 0.0
    rows, reg = gate.compare_metrics(base, cur, 0.0)
    assert reg == []
    assert any("b.y" in r.name and r.flag == "new" for r in rows)
    # wzrost liczby bledow klasyfikacji = regresja
    cur = json.loads(json.dumps(base))
    cur["classification_errors"] = 1
    assert gate.compare_metrics(base, cur, 0.0)[1]
    # spadek neg_correct = regresja
    cur = json.loads(json.dumps(base))
    cur["neg_correct"] = 0
    assert gate.compare_metrics(base, cur, 0.0)[1]
