"""Testy deterministycznego podziału dev/holdout."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from odw2json.config_loader import ROOT_DIR
from odw2json.splits import assign_split, load_splits

ROOT = ROOT_DIR
TRAIN = ROOT / "data" / "train"
SPLITS_FILE = ROOT / "data" / "splits.yaml"
SCRIPT = ROOT / "scripts" / "make_splits.py"


def _cases() -> list[str]:
    return sorted(p.name for p in TRAIN.iterdir() if p.is_dir() and p.name.startswith("przyklad_"))


def test_every_case_in_exactly_one_split():
    splits = load_splits()
    dev, holdout = set(splits["dev"]), set(splits["holdout"])
    assert not dev & holdout
    assert dev | holdout == set(_cases())


def test_holdout_size_in_range():
    holdout = load_splits()["holdout"]
    assert 10 <= len(holdout) <= 20, f"holdout ma {len(holdout)} spraw"


def test_script_is_deterministic(tmp_path: Path):
    before = SPLITS_FILE.read_bytes()
    for _ in range(2):
        subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=ROOT)
    after_first = SPLITS_FILE.read_bytes()
    subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=ROOT)
    assert SPLITS_FILE.read_bytes() == after_first == before


def test_assignment_stable_when_new_case_added():
    cases = _cases()
    before = {c: assign_split(c) for c in cases}
    assign_split("przyklad_999")
    after = {c: assign_split(c) for c in cases}
    assert before == after


def test_negatives_list():
    assert load_splits()["negatives"] == ["negatywne"]
