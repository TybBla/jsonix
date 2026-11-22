"""Wariant hybrydowy: LLM uzupełnia tylko pola null po regułach, na wycinku tekstu. Bez sieci."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odw2json import llm_fill, pipeline
from odw2json.config_loader import ROOT_DIR, load_registry
from odw2json.contracts import Document, ExtractionResult


class FakeLLM:
    """Zamiast LLMClient: zapamiętuje zapytania, zwraca przygotowaną odpowiedź."""

    def __init__(self, response: dict | Exception):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def _doc(text: str) -> Document:
    return Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0])


PRZELEW = (
    "Potwierdzenie przelewu\n"
    "Data operacji: 2025-10-09\n"
    "Kwota: 10 000,00 PLN\n"
    "Z rachunku: 50 8020 5460 0000 5888 7442 4400\n"
    "Na rachunek: 60 1010 1010 0081 3622 3100 0000\n"
    "Tytuł: WPIS OD ODWOŁANIA ZP.1.2025\n"
    "Numer transakcji: TRX-778899\n"
)


def _res(cfg, **values) -> ExtractionResult:
    data = cfg.template()
    for k, v in values.items():
        data["przelew_bankowy"][k] = v
    return ExtractionResult(doc_type=cfg.id, data=data, trace=[])


def test_null_paths_skips_filled_and_derived(registry):
    cfg = registry["odwolanie"]
    data = cfg.template()
    data["OdwolanieKIO"]["data"] = "2025-10-13"
    paths = llm_fill.null_paths(data, cfg)
    assert "OdwolanieKIO.data" not in paths
    assert "OdwolanieKIO.czynnosc_opis" not in paths  # pole wyliczane ze słownika
    assert "Odwolujacy[0].nip" in paths and "Zamawiajacy[0].regon" in paths


def test_fills_only_null_fields_and_validates(registry):
    cfg = registry["przelew"]
    res = _res(cfg, data_operacji="2025-10-09", kwota=10000.0)
    fake = FakeLLM(
        {
            "przelew_bankowy.data_operacji": "2099-01-01",  # nie był null: ignorujemy
            "przelew_bankowy.numer_transakcji": "TRX-778899",
            "przelew_bankowy.na_rachunek": "60 1010 1010 0081 3622 3100 0000",
            "przelew_bankowy.tytul": None,
        }
    )
    filler = llm_fill.LLMFiller(fake)
    filled = filler.fill(_doc(PRZELEW), res, cfg)
    pb = res.data["przelew_bankowy"]
    assert pb["data_operacji"] == "2025-10-09"
    assert pb["numer_transakcji"] == "TRX-778899"
    assert pb["na_rachunek"] == "60101010100081362231000000"  # normalizator iban z YAML
    assert pb["tytul"] is None
    assert set(filled) == {"przelew_bankowy.numer_transakcji", "przelew_bankowy.na_rachunek"}
    assert {t.method for t in res.trace} == {"llm"}
    assert len(fake.calls) == 1
    asked = json.loads(fake.calls[0][1])["pola"]
    assert "przelew_bankowy.data_operacji" not in [p["pole"] for p in asked]


def test_rejects_values_not_grounded_in_text(registry):
    cfg = registry["przelew"]
    res = _res(cfg)
    fake = FakeLLM(
        {
            "przelew_bankowy.z_rachunku": "11 2222 3333 4444 5555 6666 7777",  # brak w tekście
            "przelew_bankowy.numer_transakcji": "ZMYSLONY-1",
            "przelew_bankowy.kwota": 10000,
        }
    )
    filler = llm_fill.LLMFiller(fake)
    filler.fill(_doc(PRZELEW), res, cfg)
    pb = res.data["przelew_bankowy"]
    assert pb["z_rachunku"] is None and pb["numer_transakcji"] is None
    assert pb["kwota"] == 10000.0
    assert filler.stats["rejected"] == 2


def test_slice_is_a_window_not_whole_document(registry):
    cfg = registry["przelew"]
    filler_text = "lorem ipsum dolor sit amet " * 400
    text = filler_text + "\nNumer transakcji: TRX-1\n" + filler_text
    res = _res(
        cfg, data_operacji="2025-10-09", kwota=1.0, z_rachunku="1" * 26, na_rachunek="2" * 26, tytul="abc"
    )
    fake = FakeLLM({"przelew_bankowy.numer_transakcji": "TRX-1"})
    llm_fill.LLMFiller(fake).fill(_doc(text), res, cfg)
    user = json.loads(fake.calls[0][1])
    assert "TRX-1" in user["wycinek"]
    assert len(user["wycinek"]) < len(text) / 4


def test_field_without_hint_in_text_is_not_asked(registry):
    cfg = registry["przelew"]
    res = _res(
        cfg, data_operacji="2025-10-09", kwota=1.0, z_rachunku="1" * 26, na_rachunek="2" * 26, tytul="abc"
    )
    fake = FakeLLM({})
    llm_fill.LLMFiller(fake).fill(_doc("Potwierdzenie przelewu\nKwota 1,00 PLN\n"), res, cfg)
    assert fake.calls == []  # numer_transakcji: brak słowa kluczowego -> bez zapytania


def test_llm_error_keeps_rule_result(registry):
    cfg = registry["przelew"]
    res = _res(cfg, data_operacji="2025-10-09")
    filler = llm_fill.LLMFiller(FakeLLM(RuntimeError("429")))
    assert filler.fill(_doc(PRZELEW), res, cfg) == []
    assert res.data["przelew_bankowy"]["data_operacji"] == "2025-10-09"
    assert filler.stats["errors"] == 1


def test_derived_field_follows_llm_value(registry):
    cfg = registry["odwolanie"]
    data = cfg.template()
    res = ExtractionResult(doc_type=cfg.id, data=data, trace=[])
    text = "ODWOŁANIE\nWarszawa, dnia 13.10.2025\nZarzut 1: odrzucenie oferty Odwołującego.\n"
    fake = FakeLLM({"OdwolanieKIO.czynnosc_powod_id": 1})
    llm_fill.LLMFiller(fake).fill(_doc(text), res, cfg)
    assert data["OdwolanieKIO"]["czynnosc_powod_id"] == 1
    assert data["OdwolanieKIO"]["czynnosc_opis"] == "Decyzja o odrzuceniu oferty"


def test_from_app_config_disabled_by_default():
    assert llm_fill.from_app_config({"llm_enabled": False}) is None
    assert llm_fill.from_app_config({}) is None


def test_pipeline_uses_filler_only_when_given(tmp_path, registry, monkeypatch):
    calls = []

    class Spy:
        def fill(self, doc, res, cfg):
            calls.append(cfg.id)
            return []

    pdf = next((ROOT_DIR / "data" / "train").glob("przyklad_01/*.pdf"))
    pipeline.process_file_ex(pdf, registry)
    assert calls == []
    pipeline.process_file_ex(pdf, registry, llm_filler=Spy())
    assert len(calls) == 1


def test_prompts_describe_only_template_fields(registry):
    for cfg in registry.values():
        spec = llm_fill.load_prompt(cfg)
        assert spec.system.strip() and "TODO" not in spec.system
        for path in spec.fields:
            assert path in cfg.fields, (cfg.id, path)
            assert cfg.fields[path].derived is None


# --- kontrola „jest w tekście” (recenzja: zmyślone daty, e-maile, odmiana imion, małe kwoty)


def _spec(registry, doc_type, path):
    return registry[doc_type].fields[path]


def test_grounded_date_must_match_a_date_in_text(registry):
    spec = _spec(registry, "odwolanie", "OdwolanieKIO.czynnosc_dzien")
    text = "Warszawa, dnia 13.10.2025 r. Zarzut 1: czynność z dnia 1 października 2025 r."
    assert llm_fill.grounded("2025-10-13", text, spec)
    assert llm_fill.grounded("2025-10-01", text, spec)  # data słowna
    assert not llm_fill.grounded("2025-10-31", text, spec)  # ten sam rok, zmyślony dzień


def test_grounded_names_in_other_grammatical_case(registry):
    spec = _spec(registry, "pelnomocnictwo", "pelnomocnicy[].imie_nazwisko")
    assert llm_fill.grounded("Paweł Nowak", "udzielam pełnomocnictwa adw. Pawłowi Nowakowi", spec)
    assert llm_fill.grounded("Anna Kowalska", "reprezentowany przez adw. Annę Kowalską", spec)
    assert llm_fill.grounded("Marek Dudek", "w imieniu Marka Dudka", spec)
    assert llm_fill.grounded("Ewa Nowak", "przez Ewę Nowak", spec)
    assert not llm_fill.grounded("Jan Wiśniewski", "przez Ewę Nowak", spec)


def test_grounded_email_must_be_exact(registry):
    spec = _spec(registry, "odwolanie", "Odwolujacy[].pelnomocnik.mail")
    text = "adw. Jan Kowalski, Kancelaria Kowalski i Wspólnicy, e-mail: biuro@kowalski.pl"
    assert llm_fill.grounded("biuro@kowalski.pl", text, spec)
    assert not llm_fill.grounded("j.kowalski@kancelaria-kowalski.pl", text, spec)


def test_grounded_amounts_including_small_ones(registry):
    spec = _spec(registry, "przelew", "przelew_bankowy.kwota")
    assert llm_fill.grounded(50.0, "Kwota: 50,00 zł", spec)
    assert llm_fill.grounded(10000.0, "Kwota 10 000,00 PLN", spec)
    assert not llm_fill.grounded(1000.0, "rachunek 12 1010 0000 1234, kwota 17,00 zł", spec)


def test_grounded_ted_number_in_reversed_notation(registry):
    spec = _spec(registry, "odwolanie", "ZamowieniePubliczne.numer_ted")
    assert llm_fill.grounded("641651-2025", "Dz.Urz. UE 2025/S 123-641651", spec)
    assert not llm_fill.grounded("641652-2025", "Dz.Urz. UE 2025/S 123-641651", spec)


def test_prepare_float_in_int_field(registry):
    spec = _spec(registry, "odwolanie", "OdwolanieKIO.czynnosc_powod_id")
    assert llm_fill._prepare(1.0, spec) == 1
    assert llm_fill._prepare(1.5, spec) is None


def test_closed_value_list_skips_text_check(registry):
    cfg = registry["pelnomocnictwo"]
    data = cfg.template()
    data["mocodawca"][0]["data"]["nazwa"] = "ABC Sp. z o.o."
    res = ExtractionResult(doc_type=cfg.id, data=data, trace=[])
    text = "PEŁNOMOCNICTWO\nABC Sp. z o.o. z siedzibą w Warszawie udziela pełnomocnictwa\n"
    fake = FakeLLM({"mocodawca[0].data.typ": "osoba_prawna"})
    llm_fill.LLMFiller(fake).fill(_doc(text), res, cfg)
    assert data["mocodawca"][0]["data"]["typ"] == "osoba_prawna"
    fake2 = FakeLLM({"mocodawca[0].data.typ": "spółka"})
    data["mocodawca"][0]["data"]["typ"] = None
    llm_fill.LLMFiller(fake2).fill(_doc(text), res, cfg)
    assert data["mocodawca"][0]["data"]["typ"] is None


def test_field_whose_window_does_not_fit_is_not_asked(registry):
    cfg = registry["przelew"]
    res = _res(cfg, data_operacji="2025-10-09", kwota=1.0, z_rachunku="1" * 26, na_rachunek="2" * 26)
    far = "x " * 5000
    text = "Potwierdzenie przelewu\n" + far + "Numer transakcji: TRX-1\n" + far + "Tytuł: WPIS\n"
    fake = FakeLLM({})
    filler = llm_fill.LLMFiller(fake, {"max_chars": 1500})  # mieści się nagłówek + jedno okno
    filler.fill(_doc(text), res, cfg)
    asked = [p["pole"] for p in json.loads(fake.calls[0][1])["pola"]]
    assert asked == ["przelew_bankowy.numer_transakcji"]
    assert filler.stats["fields_dropped_budget"] == 1


def test_prompt_descriptions_not_cut_by_yaml_comment(registry):
    for cfg in registry.values():
        for path, hint in llm_fill.load_prompt(cfg).fields.items():
            assert hint.opis.rstrip().endswith((".", ")")), (cfg.id, path, hint.opis)


def test_usage_and_on_fill_hook(registry):
    cfg = registry["przelew"]
    res = _res(cfg, data_operacji="2025-10-09", kwota=10000.0)
    fake = FakeLLM({"przelew_bankowy.numer_transakcji": "TRX-778899"})
    fake.usage = {"calls": 0}
    orig = fake.complete_json

    def counting(system, user):
        fake.usage["calls"] += 1
        return orig(system, user)

    fake.complete_json = counting
    seen = []
    filler = llm_fill.LLMFiller(fake)
    filler.on_fill = lambda doc, path, value: seen.append((path, value))
    filler.fill(_doc(PRZELEW), res, cfg)
    assert seen == [("przelew_bankowy.numer_transakcji", "TRX-778899")]
    assert filler.stats["usage_calls"] == 1
