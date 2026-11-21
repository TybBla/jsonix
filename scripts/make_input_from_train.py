"""Kopiuje PDF-y z data/train/<case>/ do input/<case>/ (bez JSON-ów GT) — do lokalnej ewaluacji.

Użycie: python scripts/make_input_from_train.py [--src data/train] [--dst input] [--clean]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data" / "train"))
    ap.add_argument("--dst", default=str(ROOT / "input"))
    ap.add_argument("--clean", action="store_true", help="usuń poprzednią zawartość dst (poza .gitkeep)")
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    if a.clean and dst.exists():
        for p in dst.iterdir():
            if p.name != ".gitkeep":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
    n = 0
    for pdf in src.rglob("*.pdf"):
        t = dst / pdf.relative_to(src)
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, t)
        n += 1
    print(f"Skopiowano {n} PDF-ów do {dst}")


if __name__ == "__main__":
    main()
