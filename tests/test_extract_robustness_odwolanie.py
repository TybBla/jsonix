"""Odporność reguł ekstrakcji „odwolanie” na inne sformułowania (warianty dev tworzone w pamięci).

Każdy wariant przekształca tekst prawdziwych dev PDF-ów (warstwa tekstu) tak, jak mógłby to zrobić inny
autor pisma: synonimy etykiet stron, inne zawinięcie nazwy kancelarii, adres w linii nazwy, odwrócona
kolejność stron, nazwisko pełnomocnika wersalikami. Oczekiwanie: F1 wariantu (wg reguł UZP) >= 0,97.
Strojenie wyłącznie na dev (holdout nietknięty).
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest

from eval.score import Counts, score_pair
from odw2json import ingest
from odw2json.config_loader import DocTypeConfig, load_registry
from odw2json.contracts import Document
from odw2json.extract import extract
from odw2json.splits import load_splits

NO_OCR = {"ocr": {"enabled": False}}
MIN_DOCS = 10
MIN_F1 = 0.97


@pytest.fixture(scope="module")
def cfg() -> DocTypeConfig:
    return load_registry()["odwolanie"]


@pytest.fixture(scope="module")
def corpus() -> list[tuple[str, str, dict]]:
    """(sprawa, tekst, GT) wszystkich dev odwołań z warstwą tekstu."""
    train = Path(__file__).resolve().parents[1] / "data" / "train"
    out = []
    for case in load_splits()["dev"]:
        pdf = train / case / "odwolanie.pdf"
        if case.startswith("skany/") or not pdf.exists():
            continue
        doc = ingest.load(pdf, cfg=NO_OCR)
        gt = json.loads((train / case / "odwolanie.json").read_text(encoding="utf-8"))
        out.append((case, doc.text, gt))
    return out


def _run(cfg: DocTypeConfig, text: str) -> dict:
    return extract(Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0]), cfg).data


def _f1(c: Counts) -> float:
    d = 2 * c.tp + c.fp + c.fn
    return 2 * c.tp / d if d else 1.0


def _score_variant(cfg, corpus, variant) -> tuple[float, int, dict[str, Counts]]:
    """F1 po wszystkich zmienionych dokumentach, liczba zmienionych, liczniki per pole."""
    total, changed, fields = Counts(), 0, {}
    for _case, text, gt in corpus:
        text2 = variant(text, gt)
        if text2 == text:
            continue
        changed += 1
        c = score_pair(_run(cfg, text2), gt)
        total = total + c
        for k, v in c.fields.items():
            fields[k] = fields[k] + v if k in fields else v
    return _f1(total), changed, fields


def _field_errors(fields: dict[str, Counts], prefix: str) -> int:
    return sum(c.fp + c.fn for k, c in fields.items() if k.startswith(prefix))


# ---------------------------------------------------------------- warianty


def _relabel(old: str, new: str):
    rx = re.compile(rf"(?m)^([ \t]*){old}:")
    return lambda t, gt: rx.sub(lambda m: m[1] + new + ":", t)


def _swap_parties(t: str, gt: dict) -> str:
    lines = t.split("\n")

    def find(rx):
        return next((i for i, ln in enumerate(lines) if re.match(rx, ln)), None)

    o = find(r"\s*(?:Odwołujący|Wykonawca)[^\n]*:")
    z = find(r"\s*(?:Zamawiający|Instytucja|Strona|Podmiot)[^\n]*:")
    if o is None or z is None:
        return t
    end = re.compile(r"\s*(ODWOŁANIE|dotyczy|Dotyczy|Wykonawca wybrany|Przystępując|Uczestnik)")
    a, b = sorted([o, z])
    e = next((i for i in range(b + 1, len(lines)) if end.match(lines[i])), None)
    if e is None:
        return t
    return "\n".join(lines[:a] + lines[b:e] + lines[a:b] + lines[e:])


def _both(odw: str, zam: str):
    f1, f2 = _relabel("Odwołujący", odw), _relabel("Zamawiający", zam)
    return lambda t, gt: f2(f1(t, gt), gt)


def _swapped(odw: str, zam: str):
    both = _both(odw, zam)
    return lambda t, gt: _swap_parties(both(t, gt), gt)


def _address_in_name_line(t: str, gt: dict) -> str:
    """„Nazwa\\nul. X 1, 00-000 Miasto” -> „Nazwa, ul. X 1, 00-000 Miasto” (strony i konsorcjum)."""
    return re.sub(
        r"(?m)^((?:Odwołujący|Zamawiający):\n[^\n]+|[ \t]*\d\)[ \t]*Lider Konsorcjum:\n[^\n]+)"
        r"\n((?:ul|al|pl|os)\.)",
        r"\1, \2",
        t,
    )


def _address_no_comma_same_line(t: str, gt: dict) -> str:
    """Jak wyżej, ale bez przecinka (odwinięcie linii przez eksport PDF): „Nazwa ul. X 1, 00-000 Miasto”."""
    return re.sub(
        r"(?m)^((?:Odwołujący|Zamawiający):\n[^\n]+)\n((?:ul|al|pl|os)\.)",
        r"\1 \2",
        t,
    )


def _wrap_kancelaria(width: int):
    def f(t: str, gt: dict) -> str:
        nazwa = gt["Odwolujacy"][0]["pelnomocnik"]["nazwa"]
        old = f"adres do korespondencji: {nazwa}"
        if not nazwa or old not in t:
            return t
        return t.replace(old, "adres do korespondencji: " + "\n".join(textwrap.wrap(nazwa, width)))

    return f


def _rewrap_all(width: int):
    def f(t: str, gt: dict) -> str:
        out: list[str] = []
        for para in t.split("\n"):
            out.extend(textwrap.wrap(para, width, break_long_words=False, break_on_hyphens=False) or [""])
        return "\n".join(out)

    return f


def _upper_surname(t: str, gt: dict) -> str:
    name = gt["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"]
    if not name or name not in t:
        return t
    first, _, rest = name.partition(" ")
    return t.replace(name, f"{first} {rest.upper()}")


# ---------------------------------------------------------------- testy


@pytest.mark.parametrize(
    "label",
    [
        "Wykonawca wnoszący odwołanie",
        "Wykonawca (Odwołujący)",
        "Odwołujący się",
    ],
)
def test_odwolujacy_label_synonyms(cfg, corpus, label):
    f1, n, _ = _score_variant(cfg, corpus, _relabel("Odwołujący", label))
    assert n >= MIN_DOCS
    assert f1 >= MIN_F1, f"{label}: F1={f1:.3f}"


@pytest.mark.parametrize(
    "label",
    [
        "Instytucja zamawiająca",
        "Zamawiający – nazwa",
        "Strona zamawiająca",
        "Podmiot zamawiający",
    ],
)
def test_zamawiajacy_label_synonyms(cfg, corpus, label):
    f1, n, _ = _score_variant(cfg, corpus, _relabel("Zamawiający", label))
    assert n >= MIN_DOCS
    assert f1 >= MIN_F1, f"{label}: F1={f1:.3f}"


@pytest.mark.parametrize(
    ("odw", "zam"),
    [
        ("Wykonawca wnoszący odwołanie", "Instytucja zamawiająca"),
        ("Wykonawca (Odwołujący)", "Strona zamawiająca"),
        ("Odwołujący się", "Podmiot zamawiający"),
    ],
)
def test_both_labels_synonyms_and_swapped_order(cfg, corpus, odw, zam):
    f1, n, fields = _score_variant(cfg, corpus, _both(odw, zam))
    assert n >= MIN_DOCS and f1 >= MIN_F1, f"{odw}/{zam}: F1={f1:.3f}"
    # Zamawiający przed Odwołującym: blok pierwszej strony nie może „połykać” danych drugiej
    f1s, ns, fs = _score_variant(cfg, corpus, _swapped(odw, zam))
    assert ns >= MIN_DOCS and f1s >= MIN_F1, f"zamiana {odw}/{zam}: F1={f1s:.3f}"
    assert _field_errors(fs, "Zamawiajacy") <= 2 and _field_errors(fs, "Odwolujacy") <= 2


def test_kancelaria_name_wrapped_differently(cfg, corpus):
    for width in (24, 30, 38):
        f1, n, fields = _score_variant(cfg, corpus, _wrap_kancelaria(width))
        assert n >= MIN_DOCS, width
        assert f1 >= MIN_F1, f"szerokość {width}: F1={f1:.3f}"
        assert _field_errors(fields, "Odwolujacy[].pelnomocnik.nazwa") <= 1, width


def test_whole_text_rewrapped_keeps_party_fields(cfg, corpus):
    f1, n, fields = _score_variant(cfg, corpus, _rewrap_all(55))
    assert n >= MIN_DOCS and f1 >= MIN_F1, f"F1={f1:.3f}"
    assert _field_errors(fields, "Odwolujacy[].pelnomocnik.nazwa") <= 1


def test_address_in_name_line(cfg, corpus):
    f1, n, fields = _score_variant(cfg, corpus, _address_in_name_line)
    assert n >= MIN_DOCS and f1 >= MIN_F1, f"F1={f1:.3f}"
    assert _field_errors(fields, "Odwolujacy[].nazwa") == 0
    assert _field_errors(fields, "Zamawiajacy[].nazwa") == 0


def test_address_in_name_line_without_comma(cfg, corpus):
    f1, n, fields = _score_variant(cfg, corpus, _address_no_comma_same_line)
    assert n >= MIN_DOCS and f1 >= MIN_F1, f"F1={f1:.3f}"
    assert _field_errors(fields, "Zamawiajacy[].nazwa") == 0


def test_labels_synonyms_with_address_in_name_line(cfg, corpus):
    relabel = _both("Wykonawca wnoszący odwołanie", "Instytucja zamawiająca")

    def variant(t, gt):  # najpierw adres do linii nazwy (wzorzec zna stare etykiety), potem synonimy etykiet
        return relabel(_address_in_name_line(t, gt), gt)

    f1, n, _ = _score_variant(cfg, corpus, variant)
    assert n >= MIN_DOCS and f1 >= MIN_F1, f"F1={f1:.3f}"


def test_pelnomocnik_surname_uppercase(cfg, corpus):
    ok = total = 0
    for _case, text, gt in corpus:
        text2 = _upper_surname(text, gt)
        if text2 == text:
            continue
        total += 1
        got = _run(cfg, text2)["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"]
        ok += got == gt["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"]
    assert total >= MIN_DOCS
    assert ok / total >= 0.95, f"{ok}/{total}"


def test_pelnomocnik_uppercase_surname_is_captured_whole(cfg, corpus):
    """Niezależnie od names.py: wzorzec łapie całe „Imię NAZWISKO” (a nie ucina po imieniu)."""
    from odw2json.extract.engine import NORMALIZERS

    seen = 0
    for _case, text, gt in corpus:
        text2 = _upper_surname(text, gt)
        if text2 == text:
            continue
        seen += 1
        got = _run(cfg, text2)["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"]
        exp = gt["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"]
        assert got is not None
        # porównanie bez wielkości liter: normalizator może (names.py) lub nie zamienić wersaliki
        assert got.lower() == exp.lower() or NORMALIZERS["name"](got).lower() == exp.lower(), (got, exp)
    assert seen >= MIN_DOCS
