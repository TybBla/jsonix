"""Ekstrakcja „pelnomocnictwo” (config/doctypes/pelnomocnictwo.yaml) + rozszerzenia silnika dla list.

Rozszerzenia DSL (generyczne, opisane w docs/nowy-typ-dokumentu.md): ``split.item_regex`` (elementy od
trafień regexu na oryginale, z wielkością liter), ``lists.<L>.groups`` (i-ty element listy zagnieżdżonej
szukany w i-tym bloku całego dokumentu), ``lists.<L>.unique`` (bez duplikatów i pustych elementów),
ekstraktor ``if_match`` (stała, gdy fraza występuje).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odw2json import ingest
from odw2json.config_loader import DocTypeConfig, load_registry
from odw2json.contracts import Document
from odw2json.extract import extract

NO_OCR = {"ocr": {"enabled": False}}


def _doc(text: str) -> Document:
    return Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0])


def _pel(text: str) -> dict:
    return extract(_doc(text), load_registry()["pelnomocnictwo"]).data


@pytest.fixture
def make_cfg(tmp_path):
    def _make(template: dict, fields: dict, lists: dict | None = None) -> DocTypeConfig:
        (tmp_path / "schemas").mkdir(exist_ok=True)
        (tmp_path / "schemas" / "t.json").write_text(json.dumps(template), encoding="utf-8")
        return DocTypeConfig(
            id="t", output_template="schemas/t.json", fields=fields, lists=lists or {}, config_dir=tmp_path
        )

    return _make


# ---------------------------------------------------------------- rozszerzenia silnika


def test_split_item_regex_is_case_sensitive_on_original(make_cfg):
    tmpl = {"L": [{"n": None}]}
    fields = {"L[].n": {"extract": [{"regex": {"pattern": "(?P<v>[A-Z][a-z]+ [A-Z][a-z]+)", "case": True}}]}}
    lists = {
        "L": {"split": {"start": "re:udziela", "end": "re:do reprezent", "item_regex": "[A-Z][a-z]+ [A-Z]"}}
    }
    text = "Ala Kot nie\nudziela: Jan Nowak oraz Ewa Lis, ala ma kota\ndo reprezentowania Ola Mak"
    res = extract(_doc(text), make_cfg(tmpl, fields, lists))
    assert res.data["L"] == [{"n": "Jan Nowak"}, {"n": "Ewa Lis"}]


def test_lists_unique_drops_duplicates_and_empty_items(make_cfg):
    tmpl = {"L": [{"n": None}]}
    fields = {"L[].n": {"extract": [{"label": "osoba"}]}}
    lists = {"L": {"split": {"item_sep": "re:^-"}, "unique": True}}
    res = extract(_doc("- osoba Jan\n- nic\n- osoba Jan\n- osoba Ewa"), make_cfg(tmpl, fields, lists))
    assert res.data["L"] == [{"n": "Jan"}, {"n": "Ewa"}]
    assert {t.path for t in res.trace} == {"L[0].n", "L[1].n"}


def test_lists_unique_keeps_single_null_item_when_nothing_found(make_cfg):
    tmpl = {"L": [{"n": None}]}
    fields = {"L[].n": {"extract": [{"label": "osoba"}]}}
    lists = {"L": {"split": {"item_sep": "re:^-"}, "unique": True}}
    res = extract(_doc("- nic\n- nic"), make_cfg(tmpl, fields, lists))
    assert res.data["L"] == [{"n": None}]


def test_nested_list_groups_pick_block_by_parent_index(make_cfg):
    tmpl = {"M": [{"nazwa": None, "P": [{"imie": None}]}]}
    fields = {
        "M[].nazwa": {"extract": [{"label": "firma"}]},
        "M[].P[].imie": {"extract": [{"label": "osoba"}]},
    }
    lists = {
        "M": {"split": {"start": "re:^firmy", "end": "re:^koniec", "item_sep": "re:^firma"}},
        "M[].P": {
            "split": {"item_sep": "re:^osoba"},
            "groups": {"start": "re:^za ", "item_sep": "re:^za "},
        },
    }
    text = "Firmy:\nFirma A\nFirma B\nKoniec\nZa A:\nOsoba Jan\nOsoba Ewa\nZa B:\nOsoba Adam"
    res = extract(_doc(text), make_cfg(tmpl, fields, lists))
    assert res.data == {
        "M": [
            {"nazwa": "A", "P": [{"imie": "Jan"}, {"imie": "Ewa"}]},
            {"nazwa": "B", "P": [{"imie": "Adam"}]},
        ]
    }


def test_nested_list_groups_fall_back_to_parent_region(make_cfg):
    tmpl = {"M": [{"nazwa": None, "P": [{"imie": None}]}]}
    fields = {
        "M[].nazwa": {"extract": [{"label": "firma"}]},
        "M[].P[].imie": {"extract": [{"label": "osoba"}]},
    }
    lists = {
        "M[].P": {"split": {"item_sep": "re:^osoba"}, "groups": {"start": "re:^za ", "item_sep": "re:^za "}}
    }
    res = extract(_doc("Firma A\nOsoba Jan"), make_cfg(tmpl, fields, lists))
    assert res.data == {"M": [{"nazwa": "A", "P": [{"imie": "Jan"}]}]}


def test_if_match_extractor_gives_constant_when_phrase_found(make_cfg):
    tmpl = {"a": {"t": None}}
    fields = {
        "a.t": {
            "extract": [
                {"if_match": {"phrases": ["dzialalnosc gospodarcza"], "then": "fizyczna"}},
                {"const": "prawna"},
            ]
        }
    }
    cfg = make_cfg(tmpl, fields)
    assert extract(_doc("prowadzący działalność gospodarczą"), cfg).data["a"]["t"] == "fizyczna"
    res = extract(_doc("spółka z o.o."), cfg)
    assert res.data["a"]["t"] == "prawna"


# ---------------------------------------------------------------- reguły pełnomocnictwa (jednostkowe)


def test_podpisujacy_after_dotted_lines_skip_function_and_za_line():
    text = (
        "PEŁNOMOCNICTWO\nAlfa Beta sp. z o.o. z siedzibą w Gdańsk (KRS 0000123456, NIP 1234567890) "
        "udzielam pełnomocnictwa adw. Jan Nowak (nr wpisu) do reprezentowania spółki.\n"
        "............\nZa Alfa Beta sp. z o.o.\nAnna Kowalska\nPrezes Zarządu\n"
        "............\nPiotr Lis\nCzłonek Zarządu\n(podpis i pieczęć)\n"
    )
    d = _pel(text)
    assert d["mocodawca"][0]["podpisujacy"] == [
        {"imie_nazwisko": "Anna Kowalska"},
        {"imie_nazwisko": "Piotr Lis"},
    ]
    assert d["mocodawca"][0]["data"] == {
        "imie_nazwisko": None,
        "krs": "0000123456",
        "nazwa": "Alfa Beta sp. z o.o.",
        "nip": "1234567890",
        "typ": "osoba_prawna",
    }
    assert d["pelnomocnicy"] == [{"imie_nazwisko": "Jan Nowak", "pesel": None}]


def test_wielu_pelnomocnikow_z_zawinieta_nazwa_i_pesel():
    text = (
        "PEŁNOMOCNICTWO\nGamma S.A., ul. Polna 1, 00-001 Warszawa, KRS 0000000001, NIP 1111111111 "
        '(dalej: "Mocodawca"), udziela pełnomocnictwa: r. pr. Katarzyna Michalak, PESEL 85071204278 '
        "(nr wpisu), adw. Jolanta\nZajkowski (nr wpisu).\n"
        "Pełnomocnictwo udzielone zostaje do reprezentowania.\n"
        "Pełnomocnictwo przyjmuję:\n.......\nr. pr. Katarzyna Michalak\n.......\nadw. Jolanta Zajkowski\n"
    )
    d = _pel(text)
    assert d["pelnomocnicy"] == [
        {"imie_nazwisko": "Katarzyna Michalak", "pesel": "85071204278"},
        {"imie_nazwisko": "Jolanta Zajkowski", "pesel": None},
    ]


def test_skan_reprezentowana_przez_i_lista_nazwisk_bez_tytulow():
    text = (
        "PELNOMOCNICTWO\nDelta Spółka z ograniczoną odpowiedzialnością z siedzibą w Gdańsk, ul. Leśna 5, "
        "pod numerem KRS: 9998927009, NIP: 999-086-42-52, reprezentowana\n"
        "przez: Żaneta Rybak - Wiceprezes Zarządu, Jakub Zawadzki - Członek Zarządu (dalej:\n"
        'Mocodawca"), niniejszym udziela pełnomocnictwa:\nAnna Topolska\nPiotr Wróbel\n'
        "do reprezentowania Mocodawcy.\nZa Mocodawcę:\nJakub Zawadzki – Członek Zarządu\n"
    )
    d = _pel(text)
    m = d["mocodawca"][0]
    assert m["data"]["nazwa"] == "Delta Spółka z ograniczoną odpowiedzialnością"
    assert m["data"]["nip"] == "9990864252"
    assert m["podpisujacy"] == [{"imie_nazwisko": "Żaneta Rybak"}, {"imie_nazwisko": "Jakub Zawadzki"}]
    assert [p["imie_nazwisko"] for p in d["pelnomocnicy"]] == ["Anna Topolska", "Piotr Wróbel"]


def test_osoba_fizyczna_jako_mocodawca():
    text = (
        "PEŁNOMOCNICTWO\nJa, niżej podpisany Jarosław Dudek, prowadzący działalność gospodarczą pod firmą "
        "DUDEK-TECH\nJarosław Dudek, ul. Nadbystrzycka 40, 20-618 Lublin, NIP 9994150873, "
        "niniejszym udzielam\n"
        "pełnomocnictwa: adw. Natalia Górecka (nr wpisu).\nMocodawca:\n.........\nJarosław Dudek\n"
        "Pełnomocnictwo przyjmuję:\n.........\nadw. Natalia Górecka\n"
    )
    m = _pel(text)["mocodawca"][0]
    assert m["data"] == {
        "imie_nazwisko": "Jarosław Dudek",
        "krs": None,
        "nazwa": "DUDEK-TECH Jarosław Dudek",
        "nip": "9994150873",
        "typ": "osoba_fizyczna",
    }
    assert m["podpisujacy"] == [{"imie_nazwisko": "Jarosław Dudek"}]


def test_osoba_fizyczna_forma_z_ukosnikiem_ze_skanu():
    text = (
        "PELNOMOCNICTWO\nJa, niżej podpisany/a Paweł Brzozowski, prowadzący/a działalność gospodarczą "
        "pod firmą Paweł Brzozowski Usługi, ul. Łąkowa 45B, 80-822 Gdańsk, NIP: 999-663-55-12 (dalej:\n"
        'Mocodawca"), niniejszym udziela pełnomocnictwa:\n'
        "1. Andrzej Wróbel – radca prawny, nr wpisu WR-8082,\n"
        "2. Monika Zawadzka – adwokat, nr wpisu WA-2826, do reprezentowania Mocodawcy.\n"
        "Signature Not Verified Dokument podpisany przez Paweł Brzozowski\n"
    )
    d = _pel(text)
    m = d["mocodawca"][0]
    assert m["data"]["typ"] == "osoba_fizyczna"
    assert m["data"]["imie_nazwisko"] == "Paweł Brzozowski"
    assert m["data"]["nip"] == "9996635512"
    assert m["podpisujacy"] == [{"imie_nazwisko": "Paweł Brzozowski"}]
    assert [p["imie_nazwisko"] for p in d["pelnomocnicy"]] == ["Andrzej Wróbel", "Monika Zawadzka"]


# ---------------------------------------------------------------- integracja (dev, warstwa tekstu)

# układy: § 1. Mocodawca / tabela „Mocodawca … Pełnomocnicy” / „Działając w imieniu” / nagłówek MOCODAWCA /
# „X z siedzibą … udzielam” / „Ja, niżej podpisany(a)” / „udziela pełnomocnictwa:” + PESEL /
# osoba fizyczna / konsorcja (2 mocodawców, „W imieniu …:”) / „Za X” nad podpisem
CASES = [
    "przyklad_01",
    "przyklad_02",
    "przyklad_03",
    "przyklad_04",
    "przyklad_05",
    "przyklad_12",
    "przyklad_24",
    "przyklad_42",
    "przyklad_43",
    "przyklad_44",
    "przyklad_46",
    "przyklad_48",
]


def _run(train_dir, case: str):
    doc = ingest.load(train_dir / case / "pelnomocnictwo.pdf", cfg=NO_OCR)
    res = extract(doc, load_registry()["pelnomocnictwo"])
    gt = json.loads((train_dir / case / "pelnomocnictwo.json").read_text(encoding="utf-8"))
    return res, gt


@pytest.mark.parametrize("case", CASES)
def test_pelnomocnictwo_matches_ground_truth(train_dir, case):
    res, gt = _run(train_dir, case)
    assert res.data == gt


def test_pelnomocnictwo_trace_has_concrete_paths_page_and_snippet(train_dir):
    res, _ = _run(train_dir, "przyklad_46")
    paths = {t.path for t in res.trace}
    assert {
        "mocodawca[0].data.nip",
        "mocodawca[1].data.krs",
        "mocodawca[1].podpisujacy[0].imie_nazwisko",
    } <= paths
    assert {"pelnomocnicy[0].imie_nazwisko", "pelnomocnicy[1].imie_nazwisko"} <= paths
    for t in res.trace:
        if t.method != "const":
            assert t.page == 0 and t.source_snippet
