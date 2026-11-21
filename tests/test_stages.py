from odw2json import classify, extract, ingest
from odw2json.config_loader import load_registry


def test_ingest_reads_text(train_dir):
    doc = ingest.load(train_dir / "przyklad_01" / "odwolanie.pdf")
    assert "Zamawiaj" in doc.text
    assert len(doc.pages) >= 1


def test_classify_positive_examples(train_dir):
    reg = load_registry()
    expected = {
        "odwolanie.pdf": "odwolanie",
        "pelnomocnictwo.pdf": "pelnomocnictwo",
        "potwierdzenie_przelewu.pdf": "przelew",
    }
    for name, typ in expected.items():
        c = classify.classify(ingest.load(train_dir / "przyklad_01" / name), reg)
        assert c.doc_type == typ, (name, c)


def test_classify_ted_notice_is_unknown(train_dir):
    reg = load_registry()
    pdf = next((train_dir / "przyklad_10").glob("2025-OJS107-*.pdf"))
    assert classify.classify(ingest.load(pdf), reg).doc_type is None


def test_extract_baseline_returns_template_with_derived():
    cfg = load_registry()["odwolanie"]
    res = extract.extract(ingest_stub(), cfg)
    assert res.doc_type == "odwolanie"
    assert set(res.data) == set(cfg.template())


def ingest_stub():
    from pathlib import Path

    from odw2json.contracts import Document

    return Document(path=Path("x.pdf"), text="", pages=[""])


def test_derived_lookup_fills_opis():
    from odw2json.extract import apply_derived

    cfg = load_registry()["odwolanie"]
    data = cfg.template()
    data["OdwolanieKIO"]["czynnosc_powod_id"] = 9
    trace = apply_derived(data, cfg)
    assert data["OdwolanieKIO"]["czynnosc_opis"] == "Decyzja o unieważnieniu postępowania"
    assert trace and trace[0].method == "derived"
