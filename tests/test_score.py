import json
from pathlib import Path

import pytest

from eval.score import (
    Counts,
    ScoreConfig,
    doc_source,
    gt_path_for_pdf,
    has_text_layer,
    infer_doc_type,
    score_dirs,
    score_pair,
)
from odw2json.config_loader import ROOT_DIR, load_registry

TRAIN = ROOT_DIR / "data" / "train"
SCAN_PDF = TRAIN / "skany" / "potwierdzenia" / "0001" / "0001.pdf"


def test_identical_dicts():
    d = {"a": "x", "b": {"c": 1, "d": 2.5}, "e": [{"nazwa": "N", "nip": "1"}]}
    c = score_pair(d, d)
    assert c.fp == 0 and c.fn == 0 and c.tp == 5


def test_null_null_is_tn():
    c = score_pair({"a": None, "b": "x"}, {"a": None, "b": "x"})
    assert c.tn == 1 and c.fp == 0 and c.tp == 1


def test_pred_value_gt_null_is_fp():
    c = score_pair({"a": "x"}, {"a": None})
    assert (c.tp, c.fp, c.fn, c.tn) == (0, 1, 0, 0)


def test_pred_null_gt_value_is_fn():
    c = score_pair({"a": None}, {"a": "x"})
    assert (c.tp, c.fp, c.fn) == (0, 0, 1)


def test_missing_key_equals_null():
    c = score_pair({}, {"a": "x", "b": None})
    assert (c.fn, c.tn) == (1, 1)


def test_wrong_value_is_fp_not_fn():
    c = score_pair({"a": "x"}, {"a": "y"})
    assert (c.tp, c.fp, c.fn) == (0, 1, 0)


def test_fuzzy_name_match():
    p = {"Odwolujacy": [{"nazwa": "STRABAG Sp. z o.o."}]}
    g = {"Odwolujacy": [{"nazwa": "STRABAG sp. z o.o."}]}
    c = score_pair(p, g)
    assert c.tp == 1 and c.fp == 0
    c = score_pair({"nip": "STRABAG Sp. z o.o."}, {"nip": "STRABAG sp. z o.o."})
    assert c.tp == 0 and c.fp == 1  # exact field: case-sensitive


def test_fuzzy_only_on_uzp_long_string_fields():
    # wg UZP (Discord 13:26): nazwa pełnomocnika (firma), tytuł przelewu,
    # nazwa Odwołującego/Zamawiającego, tytuł zamówienia
    fuzzy_ok = [
        (
            {"Zamawiajacy": [{"nazwa": "Gmina Miasto Łódź"}]},
            {"Zamawiajacy": [{"nazwa": "Gmina Miasto Lódź"}]},
        ),
        (
            {"Odwolujacy": [{"pelnomocnik": {"nazwa": "Kancelaria Adwokacka Sp. z o.o."}}]},
            {"Odwolujacy": [{"pelnomocnik": {"nazwa": "Kancelaria Adwokacka sp. z o.o."}}]},
        ),
        (
            {"ZamowieniePubliczne": {"tytul": "Dostawa sprzętu IT."}},
            {"ZamowieniePubliczne": {"tytul": "Dostawa sprzętu IT"}},
        ),
        (
            {"przelew_bankowy": {"tytul": "WPIS OD ODW. ZP.1.2025"}},
            {"przelew_bankowy": {"tytul": "WPIS OD ODW ZP.1.2025"}},
        ),
    ]
    for p, g in fuzzy_ok:
        assert score_pair(p, g).tp == 1, p
    # pola dokładne mimo podobnej nazwy klucza
    exact = [
        (
            {"mocodawca": [{"data": {"nazwa": "FAMBUD Sp. z o.o."}}]},
            {"mocodawca": [{"data": {"nazwa": "FAMBUD sp. z o.o."}}]},
        ),
        (
            {"pelnomocnicy": [{"imie_nazwisko": "Jan Kowalskiego"}]},
            {"pelnomocnicy": [{"imie_nazwisko": "Jan Kowalski"}]},
        ),
        (
            {"OdwolanieKIO": {"czynnosc_opis": "Odpowiedzi/wyjaśnienia do SWZ"}},
            {"OdwolanieKIO": {"czynnosc_opis": "Odpowiedzi i wyjaśnienia do SWZ"}},
        ),
    ]
    for p, g in exact:
        c = score_pair(p, g)
        assert c.tp == 0 and c.fp == 1, p


def test_whitespace_normalized_and_numbers():
    assert score_pair({"a": "  x   y "}, {"a": "x y"}).tp == 1
    assert score_pair({"k": 10000}, {"k": 10000.0}).tp == 1
    assert score_pair({"n": "85120133547"}, {"n": 85120133547}).fp == 1
    assert score_pair({"n": "85120133547"}, {"n": 85120133547}, ScoreConfig(lenient_types=True)).tp == 1


def test_list_extra_element_and_reorder():
    gt = {"L": [{"nip": "1", "nazwa": "Alfa"}, {"nip": "2", "nazwa": "Beta"}]}
    pred = {
        "L": [{"nip": "2", "nazwa": "Beta"}, {"nip": "1", "nazwa": "Alfa"}, {"nip": "3", "nazwa": "Gamma"}]
    }
    c = score_pair(pred, gt)
    assert c.tp == 4 and c.fp == 2 and c.fn == 0
    assert c.fields["L[].nip"].tp == 2 and c.fields["L[].nip"].fp == 1


def test_list_missing_element_fn():
    gt = {"L": [{"nip": "1", "x": None}, {"nip": "2", "x": None}]}
    pred = {"L": [{"nip": "1", "x": None}]}
    c = score_pair(pred, gt)
    assert c.tp == 1 and c.fn == 1 and c.tn == 2


def test_pred_none_vs_gt():
    c = score_pair(None, {"a": "x", "b": None, "c": {"d": 1}})
    assert (c.fn, c.tn, c.tp, c.fp) == (2, 1, 0, 0)


def test_pred_vs_gt_none_negative():
    c = score_pair({"a": "x", "b": None, "c": 2}, None)
    assert c.fp == 2 and c.tp == 0 and c.fn == 0


def test_metrics():
    c = Counts(tp=2, fp=1, fn=1, tn=5)
    assert c.precision == 2 / 3 and c.recall == 2 / 3
    assert c.f1 == 4 / 6
    assert (c + c).tp == 4
    assert Counts().f1 == 0.0


def _w(p: Path, obj=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("" if obj is None else json.dumps(obj), encoding="utf-8")


def test_score_dirs(tmp_path):
    gt, pr = tmp_path / "gt", tmp_path / "pred"
    for stem in ("odwolanie", "pelnomocnictwo", "potwierdzenie_przelewu"):
        _w(gt / "p1" / f"{stem}.pdf", {})
    _w(gt / "p1" / "odwolanie.json", {"a": "x", "b": None})
    _w(gt / "p1" / "przelew.json", {"kwota": 10.0})
    _w(gt / "p1" / "pelnomocnictwo.json", {"c": "z"})
    _w(gt / "p1" / "extra.pdf", {})  # negative, no pred
    _w(gt / "negatywne" / "neg1.pdf", {})  # negative, pred wrong
    _w(gt / "negatywne" / "neg2.pdf", {})  # negative, empty pred file
    _w(gt / "negatywne" / "neg3.pdf", {})  # negative, pred {} (UZP: pusty JSON)
    _w(gt / "negatywne" / "neg4.pdf", {})  # negative, misclassified -> schema of nulls
    _w(pr / "p1" / "odwolanie.json", {"a": "x", "b": None})
    _w(pr / "p1" / "potwierdzenie_przelewu.json", {"kwota": 10})
    # pelnomocnictwo missing entirely
    _w(pr / "negatywne" / "neg1.json", {"a": "junk"})
    _w(pr / "negatywne" / "neg2.json", None)
    _w(pr / "negatywne" / "neg3.json", {})
    _w(pr / "negatywne" / "neg4.json", {"przelew_bankowy": {"kwota": None}})
    rep = score_dirs(pr, gt)
    assert rep.by_type["odwolanie"].tp == 1 and rep.by_type["odwolanie"].tn == 1
    assert rep.by_type["przelew"].tp == 1
    assert rep.by_type["pelnomocnictwo"].fn == 1
    assert rep.by_type["negative"].fp == 1
    assert rep.neg_total == 5 and rep.neg_correct == 3
    assert rep.total.tp == 2 and rep.total.fn == 1 and rep.total.fp == 1
    assert len(rep.docs) == 8
    json.dumps(rep.to_dict())


# ------------------------------------------------ E2b: skany, typ z kluczy GT, zrodlo


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def test_infer_doc_type_from_top_level_keys(registry):
    assert infer_doc_type({"przelew_bankowy": {"kwota": 1}}, registry) == "przelew"
    assert infer_doc_type({"mocodawca": [], "pelnomocnicy": []}, registry) == "pelnomocnictwo"
    odw = {"OdwolanieKIO": {}, "Odwolujacy": [], "Zamawiajacy": [], "ZamowieniePubliczne": {}}
    assert infer_doc_type(odw, registry) == "odwolanie"


def test_infer_doc_type_partial_unknown_and_ambiguous(registry):
    assert infer_doc_type({"Odwolujacy": [{"nazwa": "x"}]}, registry) == "odwolanie"  # podzbior kluczy
    assert infer_doc_type({}, registry) is None
    assert infer_doc_type({"a": "x"}, registry) is None
    assert infer_doc_type([1, 2], registry) is None
    assert infer_doc_type({"przelew_bankowy": {}, "mocodawca": []}, registry) is None  # remis

    class _T:
        def __init__(self, keys):
            self._k = keys

        def template(self):
            return dict.fromkeys(self._k)

    assert infer_doc_type({"x": 1}, {"a": _T("xy"), "b": _T("xz")}) is None


def test_gt_path_for_pdf_mapping_and_same_name(tmp_path):
    d = tmp_path / "przyklad_x"
    for name in ("odwolanie.pdf", "odwolanie.json", "potwierdzenie_przelewu.pdf", "przelew.json", "neg.pdf"):
        _w(d / name, {})
    assert gt_path_for_pdf(d / "odwolanie.pdf") == d / "odwolanie.json"
    assert gt_path_for_pdf(d / "potwierdzenie_przelewu.pdf") == d / "przelew.json"  # stary wyjatek
    assert gt_path_for_pdf(d / "neg.pdf") is None
    # X.json obok X.pdf ma pierwszenstwo przed mapowaniem
    _w(d / "potwierdzenie_przelewu.json", {})
    assert gt_path_for_pdf(d / "potwierdzenie_przelewu.pdf") == d / "potwierdzenie_przelewu.json"


def test_has_text_layer():
    assert has_text_layer(TRAIN / "przyklad_01" / "odwolanie.pdf") is True
    assert has_text_layer(SCAN_PDF) is False
    assert has_text_layer(TRAIN / "przyklad_01" / "nie_ma.pdf") is True  # nieczytelny != skan


def _nested_tree(tmp_path):
    gt, pr = tmp_path / "gt", tmp_path / "pred"
    rel = Path("skany") / "odwolania" / "0001"
    gt_doc = {"OdwolanieKIO": {"data": "2026-01-01"}, "Odwolujacy": [{"nazwa": "Alfa"}]}
    _w(gt / rel / "0001.pdf", {})
    _w(gt / rel / "0001.json", gt_doc)
    _w(gt / "przyklad_01" / "odwolanie.pdf", {})
    _w(gt / "przyklad_01" / "odwolanie.json", gt_doc)
    _w(pr / rel / "0001.json", gt_doc)
    _w(pr / "przyklad_01" / "odwolanie.json", gt_doc)
    return gt, pr, rel


def test_score_dirs_nested_case_type_from_gt_keys(tmp_path):
    gt, pr, _ = _nested_tree(tmp_path)
    rep = score_dirs(pr, gt)
    by_doc = {d.rel: d for d in rep.docs}
    d = by_doc["skany/odwolania/0001/0001.pdf"]
    assert d.doc_type == "odwolanie"  # typ z kluczy GT, nie z nazwy pliku "0001"
    assert d.pred_missing is False and d.counts.fp == 0 and d.counts.fn == 0
    assert set(rep.by_type) == {"odwolanie"}
    assert d.to_dict()["source"] == "tekst"  # brak trace -> tekst


def test_score_dirs_source_from_trace(tmp_path):
    gt, pr, rel = _nested_tree(tmp_path)
    _w(pr / ".trace" / rel / "0001.trace.json", {"ocr_used": True, "trace": []})
    _w(pr / ".trace" / "przyklad_01" / "odwolanie.trace.json", {"ocr_used": False})
    rep = score_dirs(pr, gt)
    srcs = {d.rel: d.source for d in rep.docs}
    assert srcs == {"skany/odwolania/0001/0001.pdf": "skan", "przyklad_01/odwolanie.pdf": "tekst"}
    assert set(rep.by_source) == {"tekst", "skan"}
    assert rep.by_source["skan"].tp == rep.by_source["tekst"].tp > 0
    assert set(rep.by_type_source) == {"odwolanie/tekst", "odwolanie/skan"}
    assert (rep.by_source["skan"] + rep.by_source["tekst"]).tp == rep.total.tp
    assert rep.docs_by_source == {"tekst": 1, "skan": 1}
    out = rep.to_dict()
    assert out["by_source"]["skan"]["tp"] == rep.by_source["skan"].tp
    assert "odwolanie/skan" in out["by_type_source"]
    json.dumps(out)


def test_score_dirs_sources_override_beats_trace(tmp_path):
    gt, pr, rel = _nested_tree(tmp_path)
    _w(pr / ".trace" / rel / "0001.trace.json", {"ocr_used": False})
    rep = score_dirs(pr, gt, sources={"skany/odwolania/0001/0001.pdf": "skan"})
    assert {d.rel: d.source for d in rep.docs}["skany/odwolania/0001/0001.pdf"] == "skan"


def test_doc_source_edge_cases(tmp_path):
    assert doc_source(tmp_path, "a/b.pdf") == "tekst"  # brak trace
    t = tmp_path / ".trace" / "a" / "b.trace.json"
    t.parent.mkdir(parents=True)
    t.write_text("{zepsute", encoding="utf-8")
    assert doc_source(tmp_path, "a/b.pdf") == "tekst"
    t.write_text(json.dumps({"ocr_used": True}), encoding="utf-8")
    assert doc_source(tmp_path, "a/b.pdf") == "skan"
    # kropka w nazwie: pipeline zapisuje a.b.trace.json
    t2 = tmp_path / ".trace" / "a.b.trace.json"
    t2.write_text(json.dumps({"ocr_used": True}), encoding="utf-8")
    assert doc_source(tmp_path, "a.b.pdf") == "skan"


def test_przyklad_only_behaviour_unchanged(tmp_path):
    """Sprawa klasyczna: typ = nazwa GT (jak dawniej), wszystko 'tekst'."""
    gt, pr = tmp_path / "gt", tmp_path / "pred"
    for stem in ("odwolanie", "pelnomocnictwo", "potwierdzenie_przelewu"):
        _w(gt / "p1" / f"{stem}.pdf", {})
    _w(gt / "p1" / "odwolanie.json", {"OdwolanieKIO": {"data": "2026-01-01"}})
    _w(gt / "p1" / "przelew.json", {"przelew_bankowy": {"kwota": 10.0}})
    _w(gt / "p1" / "pelnomocnictwo.json", {"mocodawca": [], "pelnomocnicy": []})
    _w(pr / "p1" / "odwolanie.json", {"OdwolanieKIO": {"data": "2026-01-01"}})
    _w(pr / "p1" / "potwierdzenie_przelewu.json", {"przelew_bankowy": {"kwota": 10}})
    rep = score_dirs(pr, gt)
    assert set(rep.by_type) == {"odwolanie", "przelew", "pelnomocnictwo"}
    assert set(rep.by_source) == {"tekst"}
    assert rep.by_source["tekst"] == rep.total
