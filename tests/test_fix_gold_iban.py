"""Poprawka GT: prefiks „PL” przy numerze rachunku tylko, gdy ma go dokument (scripts/fix_gold_iban.py)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("fix_gold_iban", ROOT / "scripts" / "fix_gold_iban.py")
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

NUM = "68438223049992295262834736"


def test_prefix_detected_with_and_without_spaces():
    assert fx.has_pl_prefix(f"Rachunek: PL{NUM}", NUM) is True
    assert fx.has_pl_prefix("PL 68 4382 2304 9992 2952 6283 4736", NUM) is True
    assert fx.has_pl_prefix("nr 68 4382 2304 9992 2952 6283 4736", NUM) is False
    assert fx.has_pl_prefix("inny numer 11 1111 1111", NUM) is None
    assert fx.has_pl_prefix(f"9{NUM}", NUM) is None, "nie fragment dłuższego ciągu cyfr"


def test_plan_and_apply_on_copy(tmp_path):
    case = tmp_path / "przyklad_01"
    case.mkdir()
    src = ROOT / "data" / "train" / "przyklad_01"
    for name in ("potwierdzenie_przelewu.pdf", "przelew.json"):
        (case / name).write_bytes((src / name).read_bytes())
    changes, missing = fx.plan(tmp_path)
    got = {(f, new) for _gt, f, _old, new in changes}
    assert ("na_rachunek", "PL" + NUM) in got and ("z_rachunku", "PL05470680287581539721455024") in got
    assert not missing
    fx.apply(changes)
    data = json.loads((case / "przelew.json").read_text(encoding="utf-8"))
    assert data["przelew_bankowy"]["na_rachunek"] == "PL" + NUM
    assert list(data["przelew_bankowy"]) == list(json.loads((src / "przelew.json").read_text(encoding="utf-8"))[
        "przelew_bankowy"
    ]), "kolejność kluczy bez zmian"
    assert fx.plan(tmp_path) == ([], []), "drugi przebieg niczego nie zmienia"
