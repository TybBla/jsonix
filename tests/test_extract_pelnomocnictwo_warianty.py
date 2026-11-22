"""E7: warianty pełnomocnictw ze skanów — dwa podpisy w jednej linii, konsorcjum po przecinku.

Wszystkie nazwy, nazwiska i numery są wymyślone (nie pochodzą z data/, w tym z holdoutu).
"""

from __future__ import annotations

from pathlib import Path

from odw2json import extract
from odw2json.config_loader import load_registry
from odw2json.contracts import Document

BASE = (
    "Warszawa, dnia 10 marca 2026 roku\nPEŁNOMOCNICTWO\n"
    "Nordex Serwis Sp. z o.o. z siedzibą w Opolu (45-037), ul. Polna 15, wpisana do rejestru przedsiębiorców "
    "Krajowego Rejestru Sądowego pod numerem KRS: 9991234560, NIP: 9994567812,\n"
    "REGON: 999123453, reprezentowana przez: Anna Lis – Prezes Zarządu, Jan Kos – Członek\n"
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
        "Kielce, dnia 19 marca 2026 roku\nPELNOMOCNICTWO\n"
        "Wykonawcy wspólnie ubiegający się o udzielenie zamówienia (Konsorcjum):\n"
        "1) Orlimex Systemy sp. k. z siedzibą w Kielcach (25-001), ul. Klonowa 8, wpisana do rejestru "
        "przedsiębiorców Krajowego Rejestru Sądowego pod numerem KRS: 9995551203,\n"
        "NIP: 999-876-54-37, REGON: 999654328, reprezentowana przez: Marta Wierzbicka – Prezes Zarządu\n"
        "– Lider Konsorcjum,\n"
        "2) Brzozan Budownictwo spółka z ograniczoną odpowiedzialnością z siedzibą w Lublinie (20-002), ul.\n"
        "Jaworowa 31, wpisana do rejestru przedsiębiorców Krajowego Rejestru Sądowego pod numerem\n"
        "KRS: 9994420817, NIP: 999-30-01-126, REGON: 999471205, reprezentowana przez: Paweł\n"
        "Zieliński – Prezes Zarządu – Partner Konsorcjum,\n"
        "(dalej łącznie: „Mocodawca”), niniejszym udzielają pełnomocnictwa:\n"
        "1. Joanna Mazur – radca prawny, nr wpisu LU-40112, do reprezentowania Mocodawcy.\n"
    )
    data = _data(text)
    assert len(data["mocodawca"]) == 2
    second = data["mocodawca"][1]["data"]
    assert second["krs"] == "9994420817" and second["nip"] == "9993001126"
    assert second["nazwa"].startswith("Brzozan Budownictwo")


def test_company_name_after_zarzadu_is_not_a_signer():
    """Po „Zarządu” stoi nazwa firmy, nie druga osoba: „Anna Lis - Prezes Zarządu Nordex Serwis”."""
    # bez „(dalej” blok podpisujących obejmuje też linię podpisów pod „Za Mocodawcę:”
    base = BASE.replace("(dalej: „Mocodawca”)", "zwana Mocodawcą")
    for line in (
        "Anna Lis - Prezes Zarządu Nordex Serwis",
        "Anna Lis - Prezes Zarządu Nordex Serwis Sp. z o.o.",
        "Anna Lis - Prezes Zarządu Nordex Serwis S.A.",
    ):
        assert _signers(_data(base.format(podpisy=line))) == {"Anna Lis", "Jan Kos"}, line
