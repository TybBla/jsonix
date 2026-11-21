"""Podział spraw na dev/holdout (deterministyczny, po hashu nazwy sprawy)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from odw2json.config_loader import ROOT_DIR

SPLIT_SALT = "odw2json-split-v1"
SPLITS_PATH = ROOT_DIR / "data" / "splits.yaml"
SPLIT_KEYS = ("dev", "holdout", "negatives")


def assign_split(case: str) -> str:
    """Zwraca 'holdout' dla co czwartej sprawy (wg hashu), inaczej 'dev'."""
    digest = hashlib.sha256(f"{SPLIT_SALT}:{case}".encode()).hexdigest()
    return "holdout" if int(digest, 16) % 4 == 0 else "dev"


def load_splits(path: Path = SPLITS_PATH) -> dict[str, list[str]]:
    """Wczytuje data/splits.yaml; zwraca klucze dev, holdout, negatives."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {key: list(data.get(key) or []) for key in SPLIT_KEYS}
