"""Integracja: typ wzorcowy „przelew” (config/doctypes/przelew.yaml) na PDF-ach z warstwą tekstu (dev)."""

from __future__ import annotations

import json

import pytest

from odw2json import ingest
from odw2json.config_loader import load_registry
from odw2json.extract import extract
from odw2json.splits import load_splits

NO_OCR = {"ocr": {"enabled": False}}
# różne układy druków: etykiety w liniach, kropki prowadzące, pismo banku, bez etykiet rachunków
CASES = [
    "przyklad_01",
    "przyklad_02",
    "przyklad_03",
    "przyklad_05",
    "przyklad_07",
    "przyklad_15",
    "przyklad_24",
]


def _run(train_dir, case: str):
    pdf = train_dir / case / "potwierdzenie_przelewu.pdf"
    doc = ingest.load(pdf, cfg=NO_OCR)
    res = extract(doc, load_registry()["przelew"])
    gt = json.loads((train_dir / case / "przelew.json").read_text(encoding="utf-8"))
    return doc, res, gt


@pytest.mark.parametrize("case", CASES)
def test_przelew_matches_ground_truth(train_dir, case):
    _, res, gt = _run(train_dir, case)
    assert res.data == gt


def test_przelew_trace_has_page_and_snippet(train_dir):
    _, res, _ = _run(train_dir, "przyklad_07")
    keys = ("data_operacji", "kwota", "na_rachunek", "numer_transakcji", "tytul", "z_rachunku")
    assert {t.path for t in res.trace} == {f"przelew_bankowy.{k}" for k in keys}
    for t in res.trace:
        assert t.page == 0 and t.source_snippet


def test_przelew_dev_accuracy_per_field(train_dir):
    cases = [c for c in load_splits()["dev"] if not c.startswith("skany/")]
    cases = [c for c in cases if (train_dir / c / "potwierdzenie_przelewu.pdf").exists()]
    assert len(cases) >= 20
    hits: dict[str, int] = {}
    misses: list[str] = []
    for case in cases:
        _, res, gt = _run(train_dir, case)
        for k, v in gt["przelew_bankowy"].items():
            ok = res.data["przelew_bankowy"][k] == v
            hits[k] = hits.get(k, 0) + ok
            if not ok:
                misses.append(f"{case}.{k}: {res.data['przelew_bankowy'][k]!r} != {v!r}")
    for k, n in hits.items():
        assert n / len(cases) >= 0.95, (k, misses)
