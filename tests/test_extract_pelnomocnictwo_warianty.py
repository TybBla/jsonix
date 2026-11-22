"""E7: warianty pełnomocnictw ze skanów — dwa podpisy w jednej linii, konsorcjum po przecinku."""

from __future__ import annotations

from pathlib import Path

from odw2json import extract
from odw2json.config_loader import load_registry
from odw2json.contracts import Document

BASE = (
    "Warszawa, dnia 10 marca 2026 roku\nPEŁNOMOCNICTWO\n"
    "Nordex Serwis Sp. z o.o. z siedzibą w Opolu (45-037), ul. Polna 15, wpisana do rejestru przedsiębiorców "
    "Krajowego Rejestru Sądowego pod numerem KRS: 9997873010, NIP: 9991785572,\n"
    "REGON: 999885921, reprezentowana przez: Anna Lis – Prezes Zarządu, Jan Kos – Członek\n"
    "Zarządu (dalej: „Mocodawca”), niniejszym udziela pełnomocnictwa:\n"
    "1. Ewa Nowak – adwokat, nr wpisu KR-10969, do reprezentowania Mocodawcy w sprawie.\n"
    "Za Mocodawcę:\n"
    "{podpisy}\n"
)


def _data(text: str) -> dict:
    doc = Document(path=Path("p.pdf"), text=text, pages=[text], page_offsets=[0])
    return extract.extract(doc, load_registry()["pelnomocnictwo"]).data


def _signers(data: dict, i: int = 0) -> set[str]:
    return {p["imie_nazwisko"] for p in data["mocodawca"][i]["podpisujacy"] if p["imie_nazwisko"]}


def test_two_signatures_merged_into_one_line():
    """OCR skleja dwie kolumny podpisów: „Jan Kos - Członek Zarządu Anna Lis - Prezes Zarządu”."""
    data = _data(BASE.format(podpisy="Jan Kos - Członek Zarządu Anna Lis - Prezes Zarządu"))
    assert _signers(data) == {"Jan Kos", "Anna Lis"}
    # OCR zniekształcił „reprezentowana przez” — zostaje tylko sklejona linia podpisów
    garbled = BASE.replace("reprezentowana przez", "reprenentowana przez")
    data = _data(garbled.format(podpisy="Jan Kos - Członek Zarządu Anna Lis - Prezes Zarządu"))
    assert _signers(data) == {"Jan Kos", "Anna Lis"}


def test_signatures_in_separate_lines_unchanged():
    data = _data(BASE.format(podpisy="Jan Kos - Członek Zarządu\nAnna Lis - Prezes Zarządu"))
    assert _signers(data) == {"Jan Kos", "Anna Lis"}


def test_consortium_members_separated_by_comma():
    text = (
        "Gdynia, dnia 19 marca 2026 roku\nPELNOMOCNICTWO\n"
        "Wykonawcy wspólnie ubiegający się o udzielenie zamówienia (Konsorcjum):\n"
        "1) Tervana Systemy sp. k. z siedzibą w Katowicach (40-031), ul. Długa 14, wpisana do rejestru "
        "przedsiębiorców Krajowego Rejestru Sądowego pod numerem KRS: 9998767758,\n"
        "NIP: 999-343-70-59, REGON: 999211631, reprezentowana przez: Dorota Grabowska – Prezes Zarządu\n"
        "– Lider Konsorcjum,\n"
        "2) Lumidor Budownictwo spółka z ograniczoną odpowiedzialnością z siedzibą w Opolu (45-873), ul.\n"
        "Sienkiewicza 44, wpisana do rejestru przedsiębiorców Krajowego Rejestru Sądowego pod numerem\n"
        "KRS: 9990349003, NIP: 999-98-82-984, REGON: 999376332, reprezentowana przez: Łukasz\n"
        "Sosnowski – Prezes Zarządu – Partner Konsorcjum,\n"
        "(dalej łącznie: „Mocodawca”), niniejszym udzielają pełnomocnictwa:\n"
        "1. Dorota Kubiak – radca prawny, nr wpisu AT-17255, do reprezentowania Mocodawcy.\n"
    )
    data = _data(text)
    assert len(data["mocodawca"]) == 2
    second = data["mocodawca"][1]["data"]
    assert second["krs"] == "9990349003" and second["nip"] == "9999882984"
    assert second["nazwa"].startswith("Lumidor Budownictwo")
