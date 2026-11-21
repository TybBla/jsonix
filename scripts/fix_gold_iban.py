"""Poprawka danych wzorcowych: numer rachunku w potwierdzeniu przelewu z prefiksem „PL”, jeśli ma go dokument.

Ustalenie UZP (Discord 21.11.2026, 21:17, `docs/kryteria-uzp.md` pkt 5a): numer rachunku wpisujemy tak, jak jest
w dokumencie; brak „PL” w części wzorcowych JSON-ów to błąd, którego nie będzie w zbiorze oceniającym.

Dla każdego PDF-a z `data/train`, którego GT ma `przelew_bankowy`, sprawdza w tekście dokumentu (warstwa tekstu
albo OCR, przez `odw2json.ingest`), czy bezpośrednio przed cyframi numeru stoi „PL”. Jeśli tak, a GT nie ma
prefiksu — dopisuje „PL” (bez spacji, jak reszta GT). Numerów, których nie da się znaleźć w tekście, nie zmienia
(lista „bez zmian — nie znaleziono” w wyniku).

Użycie:
    python scripts/fix_gold_iban.py            # podgląd zmian (nic nie zapisuje)
    python scripts/fix_gold_iban.py --apply    # zapis poprawionych JSON-ów
Skany wymagają OCR (Python 3.13/3.14 albo obraz Dockera); bez OCR ich numery trafią do „nie znaleziono”.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FIELDS = ("na_rachunek", "z_rachunku")


def has_pl_prefix(text: str, number: str) -> bool | None:
    """True/False: czy numer w tekście ma przed sobą „PL”; None: numeru nie znaleziono w tekście."""
    digits = re.sub(r"\D", "", number)
    if len(digits) != 26:
        return None
    body = r"[  -]?".join(re.escape(d) for d in digits)
    hits = [m.group(1) for m in re.finditer(rf"(P\s?L\s?)?(?<!\d){body}(?!\d)", text, re.IGNORECASE)]
    if not hits:
        return None
    return any(h is not None for h in hits)


def plan(train_dir: Path) -> tuple[list[tuple[Path, str, str, str]], list[tuple[Path, str]]]:
    from eval.score import gt_path_for_pdf
    from odw2json import ingest
    from odw2json.config_loader import load_app_config

    cfg = load_app_config().get("ingest")
    changes, missing = [], []
    for pdf in sorted(train_dir.rglob("*.pdf")):
        gt = gt_path_for_pdf(pdf)
        if gt is None:
            continue
        data = json.loads(gt.read_text(encoding="utf-8"))
        pb = data.get("przelew_bankowy") if isinstance(data, dict) else None
        if not pb:
            continue
        todo = [f for f in FIELDS if isinstance(pb.get(f), str) and pb[f] and not pb[f].upper().startswith("PL")]
        if not todo:
            continue
        text = ingest.load(pdf, cfg=cfg).text
        for f in todo:
            found = has_pl_prefix(text, pb[f])
            if found is None:
                missing.append((gt, f))
            elif found:
                changes.append((gt, f, pb[f], "PL" + re.sub(r"\D", "", pb[f])))
    return changes, missing


def apply(changes: list[tuple[Path, str, str, str]]) -> None:
    by_file: dict[Path, list[tuple[str, str]]] = {}
    for gt, f, _old, new in changes:
        by_file.setdefault(gt, []).append((f, new))
    for gt, items in by_file.items():
        data = json.loads(gt.read_text(encoding="utf-8"))
        for f, new in items:
            data["przelew_bankowy"][f] = new
        gt.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="zapisz zmiany (domyślnie tylko podgląd)")
    ap.add_argument("--train-dir", default=str(REPO / "data" / "train"))
    a = ap.parse_args(argv)
    changes, missing = plan(Path(a.train_dir))
    for gt, f, old, new in changes:
        print(f"{gt.relative_to(REPO).as_posix()}: {f} {old} -> {new}")
    for gt, f in missing:
        print(f"bez zmian - nie znaleziono w tekście: {gt.relative_to(REPO).as_posix()}: {f}")
    print(f"zmian: {len(changes)}, nie znaleziono: {len(missing)}{'' if a.apply else ' (podgląd, --apply zapisuje)'}")
    if a.apply:
        apply(changes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
