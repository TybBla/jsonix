"""E7-13: odporność ekstrakcji na szerszą listę wariantów (synonimy etykiet, szyk zdań, formaty).

Warianty (z `scripts/robustness_probe.py`) przerabiają prawdziwe teksty dev (warstwa tekstu, bez OCR)
w pamięci; GT zmienia się razem z tekstem tylko tam, gdzie powinno. Metryka: F1 wg reguł UZP (`eval.score`).

* Warianty naprawione w E7-13 (każdy na >= 10 dokumentach): F1 >= 0,97 i brak spadku względem tekstu
  oryginalnego.
* Wszystkie pozostałe warianty sondy: brak spadku o więcej niż 0,005 (z wyjątkiem znanych, uzasadnionych luk).

Strojenie wyłącznie na dev; holdout nie jest tu używany.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path

import pytest

from odw2json.config_loader import load_registry

ROOT = Path(__file__).resolve().parents[1]
MIN_DOCS = 10
MIN_F1 = 0.97
EPS = 0.005

# Warianty z E7-13, które wcześniej łamały ekstrakcję (nazwa wariantu, typ dokumentu).
FIXED = [
    ("a9 data operacji->Data przelewu", "przelew"),
    ("a10 data operacji->Data zlecenia", "przelew"),
    ("a11 numer transakcji->Nr transakcji", "przelew"),
    ("a12 numer transakcji->Identyfikator płatności", "przelew"),
    ("a15 tytuł->Opis płatności", "przelew"),
    ("a16 tytuł->Treść przelewu", "przelew"),
    ("a21 adres do korespondencji->adres do doręczeń", "odwolanie"),
    ("a28 w dniu->dnia (czynność)", "odwolanie"),
    ("c13 'W dniu D Zamawiający ...'", "odwolanie"),
    ("a29 Odwołujący:->Wnoszący odwołanie:", "odwolanie"),
    ("a30 nr referencyjny sprawy->nr sprawy", "odwolanie"),
]

# Znane luki, świadomie nienaprawiane (uzasadnienie: docs/decyzje/E4-ekstrakcja.md, „Odporność — sonda”).
KNOWN_GAPS = {
    # numer rachunku zawinięty w środku grupy cyfr i rozdzielony PUSTĄ linią (nierealistyczne złamanie)
    ("c2 puste linie", "przelew"),
}


@cache
def _probe():
    spec = importlib.util.spec_from_file_location(
        "robustness_probe", ROOT / "scripts" / "robustness_probe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["robustness_probe"] = mod  # dataclass (Python 3.14) szuka modułu po nazwie
    spec.loader.exec_module(mod)
    return mod


@cache
def _report():
    probe = _probe()
    registry = load_registry()
    return probe.evaluate(probe.build_corpus("dev", registry), registry, split="dev")


def _row(variant: str, typ: str):
    rows = [r for r in _report().rows if (r.variant, r.type) == (variant, typ)]
    assert rows, f"brak wiersza {variant!r}/{typ} w raporcie sondy"
    return rows[0]


def test_baseline_texts_are_extracted_without_regression():
    rep = _report()
    assert rep.base["przelew"].f1 == pytest.approx(1.0)
    assert rep.base["pelnomocnictwo"].f1 == pytest.approx(1.0)
    assert rep.base["odwolanie"].f1 >= 0.995


@pytest.mark.parametrize(("variant", "typ"), FIXED, ids=[f"{v}|{t}" for v, t in FIXED])
def test_fixed_variant_keeps_f1(variant: str, typ: str):
    row = _row(variant, typ)
    assert row.n >= MIN_DOCS, f"wariant dotyczy tylko {row.n} dokumentów"
    assert row.var_f1 >= MIN_F1, f"F1 {row.var_f1:.3f} < {MIN_F1}"
    assert row.var_f1 >= row.base_f1 - EPS, f"spadek F1: {row.base_f1:.3f} -> {row.var_f1:.3f}"


def test_no_variant_of_the_probe_breaks_extraction():
    broken = [
        f"{r.variant} | {r.type}: {r.base_f1:.3f} -> {r.var_f1:.3f}"
        for r in _report().rows
        if r.broke and (r.variant, r.type) not in KNOWN_GAPS
    ]
    assert not broken, "warianty łamiące ekstrakcję:\n" + "\n".join(broken)
