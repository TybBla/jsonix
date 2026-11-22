"""Odporność ekstrakcji przelewu na warianty zapisu (kwoty, etykieta tytułu, puste linie).

Warianty powstają w pamięci z tekstu PDF-ów dev (bez zmian na dysku); F1 typu liczone wg reguł UZP.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from eval.score import Counts, score_pair
from odw2json import ingest
from odw2json.config_loader import load_registry
from odw2json.contracts import Document
from odw2json.extract import extract
from odw2json.splits import load_splits

NO_OCR = {"ocr": {"enabled": False}}
MIN_DOCS = 10
MAX_DOCS = 16
MIN_F1 = 0.97


@pytest.fixture(scope="module")
def corpus() -> list[tuple[str, str, dict]]:
    train = Path(__file__).resolve().parents[1] / "data" / "train"
    out = []
    for case in load_splits()["dev"]:
        pdf = train / case / "potwierdzenie_przelewu.pdf"
        gt_path = train / case / "przelew.json"
        if not (pdf.exists() and gt_path.exists()):
            continue
        text = ingest.load(pdf, cfg=NO_OCR).text
        out.append((case, text, json.loads(gt_path.read_text(encoding="utf-8"))))
        if len(out) >= MAX_DOCS:
            break
    assert len(out) >= MIN_DOCS
    return out


def _run(text: str) -> dict:
    doc = Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0])
    return extract(doc, load_registry()["przelew"]).data


def _f1(c: Counts) -> float:
    d = 2 * c.tp + c.fp + c.fn
    return 2 * c.tp / d if d else 1.0


def _score(corpus, variant) -> tuple[float, int, list[str]]:
    total, changed, bad = Counts(), 0, []
    for case, text, gt in corpus:
        text2, gt2 = variant(text, gt)
        if text2 == text and gt2 == gt:
            continue
        changed += 1
        c = score_pair(_run(text2), gt2)
        total = total + c
        if c.fp or c.fn:
            bad.append(case)
    return _f1(total), changed, bad


def _kwota_wariant(fmt, nowa: float | None = None):
    def variant(text, gt):
        k = gt["przelew_bankowy"]["kwota"]
        v = k if nowa is None else nowa
        pat = re.escape(f"{k:.2f}").replace(r"\.", "[.,]")
        text2 = re.sub(rf"(?<![\d.,]){pat}(?:\s*(?:PLN|zł))?", lambda _m: fmt(v), text)
        gt2 = copy.deepcopy(gt)
        gt2["przelew_bankowy"]["kwota"] = float(v)
        return text2, gt2

    return variant


def _tys_kropka(v: float) -> str:
    i, d = f"{v:.2f}".split(".")
    return f"{int(i):,}".replace(",", ".") + f",{d} zł"


def _etykieta_tytulu(text, gt):
    rx = r"(?im)^([ \t]*)(Tytu[łl]em|Tytu[łl] przelewu|Tytu[łl]|Opis(?: operacji)?)\b:?"
    return re.sub(rx, r"\1Tytuł płatności:", text), gt


def _tytul_operacji(text, gt):
    rx = r"(?im)^([ \t]*)(Tytu[łl]em|Tytu[łl] przelewu|Tytu[łl]|Opis(?: operacji)?)\b:?"
    return re.sub(rx, r"\1Tytuł operacji:", text), gt


def _podwojone_linie(text, gt):
    return text.replace("\n", "\n\n"), gt


def _pusta_linia_w_tytule(text, gt):
    """Wstawia pustą linię między dwie pierwsze linie zawiniętego tytułu (o ile tytuł jest wieloliniowy)."""
    tytul = gt["przelew_bankowy"]["tytul"] or ""
    slowa = tytul.split()
    for i in range(1, len(slowa)):
        pierwsza, reszta = " ".join(slowa[:i]), " ".join(slowa[i:])
        text2 = text.replace(f"{pierwsza}\n{reszta.split()[0]}", f"{pierwsza}\n\n{reszta.split()[0]}", 1)
        if text2 != text:
            return text2, gt
    return text, gt


VARIANTS = {
    "kwota 10.000,00 zł": _kwota_wariant(_tys_kropka, 10000.0),
    "kwota 10 000 PLN": _kwota_wariant(lambda v: "10 000 PLN", 10000.0),
    "kwota 17 zł (bez groszy)": _kwota_wariant(lambda v: f"{int(v)} zł"),
    "kwota PLN 17,00": _kwota_wariant(lambda v: "PLN " + f"{v:.2f}".replace(".", ",")),
    "etykieta Tytuł płatności:": _etykieta_tytulu,
    "etykieta Tytuł operacji:": _tytul_operacji,
    "pusta linia wewnątrz tytułu": _pusta_linia_w_tytule,
    "podwojone puste linie": _podwojone_linie,
}


@pytest.mark.parametrize("name", list(VARIANTS))
def test_wariant_przelewu_nie_psuje_f1(corpus, name):
    f1, changed, bad = _score(corpus, VARIANTS[name])
    assert changed >= 1 or name == "pusta linia wewnątrz tytułu"
    assert f1 >= MIN_F1, f"{name}: F1={f1:.3f} na {changed} dok., problemy: {bad[:5]}"


def test_kwoty_obejmuja_co_najmniej_10_dokumentow(corpus):
    _, changed, _ = _score(corpus, VARIANTS["kwota 17 zł (bez groszy)"])
    assert changed >= MIN_DOCS
