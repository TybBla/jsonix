"""Porównanie wariantów w scripts/bench_hybryda.py (bez uruchamiania pipeline'u)."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bench_hybryda", Path(__file__).resolve().parent.parent / "scripts" / "bench_hybryda.py"
)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def test_field_diff_reports_only_changed_fields():
    base = {"a": {"tp": 1, "tn": 2, "fp": 0, "fn": 0}, "b": {"tp": 3, "tn": 0, "fp": 0, "fn": 1}}
    hyb = {"a": {"tp": 1, "tn": 1, "fp": 1, "fn": 0}, "b": {"tp": 3, "tn": 0, "fp": 0, "fn": 1}}
    d = bench.field_diff(base, hyb)
    assert [x["pole"] for x in d] == ["a"]
    assert d[0]["delta"] == {"tp": 0, "tn": -1, "fp": 1, "fn": 0}


def test_markdown_row_has_llm_columns_only_for_hybrid():
    row = {"tp": 1, "tn": 1, "fp": 0, "fn": 0, "f1": 1.0, "precision": 1.0, "recall": 1.0}
    md = bench.to_markdown(
        [
            {"section": "dev@tekst", "variant": "reguly", "total": row, "llm": None, "seconds": 1.0},
            {
                "section": "dev@tekst",
                "variant": "hybryda",
                "total": row,
                "llm": {"docs_asked": 7},
                "seconds": 9.0,
            },
        ]
    )
    assert "| dev@tekst (w próbie (strojenie)) | reguly | 1,0000 |" in md and "| 7 |" in md


def test_train_pdf_maps_gate_workdir_to_train(tmp_path):
    work = tmp_path / "odw2json-gate-dev-x" / "in" / "skany" / "przelewy" / "0001" / "przelew.pdf"
    assert bench.train_pdf(work, Path("T")) == Path("T") / "skany" / "przelewy" / "0001" / "przelew.pdf"
    assert bench.train_pdf(Path("x/y.pdf"), Path("T")) is None


def test_gt_leaf_and_judge_fill():
    gt = {"Odwolujacy": [{"nip": "123", "nazwa": "ABC Sp. z o.o."}], "X": {"a": None}}
    assert bench.gt_leaf(gt, "Odwolujacy[0].nip") == (True, "123")
    assert bench.gt_leaf(gt, "Odwolujacy[1].nip") == (False, None)
    assert bench.judge_fill("123", "123", "Odwolujacy[0].nip") == "poprawne"
    assert bench.judge_fill("124", "123", "Odwolujacy[0].nip") == "bledne"
    assert bench.judge_fill("124", None, "X.a") == "zmyslone"
    assert bench.judge_fill("ABC Sp. z o.o", "ABC Sp. z o.o.", "Odwolujacy[0].nazwa") == "poprawne"  # fuzzy
