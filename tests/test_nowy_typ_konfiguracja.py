"""E10: nowy typ dokumentu i nowe pole WYŁĄCZNIE konfiguracją (0 linii kodu).

Przykład: examples/nowy-typ/orzeczenie_kio (orzeczenie KIO: wyrok/postanowienie). Test kopiuje config/,
nakłada pliki przykładu i uruchamia ten sam potok co CLI — bez żadnej zmiany w odw2json/.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from odw2json import classify, extract, pipeline
from odw2json.config_loader import load_app_config, load_registry
from odw2json.contracts import Document

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "nowy-typ" / "orzeczenie_kio"
KIO_PDF = ROOT / "data" / "train" / "negatywne" / "KIO_KIO 2617-21.pdf"
P01 = ROOT / "data" / "train" / "przyklad_01"


@pytest.fixture
def config_with_new_type(tmp_path) -> Path:
    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    shutil.copytree(EXAMPLE / "config", cfg, dirs_exist_ok=True)
    return cfg


def _run(tmp_path: Path, registry: dict, pdfs: list[Path]) -> Path:
    case = tmp_path / "in" / "sprawa"
    case.mkdir(parents=True)
    for pdf in pdfs:
        shutil.copy(pdf, case / pdf.name)
    out = tmp_path / "out"
    rep = pipeline.run(tmp_path / "in", out, app_cfg=load_app_config(), registry=registry)
    assert not rep.errors, rep.errors
    return out / "sprawa"


def test_example_is_configuration_only():
    files = [p for p in EXAMPLE.rglob("*") if p.is_file()]
    assert files
    assert {p.suffix for p in files} <= {".yaml", ".json", ".md"}, "przykład = konfiguracja, bez kodu"


def test_new_type_is_not_active_in_delivered_config():
    """Wg UZP orzeczenia KIO to dokumenty spoza typów ({}); przykład nie może trafić do config/."""
    assert "orzeczenie_kio" not in load_registry()


def test_new_type_from_configuration_end_to_end(tmp_path, config_with_new_type):
    registry = load_registry(config_with_new_type)
    assert set(registry) == {"odwolanie", "pelnomocnictwo", "przelew", "orzeczenie_kio"}
    out = _run(tmp_path, registry, [KIO_PDF])
    data = json.loads((out / f"{KIO_PDF.stem}.json").read_text(encoding="utf-8"))
    assert data == {
        "OrzeczenieKIO": {
            "sygnatura": "KIO 2617/21",
            "rodzaj": "postanowienie",
            "data": "2021-09-20",
            "przewodniczacy": "Ewa Kisiel",
            "odwolujacy": "TAMEXOBIEKTY SPORTOWE S.A.",
            "zamawiajacy": "Gmina Cieszyn",
            "rozstrzygniecie": "odrzuca",
            "kwota_wpisu": 10000.0,
        }
    }
    trace = json.loads((out.parent / ".trace" / "sprawa" / f"{KIO_PDF.stem}.trace.json").read_text("utf-8"))
    sources = {t["path"]: t for t in trace["trace"]}
    sig = sources["OrzeczenieKIO.sygnatura"]
    assert sig["page"] == 0 and sig["source_snippet"], "trace z miejscem w dokumencie (GUI)"


def test_existing_types_unchanged_by_new_type(tmp_path, config_with_new_type):
    base = _run(tmp_path / "base", load_registry(), list(P01.glob("*.pdf")))
    extended = _run(tmp_path / "ext", load_registry(config_with_new_type), list(P01.glob("*.pdf")))
    for pdf in P01.glob("*.pdf"):
        name = f"{pdf.stem}.json"
        same = json.loads((extended / name).read_text("utf-8")) == json.loads(
            (base / name).read_text("utf-8")
        )
        assert same, name


def test_new_type_on_other_wording(config_with_new_type):
    """Wyrok (nie postanowienie), inne strony i rozstrzygnięcie — te same reguły z YAML."""
    text = (
        "Sygn. akt: KIO 512/24\nWYROK\nz dnia 5 marca 2024 r.\n"
        "Krajowa Izba Odwoławcza - w składzie:\nPrzewodniczący: Anna Nowak-Kowalska\nProtokolant: Jan Lis\n"
        "po rozpoznaniu na rozprawie w dniu 4 marca 2024 r. w Warszawie odwołania wniesionego do Prezesa "
        "Krajowej Izby Odwoławczej przez wykonawcę: Budex Sp. z o.o. z siedzibą w Poznaniu w postępowaniu "
        "prowadzonym przez Miasto Kraków z siedzibą w Krakowie,\norzeka:\n1. oddala odwołanie;\n"
        "2. kosztami postępowania obciąża wykonawcę i zalicza w poczet kosztów postępowania odwoławczego "
        "kwotę 7 500,00 zł uiszczoną tytułem wpisu od odwołania.\nUzasadnienie\n"
    )
    registry = load_registry(config_with_new_type)
    doc = Document(path=Path("wyrok.pdf"), text=text, pages=[text], page_offsets=[0])
    cls = classify.classify(doc, registry)
    assert cls.doc_type == "orzeczenie_kio"
    got = extract.extract(doc, registry["orzeczenie_kio"]).data["OrzeczenieKIO"]
    assert got["rodzaj"] == "wyrok" and got["rozstrzygniecie"] == "oddala"
    assert got["sygnatura"] == "KIO 512/24" and got["data"] == "2024-03-05"
    assert got["przewodniczacy"] == "Anna Nowak-Kowalska"
    assert got["odwolujacy"] == "Budex Sp. z o.o." and got["zamawiajacy"] == "Miasto Kraków"
    assert got["kwota_wpisu"] == 7500.0


def test_new_field_in_existing_type_from_configuration(tmp_path, config_with_new_type):
    """Nowe pole = klucz w szablonie + reguła w YAML (tu: waluta przelewu)."""
    cfg = config_with_new_type
    schema_path = cfg / "schemas" / "przelew.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["przelew_bankowy"]["waluta"] = None
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    yaml_path = cfg / "doctypes" / "przelew.yaml"
    doctype = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    doctype["fields"]["przelew_bankowy.waluta"] = {"extract": [{"regex": r"(?P<v>\bPLN\b|\bEUR\b)"}]}
    yaml_path.write_text(yaml.safe_dump(doctype, allow_unicode=True, sort_keys=False), encoding="utf-8")
    out = _run(tmp_path, load_registry(cfg), [P01 / "potwierdzenie_przelewu.pdf"])
    data = json.loads((out / "potwierdzenie_przelewu.json").read_text("utf-8"))
    assert data["przelew_bankowy"]["waluta"] == "PLN"
    assert list(data["przelew_bankowy"])[-1] == "waluta", "kolejność kluczy wg szablonu"
