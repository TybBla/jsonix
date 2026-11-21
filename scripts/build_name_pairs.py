"""Buduje pary (forma imienia i nazwiska w tekście PDF -> GT w mianowniku) z data/train.

Dla każdego `imie_nazwisko` z GT (pełnomocnicy, podpisujący, pełnomocnik odwołującego)
szuka w tekście PDF wystąpień „Imię Nazwisko” dopasowanych po rdzeniu (pierwsze litery
imienia i nazwiska) i zapisuje unikalne pary do tests/fixtures/names_pairs.json.

Uruchomienie: python scripts/build_name_pairs.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from odw2json.ingest import load  # noqa: E402

TRAIN = ROOT / "data" / "train"
OUT = ROOT / "tests" / "fixtures" / "names_pairs.json"
DOCS = {"odwolanie": "odwolanie", "pelnomocnictwo": "pelnomocnictwo"}

_TITLE = (
    r"(?:(?:adw\.|adwokat(?:a|owi|em)?|r\.\s?pr\.|radc(?:a|y|ę|zie|ą)\s+prawn(?:y|ego|emu|ym)"
    r"|mec\.|dr|Pan(?:a|u|em|i|ią)?)\s+)*"
)


def _names(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "imie_nazwisko" and isinstance(v, str) and v.strip():
                out.add(v.strip())
            else:
                _names(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _names(v, out)


def _stem(word: str) -> str:
    return word[: max(3, min(4, len(word) - 1))]


def find_forms(text: str, gt: str) -> set[str]:
    parts = gt.split()
    if len(parts) < 2:
        return set()
    first, last = parts[0], " ".join(parts[1:])
    last_parts = last.split("-")
    last_rx = r"-".join(re.escape(_stem(p)) + r"[a-ząćęłńóśźż]*" for p in last_parts)
    rx = re.compile(
        r"(?<![\wąćęłńóśźż])"
        + _TITLE
        + re.escape(_stem(first))
        + r"[a-ząćęłńóśźż]*\s+"
        + last_rx
        + r"(?![\wąćęłńóśźż])"
    )
    return {re.sub(r"\s+", " ", m.group(0)) for m in rx.finditer(text)}


def case_of(form: str, gt: str) -> str:
    """Zgrubna etykieta przypadku z końcówki imienia (do statystyki)."""
    f = form.split()[-2] if len(form.split()) >= 2 else form
    g = gt.split()[0]
    if f == g:
        return "mianownik"
    if f.endswith(("owi", "e", "u")) and not f.endswith("ę"):
        return "celownik"  # Janowi, Annie, Tomaszowi; uwaga: Ani(e)
    if f.endswith(("em", "ą")):
        return "narzędnik"
    if f.endswith("ę"):
        return "biernik"
    if f.endswith(("a", "y", "i")):
        return "dopełniacz"
    return "inny"


def main() -> None:
    splits = yaml.safe_load((ROOT / "data" / "splits.yaml").read_text(encoding="utf-8"))
    split_of = {c: s for s in ("dev", "holdout") for c in splits.get(s, [])}
    pairs: dict[tuple[str, str], dict] = {}
    missing = 0
    for case_dir in sorted(TRAIN.glob("przyklad_*")):
        for stem in DOCS:
            pdf, gt_json = case_dir / f"{stem}.pdf", case_dir / f"{stem}.json"
            if not (pdf.exists() and gt_json.exists()):
                continue
            names: set[str] = set()
            _names(json.loads(gt_json.read_text(encoding="utf-8")), names)
            if not names:
                continue
            text = load(pdf, cfg={"ocr": {"enabled": False}}).text
            for gt in sorted(names):
                forms = find_forms(text, gt)
                if not forms:
                    missing += 1
                for form in forms:
                    key = (form, gt)
                    if key not in pairs:
                        pairs[key] = {
                            "text": form,
                            "gt": gt,
                            "case": case_of(form, gt),
                            "sprawa": case_dir.name,
                            "doc": stem,
                            "split": split_of.get(case_dir.name, "dev"),
                        }
    items = sorted(pairs.values(), key=lambda p: (p["sprawa"], p["doc"], p["gt"], p["text"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"par: {len(items)}, GT bez dopasowania w tekście: {missing}")
    for split in ("dev", "holdout"):
        c = Counter(p["case"] for p in items if p["split"] == split)
        print(split, dict(c))


if __name__ == "__main__":
    main()
