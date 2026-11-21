"""Testy deterministycznego podziału dev/holdout."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from odw2json.config_loader import ROOT_DIR
from odw2json.splits import assign_split, load_splits

ROOT = ROOT_DIR
TRAIN = ROOT / "data" / "train"
SKANY = TRAIN / "skany"
SPLITS_FILE = ROOT / "data" / "splits.yaml"
SCRIPT = ROOT / "scripts" / "make_splits.py"

# Przydział przykladow sprzed zmiany (zamrozony z data/splits.yaml przed T1).
FROZEN_PRZYKLAD_DEV = [
    "przyklad_01",
    "przyklad_02",
    "przyklad_03",
    "przyklad_04",
    "przyklad_05",
    "przyklad_07",
    "przyklad_08",
    "przyklad_09",
    "przyklad_12",
    "przyklad_14",
    "przyklad_15",
    "przyklad_16",
    "przyklad_17",
    "przyklad_18",
    "przyklad_19",
    "przyklad_21",
    "przyklad_22",
    "przyklad_23",
    "przyklad_24",
    "przyklad_26",
    "przyklad_27",
    "przyklad_28",
    "przyklad_29",
    "przyklad_30",
    "przyklad_32",
    "przyklad_35",
    "przyklad_36",
    "przyklad_37",
    "przyklad_39",
    "przyklad_42",
    "przyklad_43",
    "przyklad_44",
    "przyklad_45",
    "przyklad_46",
    "przyklad_47",
    "przyklad_48",
    "przyklad_49",
    "przyklad_50",
    "przyklad_52",
    "przyklad_53",
    "przyklad_54",
    "przyklad_55",
    "przyklad_56",
    "przyklad_57",
    "przyklad_58",
    "przyklad_60",
]
FROZEN_PRZYKLAD_HOLDOUT = [
    "przyklad_06",
    "przyklad_10",
    "przyklad_11",
    "przyklad_13",
    "przyklad_20",
    "przyklad_25",
    "przyklad_31",
    "przyklad_33",
    "przyklad_34",
    "przyklad_38",
    "przyklad_40",
    "przyklad_41",
    "przyklad_51",
    "przyklad_59",
]


def _cases() -> list[str]:
    return sorted(p.name for p in TRAIN.iterdir() if p.is_dir() and p.name.startswith("przyklad_"))


def _scan_cases() -> list[str]:
    return sorted(
        f"skany/{typ.name}/{sprawa.name}"
        for typ in SKANY.iterdir()
        if typ.is_dir()
        for sprawa in typ.iterdir()
        if sprawa.is_dir()
    )


def test_scan_cases_discovered():
    assert len(_scan_cases()) == 30


def test_every_case_in_exactly_one_split():
    splits = load_splits()
    dev, holdout = set(splits["dev"]), set(splits["holdout"])
    assert not dev & holdout
    assert dev | holdout == set(_cases()) | set(_scan_cases())


def test_every_scan_case_in_exactly_one_split():
    splits = load_splits()
    dev, holdout = set(splits["dev"]), set(splits["holdout"])
    for case in _scan_cases():
        assert (case in dev) != (case in holdout), f"{case} nie jest w dokladnie jednym splicie"


def test_scan_ids_loaded_from_splits():
    splits = load_splits()
    loaded = {c for c in splits["dev"] + splits["holdout"] if c.startswith("skany/")}
    assert loaded == set(_scan_cases())


def test_przyklad_assignment_unchanged():
    splits = load_splits()
    assert sorted(c for c in splits["dev"] if c.startswith("przyklad_")) == FROZEN_PRZYKLAD_DEV
    assert sorted(c for c in splits["holdout"] if c.startswith("przyklad_")) == FROZEN_PRZYKLAD_HOLDOUT


def test_przyklad_assignment_matches_hash():
    for case in FROZEN_PRZYKLAD_DEV:
        assert assign_split(case) == "dev"
    for case in FROZEN_PRZYKLAD_HOLDOUT:
        assert assign_split(case) == "holdout"


def test_holdout_size_in_range():
    holdout = [c for c in load_splits()["holdout"] if c.startswith("przyklad_")]
    assert 10 <= len(holdout) <= 20, f"holdout ma {len(holdout)} spraw"


def test_script_is_deterministic(tmp_path: Path):
    outs = []
    for i in range(2):
        out = tmp_path / f"splits{i}.yaml"
        subprocess.run([sys.executable, str(SCRIPT), "--out", str(out)], check=True, cwd=ROOT)
        outs.append(out.read_bytes())
    assert outs[0] == outs[1] == SPLITS_FILE.read_bytes()


def test_assignment_stable_when_new_case_added():
    cases = _cases()
    before = {c: assign_split(c) for c in cases}
    assign_split("przyklad_999")
    after = {c: assign_split(c) for c in cases}
    assert before == after


def test_negatives_list():
    assert load_splits()["negatives"] == ["negatywne"]
