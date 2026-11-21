"""Generuje data/splits.yaml (dev/holdout wg assign_split).

Regeneracja: python scripts/make_splits.py
Plik jest deterministyczny: ponowne uruchomienie daje identyczne bajty.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from odw2json.splits import assign_split  # noqa: E402

TRAIN = ROOT / "data" / "train"
OUT = ROOT / "data" / "splits.yaml"
NEGATIVES = ["negatywne"]

HEADER = (
    "# Podział danych treningowych na dev i holdout (generowany, nie edytować ręcznie).\n"
    "# Przydział: sha256('odw2json-split-v1:<sprawa>') % 4 == 0 -> holdout, inaczej dev.\n"
    "# Regeneracja: python scripts/make_splits.py\n"
)


def main() -> None:
    cases = sorted(p.name for p in TRAIN.iterdir() if p.is_dir() and p.name.startswith("przyklad_"))
    dev = [c for c in cases if assign_split(c) == "dev"]
    holdout = [c for c in cases if assign_split(c) == "holdout"]
    body = yaml.safe_dump(
        {"dev": dev, "holdout": holdout, "negatives": NEGATIVES},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    OUT.write_text(HEADER + body, encoding="utf-8", newline="\n")
    print(f"dev={len(dev)} holdout={len(holdout)} -> {OUT}")


if __name__ == "__main__":
    main()
