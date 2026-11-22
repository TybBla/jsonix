"""E7: przelewy ze skanów — etykiety rozbite przez OCR, daty bez kropek, zniekształcone nagłówki."""

from __future__ import annotations

from pathlib import Path

from odw2json import extract
from odw2json.config_loader import load_registry
from odw2json.contracts import Document


def _extract(text: str) -> dict:
    cfg = load_registry()["przelew"]
    doc = Document(path=Path("skan.pdf"), text=text, pages=[text], page_offsets=[0])
    return extract.extract(doc, cfg).data["przelew_bankowy"]


def test_labels_split_across_lines():
    text = (
        "Bank Mazurski\nZ rachunku 68 1090 1505 1005 2441 7124 3731\n"
        "Na rachunek 60 1010 1010 0081 3622 3100 0000\n"
        "Tytulem Wpis od odwołania, ZP/12/2026, SZPITAL\nKwota 10 000,00 PLN\nprzelewu\n"
        "Data 2026-03-26\nwykonania\nStatus Wykonany\nNumer 305494\ntransakcji\nŻródło Bank Mazurski S.A.\n"
    )
    got = _extract(text)
    assert got["data_operacji"] == "2026-03-26"
    assert got["numer_transakcji"] == "305494"


def test_date_without_dots_and_garbled_payment_details_label():
    text = (
        "B Bank Karpacki\nPrzelew krajowy\nRacnunea ziecenwddwry 11 1240 1111 9078 8570 5000 0455\n"
        "Rac nunek kontrahenta 25 1030 1508 9486 5035 5622 1675\nKwota 17.00 PLN\n"
        "Zlecona data wykonania 20 04 2026\n"
        "Szczegoty platnosci opiata skarbowa od peinomocnictwa dla adw Rafal Maknowsku w postępowaniu przed\n"
        "KIO w przetargu ZP/134/2026\nSignature Not Venfied\nDokument podpisany przez Bank Karpacki S.A.\n"
    )
    got = _extract(text)
    assert got["data_operacji"] == "2026-04-20"
    assert got["tytul"].startswith("opiata skarbowa") and got["tytul"].endswith("ZP/134/2026")


def test_title_with_label_after_value():
    """OCR przestawia kolumny: wartość tytułu, a za nią etykieta „Opis”."""
    text = (
        "Potwierdzenie transakcji\n"
        "wpis od odwołania - postępowanie nr DA.ZP.242.50.2026 CEN9057564440515 Opis\n"
        "Data transakcji Numer referencyjny transakcji\nKwota 11.09.2026 CEN9057564440515\n7 500,00 PLN\n"
    )
    assert _extract(text)["tytul"] == "wpis od odwołania - postępowanie nr DA.ZP.242.50.2026 CEN9057564440515"
