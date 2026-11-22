"""E4: odpornosc ekstrakcji „pelnomocnictwo” na warianty prawdziwych tekstow z dev (w pamieci, bez OCR).

Wariant = (tekst, GT) po przerobce: synonimy zapowiedzi pelnomocnictwa we wstepie, nazwiska WIELKIMI
literami (pelnomocnicy i podpisujacy; GT zawsze w postaci tytulowej „Jan Nowak”), etykieta „MOCODAWCA”
wersalikami, podwojne puste linie. Wariant musi dotyczyc >= 10 dokumentow dev, a F1 (wg reguł UZP) >= 0,97.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

import pytest

from eval.score import Counts, score_pair
from odw2json import ingest
from odw2json.config_loader import load_registry
from odw2json.contracts import Document
from odw2json.extract import extract
from odw2json.splits import load_splits

TRAIN = Path(__file__).resolve().parents[1] / "data" / "train"
NO_OCR = {"ocr": {"enabled": False}}
MIN_DOCS = 10
MIN_F1 = 0.97


@cache
def _registry():
    return load_registry()


@cache
def _dev() -> list[tuple[str, str, dict]]:
    """(sprawa, tekst, GT) dla spraw dev z warstwa tekstowa (bez skanow)."""
    out = []
    for case in load_splits()["dev"]:
        pdf = TRAIN / case / "pelnomocnictwo.pdf"
        if case.startswith("skany/") or not pdf.exists():
            continue
        gt = json.loads((TRAIN / case / "pelnomocnictwo.json").read_text(encoding="utf-8"))
        out.append((case, ingest.load(pdf, cfg=NO_OCR).text, gt))
    return out


def _run(text: str) -> dict:
    doc = Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0])
    return extract(doc, _registry()["pelnomocnictwo"]).data


def _names(gt: dict, podpisujacy: bool = True) -> list[str]:
    names = [p["imie_nazwisko"] for p in gt["pelnomocnicy"] if p.get("imie_nazwisko")]
    if podpisujacy:
        for m in gt["mocodawca"]:
            names += [s["imie_nazwisko"] for s in m["podpisujacy"] if s.get("imie_nazwisko")]
    return sorted(set(names), key=len, reverse=True)


# ---------------------------------------------------------------- warianty (tekst, gt) -> tekst


def _sub(pattern: str, repl: str):
    return lambda t, gt: re.sub(pattern, repl, t, flags=re.IGNORECASE)


_UDZIEL = r"(?:niniejszym\s+)?udziela\w*\s+pe[łl]nomocnictwa"
_USTAN = r"ustanawiam\s+pe[łl]nomocnik\w*"


def _restore(text: str, changed: str, original: str) -> str:
    """Przywraca `original` w miejscu `changed` (nazwa moze byc zawinieta - bialymi znakami dowolnymi)."""
    rx = r"\s+".join(re.escape(w) for w in changed.split())
    words = original.split()

    def back(m: re.Match) -> str:
        seps = re.findall(r"\s+", m[0])
        return words[0] + "".join(sep + w for sep, w in zip(seps, words[1:], strict=True))

    return re.sub(rx, back, text)


def _upper_names(whole: bool):
    def up(s: str, gt: dict) -> str:
        for n in _names(gt):
            first, _, last = n.partition(" ")
            s = s.replace(n, n.upper() if whole else f"{first} {last.upper()}")
        return s

    def v(t: str, gt: dict) -> str:
        t = up(t, gt)
        # nazwa firmy osoby fizycznej („DUDEK-TECH Jan Nowak”) jest cytatem - zostaje w oryginale
        for m in gt["mocodawca"]:
            nazwa = m["data"].get("nazwa")
            if nazwa:
                t = _restore(t, up(nazwa, gt), nazwa)
        return t

    return v


def _upper_label(t: str, gt: dict) -> str:
    return re.sub(r"(?m)^([ \t]*)Mocodawca\b", lambda m: m[1] + "MOCODAWCA", t)


def _blank_lines(t: str, gt: dict) -> str:
    return t.replace("\n", "\n\n")


VARIANTS = {
    "wstep: umocowuje": lambda t, gt: re.sub(f"{_UDZIEL}|{_USTAN}", "umocowuję", t, flags=re.I),
    "wstep: udzielam umocowania": _sub(_UDZIEL, "udzielam umocowania"),
    "wstep: ustanawiam pelnomocnikami": _sub(_UDZIEL, "ustanawiam pełnomocnikami"),
    "wstep: upowazniam do reprezentowania": _sub(_UDZIEL, "upoważniam do reprezentowania"),
    "wstep: niniejszym umocowujemy": _sub(_UDZIEL, "niniejszym umocowujemy"),
    "nazwiska WIELKIMI (cale)": _upper_names(True),
    "nazwiska WIELKIMI (samo nazwisko)": _upper_names(False),
    "etykieta MOCODAWCA wersalikami": _upper_label,
    "puste linie podwojone": _blank_lines,
}


def _variant_f1(name: str) -> tuple[int, float]:
    c, n = Counts(), 0
    for _case, text, gt in _dev():
        t2 = VARIANTS[name](text, gt)
        if t2 == text:
            continue
        n += 1
        c = c + score_pair(_run(t2), gt)
    return n, c.f1


def test_dev_pool_has_enough_documents():
    assert len(_dev()) >= 30


def test_baseline_f1_is_perfect_on_dev():
    c = Counts()
    for _case, text, gt in _dev():
        c = c + score_pair(_run(text), gt)
    assert c.f1 == pytest.approx(1.0)


@pytest.mark.parametrize("name", list(VARIANTS))
def test_variant_f1(name):
    n, f1 = _variant_f1(name)
    assert n >= MIN_DOCS, f"wariant dotyczy tylko {n} dokumentow"
    assert f1 >= MIN_F1, f"F1 {f1:.3f} < {MIN_F1} dla wariantu {name!r}"


# ---------------------------------------------------------------- reguly jednostkowe


def test_typ_not_guessed_for_empty_text():
    d = _run("")
    assert d["mocodawca"][0]["data"]["typ"] is None
    assert d["pelnomocnicy"] == [{"imie_nazwisko": None, "pesel": None}]


def test_typ_osoba_prawna_when_document_describes_party():
    d = _run("PEŁNOMOCNICTWO\nMocodawca Alfa S.A.\nul. Polna 1, 00-001 Warszawa\nNIP 1111111111\n")
    assert d["mocodawca"][0]["data"]["typ"] == "osoba_prawna"


def test_mocodawca_label_uppercase_not_part_of_name():
    text = "PEŁNOMOCNICTWO\nMOCODAWCA Hartica Serwis S.A.\nul. Akacjowa 54, 80-122 Gdańsk\nNIP 9990678035\n"
    assert _run(text)["mocodawca"][0]["data"]["nazwa"] == "Hartica Serwis S.A."


def test_nazwa_with_blank_line_before_address():
    text = "PEŁNOMOCNICTWO\n\nHartica Serwis S.A.\n\nul. Akacjowa 54, 80-122 Gdańsk\n\nNIP 9990678035\n"
    assert _run(text)["mocodawca"][0]["data"]["nazwa"] == "Hartica Serwis S.A."


@pytest.mark.parametrize(
    "intro",
    [
        "umocowuję",
        "udzielam umocowania",
        "niniejszym umocowujemy",
        "ustanawiamy pełnomocnikami",
        "upoważniam do reprezentowania",
        "niniejszym upoważniamy do reprezentowania Wykonawcy",
    ],
)
def test_pelnomocnik_after_intro_synonyms(intro):
    text = f"PEŁNOMOCNICTWO\nAlfa S.A., NIP 1111111111, {intro} adw. Jan Nowak (nr wpisu WA 1) w sprawie.\n"
    assert [p["imie_nazwisko"] for p in _run(text)["pelnomocnicy"]] == ["Jan Nowak"]


def test_uppercase_names_for_pelnomocnicy_and_podpisujacy_normalized():
    text = (
        "PEŁNOMOCNICTWO\nAlfa S.A., NIP 1111111111, ustanawiam pełnomocnikiem adw. JAN NOWAK-JEZIORAŃSKI "
        "(nr wpisu), r. pr. Anna KOWALSKA (nr wpisu), do reprezentowania Mocodawcy.\n"
        "............\nPIOTR LIS\nPREZES ZARZĄDU\n"
    )
    d = _run(text)
    assert [p["imie_nazwisko"] for p in d["pelnomocnicy"]] == ["Jan Nowak-Jeziorański", "Anna Kowalska"]
    assert d["mocodawca"][0]["podpisujacy"] == [{"imie_nazwisko": "Piotr Lis"}]
