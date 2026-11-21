import json
from pathlib import Path

from eval.score import Counts, ScoreConfig, score_dirs, score_pair


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
    c = score_pair({"nazwa": "STRABAG Sp. z o.o."}, {"nazwa": "STRABAG sp. z o.o."})
    assert c.tp == 1 and c.fp == 0
    c = score_pair({"nip": "STRABAG Sp. z o.o."}, {"nip": "STRABAG sp. z o.o."})
    assert c.tp == 0 and c.fp == 1  # exact field: case-sensitive


def test_whitespace_normalized_and_numbers():
    assert score_pair({"a": "  x   y "}, {"a": "x y"}).tp == 1
    assert score_pair({"k": 10000}, {"k": 10000.0}).tp == 1
    assert score_pair({"n": "85120133547"}, {"n": 85120133547}).fp == 1
    assert score_pair({"n": "85120133547"}, {"n": 85120133547},
                      ScoreConfig(lenient_types=True)).tp == 1


def test_list_extra_element_and_reorder():
    gt = {"L": [{"nip": "1", "nazwa": "Alfa"}, {"nip": "2", "nazwa": "Beta"}]}
    pred = {"L": [{"nip": "2", "nazwa": "Beta"}, {"nip": "1", "nazwa": "Alfa"},
                  {"nip": "3", "nazwa": "Gamma"}]}
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
    _w(gt / "p1" / "extra.pdf", {})            # negative, no pred
    _w(gt / "negatywne" / "neg1.pdf", {})      # negative, pred wrong
    _w(gt / "negatywne" / "neg2.pdf", {})      # negative, empty pred file
    _w(pr / "p1" / "odwolanie.json", {"a": "x", "b": None})
    _w(pr / "p1" / "potwierdzenie_przelewu.json", {"kwota": 10})
    # pelnomocnictwo missing entirely
    _w(pr / "negatywne" / "neg1.json", {"a": "junk"})
    _w(pr / "negatywne" / "neg2.json", None)
    rep = score_dirs(pr, gt)
    assert rep.by_type["odwolanie"].tp == 1 and rep.by_type["odwolanie"].tn == 1
    assert rep.by_type["przelew"].tp == 1
    assert rep.by_type["pelnomocnictwo"].fn == 1
    assert rep.by_type["negative"].fp == 1
    assert rep.neg_total == 3 and rep.neg_correct == 2
    assert rep.total.tp == 2 and rep.total.fn == 1 and rep.total.fp == 1
    assert len(rep.docs) == 6
    json.dumps(rep.to_dict())
