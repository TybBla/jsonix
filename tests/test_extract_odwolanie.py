"""Ekstrakcja typu „odwolanie” (config/doctypes/odwolanie.yaml): reguły trudne + integracja na dev PDF-ach."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odw2json import ingest
from odw2json.config_loader import DocTypeConfig, load_lookup, load_registry
from odw2json.contracts import Document
from odw2json.extract import extract
from odw2json.splits import load_splits

NO_OCR = {"ocr": {"enabled": False}}


def _doc(text: str) -> Document:
    return Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0])


@pytest.fixture(scope="module")
def cfg() -> DocTypeConfig:
    return load_registry()["odwolanie"]


# ---------------------------------------------------------------- nowe ekstraktory silnika


@pytest.fixture
def make_cfg(tmp_path):
    def _make(fields: dict) -> DocTypeConfig:
        (tmp_path / "schemas").mkdir(exist_ok=True)
        (tmp_path / "lookups").mkdir(exist_ok=True)
        (tmp_path / "schemas" / "t.json").write_text(json.dumps({"a": {"x": None}}), encoding="utf-8")
        (tmp_path / "lookups" / "frazy.yaml").write_text(
            "- {id: 7, phrases: ['nie odrzucil', 're:zaniechal\\w*\\s+odrzucenia']}\n"
            "- {id: 1, phrases: [odrzuceniu oferty]}\n",
            encoding="utf-8",
        )
        return DocTypeConfig(id="t", output_template="schemas/t.json", fields=fields, config_dir=tmp_path)

    return _make


def test_phrase_lookup_priority_not_position(make_cfg):
    c = make_cfg({"a.x": {"type": "int", "extract": [{"phrase_lookup": "frazy"}]}})
    # "odrzuceniu oferty" stoi wcześniej, ale wpis 7 ma pierwszeństwo (kolejność w słowniku)
    res = extract(_doc("o odrzuceniu oferty ... Zamawiający nie odrzucił oferty X"), c)
    assert res.data["a"]["x"] == 7
    assert res.trace[0].method == "phrase_lookup" and "nie odrzucił" in res.trace[0].source_snippet


def test_phrase_lookup_with_within_windows(make_cfg):
    c = make_cfg(
        {
            "a.x": {
                "type": "int",
                "extract": [
                    {"phrase_lookup": "frazy", "within": {"after": "w dniu", "before": "uprzednio"}},
                    {"phrase_lookup": "frazy", "within": [{"after": "zarzut nr 1"}, {"max_chars": 40}]},
                ],
            }
        }
    )
    assert extract(_doc("w dniu 1 maja X. Uprzednio nie odrzucił"), c).data["a"]["x"] is None
    text = "w dniu 1 maja poinformował o odrzuceniu oferty. Uprzednio nie odrzucił"
    assert extract(_doc(text), c).data["a"]["x"] == 1
    # brak zdania o czynności -> drugi wpis: okno po "Zarzut nr 1"
    assert extract(_doc("Zarzut nr 1 – Zamawiający zaniechał odrzucenia oferty"), c).data["a"]["x"] == 7
    far = "Zarzut nr 1 – " + "x" * 60 + " zaniechał odrzucenia"
    assert extract(_doc(far), c).data["a"]["x"] is None  # poza oknem 40 znaków


def test_within_rejects_unknown_keys(make_cfg):
    with pytest.raises(ValueError, match="within"):
        make_cfg({"a.x": {"extract": [{"regex": "x", "within": {"afterr": "a"}}]}})


def test_ocr_digits_normalizer():
    from odw2json.extract.engine import NORMALIZERS

    assert NORMALIZERS["bzp"](NORMALIZERS["ocr_digits"]("2026/BZP o0692455/03")) == "2026/BZP00692455/03"
    assert NORMALIZERS["ocr_digits"]("Sp. z o.o. 12o") == "Sp. z o.o. 120"


def test_flag_extractor_value_and_fallback(make_cfg):
    c = make_cfg({"a.x": {"type": "int", "extract": [{"flag": ["reprezentowany przez"]}, {"const": 0}]}})
    assert extract(_doc("Reprezentowany przez: adw. X"), c).data["a"]["x"] == 1
    assert extract(_doc("bez pełnomocnika"), c).data["a"]["x"] == 0
    c2 = make_cfg({"a.x": {"type": "int", "extract": [{"flag": {"phrases": ["lider"], "value": 5}}]}})
    assert extract(_doc("Lider"), c2).data["a"]["x"] == 5


# ---------------------------------------------------------------- powód z pierwszego zarzutu

HEAD = "Odwołujący:\nAlfa sp. z o.o.\nZamawiający:\nGmina Beta\n"


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("poinformował o odrzuceniu oferty złożonej przez Odwołującego.", 1),
        ("ogłosił wybór oferty w postępowaniu.", 2),
        ("dokonał wyboru oferty najkorzystniejszej. Uprzednio, w dniu 2 maja, nie odrzucił oferty.", 2),
        ("poinformował o wykluczeniu z postępowania podmiotu.", 3),
        ("wykluczył Odwołującego z postępowania.", 3),
        ("opublikował Specyfikację Warunków Zamówienia.", 4),
        ("opublikował ogłoszenie o zamówieniu i udostępnił Specyfikację Warunków Zamówienia.", 4),
        ("zmodyfikował treść Specyfikacji Warunków Zamówienia.", 5),
        ("przekazał wykonawcom odpowiedzi i wyjaśnienia do treści Specyfikacji Warunków Zamówienia.", 6),
        ("udzielił odpowiedzi na pytania wykonawców i opublikował wyjaśnienia treści SWZ.", 6),
        ("nie odrzucił oferty złożonej przez Odwołującego.", 7),
        ("przekazał informację o wyniku postępowania, z której wynika, że zaniechał odrzucenia oferty X.", 7),
        ("nie wykluczył z postępowania podmiotu działającego wspólnie z Odwołującym.", 8),
        ("przekazał informację o wyniku, z której wynika, że zaniechał wykluczenia wykonawcy X.", 8),
        ("unieważnił postępowanie.", 9),
        ("zaniechał unieważnienia postępowania.", 10),
        ("przekazał informację o wyborze oferty X sp. z o.o., zaniechawszy unieważnienia postępowania.", 10),
        ("udostępnił Opis Przedmiotu Zamówienia.", 11),
        (
            "opublikował dokumenty zamówienia, w tym Opis Przedmiotu Zamówienia (Załącznik nr 1 do SWZ).",
            11,
        ),
        ("udostępnił projektowane postanowienia umowy.", 12),
    ],
)
def test_powod_from_czynnosc_sentence(cfg, sentence, expected):
    text = HEAD + f"Zamawiający w dniu 3 lipca 2026 roku {sentence}\nZarzut nr 1 naruszenia zasad:\n"
    res = extract(_doc(text), cfg)
    k = res.data["OdwolanieKIO"]
    assert k["czynnosc_powod_id"] == expected
    assert k["czynnosc_dzien"] == "2026-07-03"
    assert k["czynnosc_opis"] is not None


def test_powod_falls_back_to_first_zarzut(cfg):
    text = HEAD + (
        "Zarzut nr 1 – bezpodstawnego unieważnienia postępowania, tj. naruszenie art. 255 Pzp;\n"
        "Zarzut nr 2 – zaniechania odrzucenia oferty wykonawcy X;\n"
    )
    k = extract(_doc(text), cfg).data["OdwolanieKIO"]
    assert k["czynnosc_powod_id"] == 9
    assert k["czynnosc_dzien"] is None  # brak wiarygodnej daty czynności


def test_no_czynnosc_gives_nulls(cfg):
    k = extract(_doc(HEAD + "Treść bez zarzutów.\n"), cfg).data["OdwolanieKIO"]
    assert k["czynnosc_powod_id"] is None and k["czynnosc_opis"] is None and k["czynnosc_dzien"] is None


# ---------------------------------------------------------------- strony i nagłówek

MULTI = """Kraków, 02.07.2026
Prezes Krajowej Izby Odwoławczej
Odwołujący:
Nordelia Facility Services S.A.
ul. Wielicka 250, 30-663 Kraków
KRS: 9993307745, NIP: 9995519382, REGON: 999284670
reprezentowany przez: r. pr. Joanna Stępień, adw. Michał Borkowski
adres do korespondencji: Stępień Borkowski Kancelaria Prawna sp.p., ul. Dietla 64/5, 31-039
Kraków
tel. 000 000 000, e-mail: sekretariat@sbkancelaria.example
Zamawiający (zamawiający wspólnie przeprowadzający postępowanie na podstawie art. 38 ust.
1 Pzp):
1) Zamawiający – Lider, prowadzący postępowanie:
Małopolskie Centrum Logistyki Medycznej sp. z o.o.
ul. Kamieńskiego 47, 30-644 Kraków
KRS: 9991840562, NIP: 9998802341, REGON: 999015873
2) Zamawiający – Partner:
Krakowskie Zakłady Komunalne S.A.
ul. Półłanki 18, 30-740 Kraków
NIP: 9990457736, REGON: 999762149
dotyczy: postępowania pn. "Kompleksowe usługi utrzymania
czystości", nr referencyjny:
MCLM/ZP/07/2026, ogłoszenie o zamówieniu w Biuletynie Zamówień Publicznych nr
2026/BZP 00999263, ogłoszenie w Dzienniku Urzędowym Unii Europejskiej nr 2026/S
199-999065
ODWOŁANIE
Działając w imieniu Odwołującego wnoszę odwołanie. Wcześniejsze ogłoszenie nr 2025/BZP 00998207.
"""


def test_multiple_zamawiajacy_with_leader(cfg):
    d = extract(_doc(MULTI), cfg).data
    zam = d["Zamawiajacy"]
    assert [z["nazwa"] for z in zam] == [
        "Małopolskie Centrum Logistyki Medycznej sp. z o.o.",
        "Krakowskie Zakłady Komunalne S.A.",
    ]
    assert [z["prowadzacy_postepowanie"] for z in zam] == [1, 0]
    assert zam[0]["krs"] == "9991840562" and zam[1]["krs"] is None and zam[1]["nip"] == "9990457736"
    odw = d["Odwolujacy"]
    assert len(odw) == 1 and odw[0]["nazwa"] == "Nordelia Facility Services S.A."
    assert odw[0]["przez-pelnomocnika"] == 1
    assert odw[0]["pelnomocnik"] == {
        "imie_nazwisko": "Joanna Stępień",
        "nazwa": "Stępień Borkowski Kancelaria Prawna sp.p.",
        "mail": "sekretariat@sbkancelaria.example",
    }
    zp = d["ZamowieniePubliczne"]
    assert zp == {
        "numer_bzp": "2026/BZP00999263",
        "numer_postepowania": "MCLM/ZP/07/2026",
        "numer_ted": "999065-2026",
        "tytul": "Kompleksowe usługi utrzymania czystości",
    }
    assert d["OdwolanieKIO"]["data"] == "2026-07-02" and d["OdwolanieKIO"]["miejscowosc"] == "Kraków"


def test_single_zamawiajacy_has_null_prowadzacy(cfg):
    text = (
        MULTI.split("Zamawiający (")[0] + "Zamawiający:\nGmina Rudnik Wielki\nNIP: 9990264287\ndotyczy: x\n"
    )
    zam = extract(_doc(text), cfg).data["Zamawiajacy"]
    assert len(zam) == 1 and zam[0]["nazwa"] == "Gmina Rudnik Wielki"
    assert zam[0]["prowadzacy_postepowanie"] is None


def test_konsorcjum_gives_leader(cfg):
    text = (
        "Odwołujący: Konsorcjum wykonawców wspólnie ubiegających się o udzielenie zamówienia w\nskładzie:\n"
        "1) Lider Konsorcjum:\nKorvel Serwis sp. z o.o. sp.k.\n"
        "KRS: 9997450782, NIP: 9996998288, REGON: 999873715\n"
        "2) Partner Konsorcjum:\nLumerio Facility sp.j.\nKRS: 9990093297, NIP: 9999917794, REGON: 999404710\n"
        "dotyczy: x\n"
    )
    o = extract(_doc(text), cfg).data["Odwolujacy"][0]
    assert (o["nazwa"], o["krs"], o["nip"], o["regon"]) == (
        "Korvel Serwis sp. z o.o. sp.k.",
        "9997450782",
        "9996998288",
        "999873715",
    )
    assert o["przez-pelnomocnika"] == 0 and o["pelnomocnik"]["imie_nazwisko"] is None


SYN = """Instytucja zamawiająca: Gmina Rudnik Wielki, ul. Polna 5, 00-001 Rudnik, NIP: 9990264287
Wykonawca wnoszący odwołanie:
DUDEK-TECH Jarosław Dudek reprezentowany przez: adw. Natalia GÓRECKA
adres do korespondencji: Kancelaria Adwokacka Spółka z
ograniczoną odpowiedzialnością, ul. Jasionowa 19, 80-994 Gdańsk
tel. 000 000 000, e-mail: biuro@kancelaria.example
dotyczy: x
"""


def test_party_label_synonyms_and_name_boundaries(cfg):
    d = extract(_doc(SYN), cfg).data
    assert [z["nazwa"] for z in d["Zamawiajacy"]] == ["Gmina Rudnik Wielki"]
    assert d["Zamawiajacy"][0]["nip"] == "9990264287"
    o = d["Odwolujacy"][0]
    assert o["nazwa"] == "DUDEK-TECH Jarosław Dudek"
    assert o["pelnomocnik"]["nazwa"] == "Kancelaria Adwokacka Spółka z ograniczoną odpowiedzialnością"
    assert o["pelnomocnik"]["mail"] == "biuro@kancelaria.example"
    # wersaliki: wzorzec łapie całe „Imię NAZWISKO” (wielkość liter poprawia names.py)
    assert o["pelnomocnik"]["imie_nazwisko"].lower() == "natalia górecka"


def test_header_date_only_from_place_line(cfg):
    text = "Prezes Krajowej Izby Odwoławczej\nul. Postępu 17A\n02-676 Warszawa\n" + HEAD
    k = extract(_doc(text + "ustawy z dnia 11 września 2019 r.\n"), cfg).data["OdwolanieKIO"]
    assert k["data"] is None and k["miejscowosc"] is None


# ---------------------------------------------------------------- integracja na dev

CASES = [
    "przyklad_01",
    "przyklad_02",
    "przyklad_07",
    "przyklad_42",
    "przyklad_44",
    "przyklad_46",
    "przyklad_49",
]
KEY = [
    ("OdwolanieKIO", "data"),
    ("OdwolanieKIO", "czynnosc_dzien"),
    ("OdwolanieKIO", "czynnosc_powod_id"),
    ("OdwolanieKIO", "miejscowosc"),
    ("ZamowieniePubliczne", "numer_bzp"),
    ("ZamowieniePubliczne", "numer_postepowania"),
    ("ZamowieniePubliczne", "numer_ted"),
    ("ZamowieniePubliczne", "tytul"),
]
PARTY = {
    "Odwolujacy": ["krs", "nazwa", "nip", "regon", "przez-pelnomocnika", "pelnomocnik"],
    "Zamawiajacy": ["krs", "nazwa", "nip", "regon", "prowadzacy_postepowanie"],
}


def _run(train_dir, case: str):
    doc = ingest.load(train_dir / case / "odwolanie.pdf", cfg=NO_OCR)
    res = extract(doc, load_registry()["odwolanie"])
    gt = json.loads((train_dir / case / "odwolanie.json").read_text(encoding="utf-8"))
    return res, gt


@pytest.mark.parametrize("case", CASES)
def test_odwolanie_key_fields_match_ground_truth(train_dir, case):
    res, gt = _run(train_dir, case)
    for sec, key in KEY:
        assert res.data[sec][key] == gt[sec][key], f"{sec}.{key}"
    # opis = słownik UZP wg id (GT bywa niespójne: „Odpowiedzi i wyjaśnienia” vs „Odpowiedzi/wyjaśnienia”)
    k = res.data["OdwolanieKIO"]
    assert k["czynnosc_opis"] == load_lookup("czynnosc_powod")[k["czynnosc_powod_id"]]
    for sec, keys in PARTY.items():
        assert len(res.data[sec]) == len(gt[sec]), sec
        for got, exp in zip(res.data[sec], gt[sec], strict=True):
            for k in keys:
                assert got[k] == exp[k], f"{sec}.{k}"


def test_odwolanie_trace_has_page_and_snippet(train_dir):
    res, _ = _run(train_dir, "przyklad_42")
    filled = [t for t in res.trace if t.value is not None]
    assert len(filled) >= 25
    assert all(t.page is not None and t.source_snippet for t in filled)
    paths = {t.path for t in filled}
    assert {"Zamawiajacy[0].nazwa", "Zamawiajacy[1].nazwa", "Odwolujacy[0].pelnomocnik.mail"} <= paths


def test_odwolanie_dev_accuracy(train_dir):
    """Dokładność pól skalarnych na wszystkich dev z warstwą tekstu (strojenie tylko na dev)."""
    cases = [c for c in load_splits()["dev"] if not c.startswith("skany/")]
    ok = total = 0
    for case in cases:
        if not (train_dir / case / "odwolanie.pdf").exists():
            continue
        res, gt = _run(train_dir, case)
        for sec, key in KEY:
            total += 1
            ok += res.data[sec][key] == gt[sec][key]
    assert total and ok / total >= 0.95
