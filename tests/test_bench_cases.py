"""Pomiar czasu na dokument/sprawę (scripts/bench_cases.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("bench_cases", ROOT / "scripts" / "bench_cases.py")
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


def test_summary_splits_text_and_ocr_and_sums_cases():
    docs = [
        {
            "pdf": "data/train/a/x.pdf",
            "ocr": False,
            "ingest_s": 0.1,
            "classify_s": 0.01,
            "extract_s": 0.0,
            "total_s": 0.11,
        },
        {
            "pdf": "data/train/a/y.pdf",
            "ocr": True,
            "ingest_s": 3.0,
            "classify_s": 0.01,
            "extract_s": 0.0,
            "total_s": 3.01,
        },
        {
            "pdf": "data/train/b/z.pdf",
            "ocr": False,
            "ingest_s": 0.2,
            "classify_s": 0.0,
            "extract_s": 0.0,
            "total_s": 0.2,
        },
    ]
    s = bc.summarize(docs, [Path("a"), Path("b")])
    assert s["dokumenty"]["n"] == 3 and s["dokumenty_ocr"]["n"] == 1 and s["dokumenty_tekst"]["n"] == 2
    assert abs(s["sprawy"]["max"] - 3.12) < 1e-9, "sprawa = suma jej dokumentów"
    assert s["etapy_suma_s"]["ingest"] == 3.3


def test_time_document_on_text_pdf(tmp_path):
    pdf = ROOT / "data" / "train" / "przyklad_01" / "pelnomocnictwo.pdf"
    d = bc.time_document(str(pdf), str(tmp_path))
    assert d["doc_type"] == "pelnomocnictwo" and d["ocr"] is False
    assert d["total_s"] >= d["ingest_s"] > 0
