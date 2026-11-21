"""Klasyfikator typu dokumentu sterowany cechami z YAML (E3-T1)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import uuid
from functools import cache
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from eval.score import gt_path_for_pdf, infer_doc_type, load_json
from odw2json import classify, ingest, pipeline
from odw2json.classify import features
from odw2json.config_loader import (
    ClassifyConfig,
    ClassifySettings,
    DocTypeConfig,
    ForeignTitles,
    load_classify_settings,
    load_registry,
)
from odw2json.contracts import Classification, Document
from odw2json.splits import load_splits
from odw2json.textnorm import collapse_spaced_letters

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data" / "train"
NO_OCR = {"ocr": {"enabled": False}}


def _doc(text: str) -> Document:
    return Document(path=Path("x.pdf"), text=text, pages=[text])


@cache
def _registry() -> dict[str, DocTypeConfig]:
    return load_registry()


def _case_pdfs() -> list[Path]:
    """Wszystkie PDF-y spraw tekstowych (dev + holdout) i negatywow (bez OCR skanow)."""
    sp = load_splits()
    pdfs: list[Path] = []
    for case in [*sp["dev"], *sp["holdout"]]:
        if case.startswith("skany/"):
            continue
        pdfs += sorted((TRAIN / case).glob("*.pdf"))
    for d in sp["negatives"]:
        pdfs += sorted((TRAIN / d).glob("*.pdf"))
    return pdfs


def _expected(pdf: Path) -> str | None:
    """Oczekiwany typ z GT (klucze szablonu), nie z nazwy pliku; brak GT = negatyw."""
    gt = gt_path_for_pdf(pdf)
    return infer_doc_type(load_json(gt), _registry()) if gt else None


@cache
def _loaded() -> list[tuple[Path, str | None, Document]]:
    return [(p, _expected(p), ingest.load(p, cfg=NO_OCR)) for p in _case_pdfs()]


# ----------------------------------------------------------- zwijanie liter


def test_collapse_spaced_title():
    assert collapse_spaced_letters("P E Ł N O M O C N I C T W O") == "PEŁNOMOCNICTWO"


def test_collapse_inside_sentence_keeps_neighbours():
    out = collapse_spaced_letters("Warszawa, dnia 1 maja\nP E Ł N O M O C N I C T W O\nMocodawca X")
    assert "PEŁNOMOCNICTWO" in out and "Warszawa, dnia 1 maja" in out and "Mocodawca X" in out


@pytest.mark.parametrize("text", ["a i w z", "w a z", "o b y", "sprawa a i w z dnia 5 maja", "I V X"])
def test_collapse_does_not_glue_short_runs_or_words(text):
    assert collapse_spaced_letters(text) == text


def test_collapse_does_not_touch_digits_or_normal_words():
    text = "KRS 1 2 3 4 5 6 oraz zwykly tekst a b"
    assert collapse_spaced_letters(text) == text


# ------------------------------------------------------------- cechy z YAML


def test_spaced_title_is_pelnomocnictwo():
    text = "P E Ł N O M O C N I C T W O\nMocodawca Firma sp. z o.o.\nul. Akacjowa 5\nKRS 9999669444"
    c = classify.classify(_doc(text), _registry())
    assert c.doc_type == "pelnomocnictwo"
    assert c.evidence


def test_empty_text_is_unknown():
    c = classify.classify(_doc(""), _registry())
    assert c.doc_type is None and c.confidence == 0.0


def test_generic_domain_words_do_not_make_przelew():
    text = "Rachunek bankowy. Kwota do zaplaty wynosi 100 zl. Przelew prosimy wykonac w terminie."
    assert classify.classify(_doc(text), _registry()).doc_type is None


def test_ted_and_jpk_are_unknown():
    reg = _registry()
    for name in ("2025_S 112-383751.pdf", "Broszura_JPK_FA(2).pdf"):
        doc = ingest.load(TRAIN / "negatywne" / name, cfg=NO_OCR)
        assert classify.classify(doc, reg).doc_type is None, name


def test_all_text_layer_cases_classified_correctly():
    reg = _registry()
    bad = []
    for pdf, expected, doc in _loaded():
        got = classify.classify(doc, reg).doc_type
        if got != expected:
            bad.append(f"{pdf.relative_to(TRAIN).as_posix()}: oczekiwano {expected}, jest {got}")
    assert not bad, "\n".join(bad)


def test_dataset_has_all_types_and_negatives():
    kinds = {e for _, e, _ in _loaded()}
    assert {"odwolanie", "pelnomocnictwo", "przelew", None} <= kinds


def test_evidence_and_confidence_for_positives():
    reg = _registry()
    for pdf, expected, doc in _loaded():
        c = classify.classify(doc, reg)
        if expected is None:
            assert c.doc_type is None
            continue
        assert c.evidence, pdf
        assert 0.0 < c.confidence <= 1.0, pdf
        assert set(c.scores) == set(reg)


def test_no_dependence_on_file_name():
    reg = _registry()
    for _pdf, _exp, doc in _loaded():
        renamed = dataclasses.replace(doc, path=Path(f"{uuid.uuid4().hex}.pdf"))
        assert classify.classify(renamed, reg) == classify.classify(doc, reg)


def test_renamed_copies_give_same_result(tmp_path):
    reg = _registry()
    sample = _loaded()[::17]
    assert len(sample) >= 8
    for i, (pdf, _exp, doc) in enumerate(sample):
        copy = tmp_path / f"{uuid.uuid4().hex}_{i}.pdf"
        shutil.copy(pdf, copy)
        got = classify.classify(ingest.load(copy, cfg=NO_OCR), reg)
        assert got == classify.classify(doc, reg), pdf


def test_header_limit_is_respected():
    cfg = {
        "id": "t",
        "output_template": "schemas/odwolanie.json",
        "classify": {"title": ["zebra"], "header_chars": 20, "min_score": 4},
    }
    reg = {"t": DocTypeConfig(**cfg)}
    assert classify.classify(_doc("zebra " + "x " * 50), reg).doc_type == "t"
    assert classify.classify(_doc("x " * 50 + "zebra"), reg).doc_type is None


def _reg(**classify_cfg) -> dict[str, DocTypeConfig]:
    cfg = {"id": "t", "output_template": "schemas/odwolanie.json", "classify": classify_cfg}
    return {"t": DocTypeConfig(**cfg)}


def test_required_any_excludes_type():
    reg = _reg(strong=["alfa", "beta"], required_any=["gamma", "re:\\bdelta\\d+"])
    assert classify.classify(_doc("alfa beta"), reg).doc_type is None
    assert classify.classify(_doc("alfa beta gamma"), reg).doc_type == "t"
    assert classify.classify(_doc("alfa beta delta12"), reg).doc_type == "t"


def test_patterns_add_weight_and_evidence():
    reg = _reg(patterns=[{"regex": r"zarzut nr \d+", "weight": 5}])
    c = classify.classify(_doc("Zarzut nr 3 dotyczy"), reg)
    assert c.doc_type == "t" and c.scores["t"] == 5.0
    assert any("zarzut" in e for e in c.evidence)


def test_custom_weights():
    reg = _reg(strong=["a1"], weak=["b1"], weights={"strong": 10, "weak": 0.5}, min_score=10)
    assert classify.classify(_doc("a1"), reg).scores["t"] == 10.0
    assert classify.classify(_doc("b1"), reg).doc_type is None


def test_min_margin_rejects_ambiguous():
    a = {
        "id": "a",
        "output_template": "schemas/odwolanie.json",
        "classify": {"strong": ["x1"], "min_score": 1, "min_margin": 2},
    }
    b = {"id": "b", "output_template": "schemas/przelew.json", "classify": {"strong": ["x1"]}}
    reg = {"a": DocTypeConfig(**a), "b": DocTypeConfig(**b)}
    c = classify.classify(_doc("x1 x1"), reg)
    assert c.doc_type is None
    assert any("margin" in e for e in c.evidence)


def test_confidence_formula():
    # wynik 8 (min_score 3), drugi typ 2: margines (8-2)/8 = 0.75, nasycenie min(1, 8/6) = 1
    assert features.confidence(8.0, 2.0, 3.0) == pytest.approx(0.75)
    # wynik rowny min_score, brak konkurenta: margines 1, nasycenie 3/6
    assert features.confidence(3.0, 0.0, 3.0) == pytest.approx(0.5)
    assert features.confidence(5.0, 5.0, 3.0) == 0.0
    assert 0.0 <= features.confidence(100.0, -4.0, 3.0) <= 1.0


# ---------------------------------------------------------------- walidacja


@pytest.mark.parametrize(
    "bad",
    [
        {"title": "pelnomocnictwo"},  # string zamiast listy
        {"strng": ["x"]},  # literowka w nazwie pola
        {"patterns": [{"regex": "(", "weight": 1}]},  # niepoprawny regex
        {"patterns": [{"weight": 1}]},  # brak regex
        {"required_any": ["re:["]},  # niepoprawny regex w required_any
        {"min_margin": -1},
        {"header_chars": 0},
        {"weights": {"title": "dużo"}},
        {"weights": {"nieznane": 1}},
        {"title_mode": "gdziekolwiek"},
        {"title_line_min_cover": 0},
        {"title_line_min_cover": 1.5},
        {"title_line_max_chars": 0},
        {"required_any": [{"all_of": []}]},  # pusta grupa
        {"required_any": [{"all_of": ["re:["]}]},  # niepoprawny regex w grupie
        {"required_any": [{"any_of": ["x"]}]},  # nieznany klucz grupy
        {"required_any": [{"all_of": ["x"], "extra": 1}]},
    ],
)
def test_invalid_classify_config_raises(bad):
    with pytest.raises(ValidationError):
        ClassifyConfig(**bad)


@pytest.mark.parametrize(
    "bad",
    [
        {"foreign_titles": {"weight": 5}},  # kara nie moze byc dodatnia
        {"foreign_titles": {"header_chars": 0}},
        {"foreign_titles": {"phrases": "wyrok"}},
        {"foreign_titles": {"fraza": ["wyrok"]}},
        {"foreign": {}},
    ],
)
def test_invalid_classify_settings_raise(bad):
    with pytest.raises(ValidationError):
        ClassifySettings(**bad)


def test_invalid_yaml_in_registry_gives_readable_error(tmp_path):
    cfg_dir = tmp_path / "config"
    (cfg_dir / "doctypes").mkdir(parents=True)
    shutil.copytree(ROOT / "config" / "schemas", cfg_dir / "schemas")
    bad = {
        "id": "x",
        "output_template": "schemas/odwolanie.json",
        "classify": {"patterns": [{"regex": "(", "weight": 1}]},
    }
    (cfg_dir / "doctypes" / "x.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    with pytest.raises(ValidationError) as ei:
        load_registry(cfg_dir)
    assert "regex" in str(ei.value)


def test_shipped_configs_use_new_features():
    reg = _registry()
    for name, cfg in reg.items():
        assert cfg.classify.title, name
    assert reg["przelew"].classify.required_any


# ---------------------------------------------------------------- trace


def test_evidence_in_trace(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    shutil.copy(TRAIN / "przyklad_02" / "pelnomocnictwo.pdf", inp / "cokolwiek.pdf")
    pipeline.run(
        inp,
        out,
        app_cfg={"unknown_output": "empty_object", "write_trace": True, "ingest": NO_OCR},
    )
    trace = json.loads((out / ".trace" / "cokolwiek.trace.json").read_text(encoding="utf-8"))
    c = trace["classification"]
    assert c["doc_type"] == "pelnomocnictwo"
    assert c["evidence"] and all(isinstance(e, str) for e in c["evidence"])
    assert 0 < c["confidence"] <= 1


def test_classification_evidence_defaults_to_empty():
    assert Classification("x", 1.0, "m").evidence == []


# ---------------------------------------------------------------- skany (OCR)


@pytest.mark.slow
@pytest.mark.ocr_live
def test_all_scans_classified_correctly():
    reg = _registry()
    scans = sorted((TRAIN / "skany").rglob("*.pdf"))
    assert len(scans) == 30
    bad = []
    for pdf in scans:
        got = classify.classify(ingest.load(pdf), reg).doc_type
        exp = _expected(pdf)
        if got != exp:
            bad.append(f"{pdf.relative_to(TRAIN).as_posix()}: oczekiwano {exp}, jest {got}")
    assert not bad, "\n".join(bad)


# ------------------------------------------------- title_mode: line (E3-T3)


def _title_reg(mode="line", **extra) -> dict[str, DocTypeConfig]:
    return _reg(title=["odwolanie"], title_mode=mode, header_chars=400, min_score=4, **extra)


def _title_score(text: str, mode="line", **extra) -> float:
    return classify.classify(_doc(text), _title_reg(mode, **extra)).scores["t"]


def test_title_line_standalone_scores():
    assert _title_score("Gmina X\nODWOŁANIE\nwobec czynności") == 4.0
    assert _title_score("Gmina X\n  Odwołanie:  \nwobec czynności") == 4.0  # interpunkcja przy brzegach


def test_title_line_spaced_letters_are_collapsed():
    assert _title_score("Gmina X\nO D W O Ł A N I E\nwobec czynności") == 4.0


def test_title_line_phrase_inside_sentence_does_not_score():
    assert _title_score("Pismo dotyczy tego, ze wnosimy odwolanie od wyboru oferty najkorzystniejszej") == 0.0
    # tryb anywhere (domyslny) zachowuje stare zachowanie
    assert _title_score("Pismo dotyczy tego, ze wnosimy odwolanie od wyboru", mode="anywhere") == 4.0
    assert ClassifyConfig().title_mode == "anywhere"


def test_title_line_requires_word_boundaries():
    assert _title_score("Gmina X\nodwolaniem\ntekst") == 0.0
    assert _title_score("Gmina X\nnieodwolanie\ntekst") == 0.0


def test_title_line_qualifier_must_be_short_and_dominant():
    assert _title_score("X\nodwolanie wobec czynnosci\ntekst", title_line_min_cover=0.3) == 4.0
    assert _title_score("X\nodwolanie wobec czynnosci\ntekst") == 0.0  # 9/26 < 0.6
    long_line = "odwolanie " + "x" * 80
    assert _title_score("X\n" + long_line, title_line_min_cover=0.05, title_line_max_chars=60) == 0.0


def test_title_line_counts_once_and_respects_header_chars():
    assert _title_score("odwolanie\nodwolanie\nodwolanie") == 4.0
    assert _title_score("x\n" * 300 + "odwolanie") == 0.0


def test_title_line_evidence_mentions_phrase():
    c = classify.classify(_doc("X\nodwolanie\n"), _title_reg())
    assert any(e.startswith("title") and "odwolanie" in e for e in c.evidence)


def test_title_line_multiword_phrase_tolerates_lost_spaces():
    reg = _reg(title=["potwierdzenie przelewu"], title_mode="line", min_score=1)

    def score(text: str) -> float:
        return classify.classify(_doc(text), reg).scores["t"]

    assert score("Bank X\nPotwierdzenie przelewu\n") == 4.0
    assert score("Bank X\nPotwierdzenieprzelewu\n") == 4.0  # OCR zgubil odstep
    assert score("Bank X\nP O T W I E R D Z E N I E P R Z E L E W U\n") == 4.0
    assert score("Bank X\nProsimy o potwierdzenie przelewu wadium w terminie 3 dni\n") == 0.0


# ------------------------------- wdrozone YAML-e po E3-T3 (przelew, odwolanie)

_IBAN_A = "11 1111 2222 3333 4444 5555 6666"
_IBAN_B = "12 3456 7890 1234 5678 9012 3456"


def _shipped(text: str) -> str | None:
    return classify.classify(_doc(text), _registry()).doc_type


def test_przelew_needs_title_or_bank_slip_labels_besides_iban():
    body = f"Rachunek: {_IBAN_B}\nKwota: 100,00 PLN\nTytul przelewu: oplata\nPrzelew krajowy\n"
    assert _shipped(body) is None  # IBAN + kwota bez tytulu i etykiet nadawca/odbiorca
    assert _shipped("Potwierdzenie przelewu\n" + body) == "przelew"  # tytul
    slip = f"Zleceniodawca: A\nRachunek nadawcy: {_IBAN_A}\nBeneficjent: B\nRachunek odbiorcy: {_IBAN_B}\n"
    assert _shipped(slip + "Kwota: 100,00 PLN\nTytul przelewu: oplata\nPrzelew krajowy\n") == "przelew"


def test_przelew_invoice_words_are_penalised():
    invoice_words = "Sprzedawca: A\nNabywca: B\nStawka VAT 23%\nDo zaplaty: 100,00 PLN\n"
    text = f"Potwierdzenie przelewu\nKwota: 100,00 PLN\nRachunek: {_IBAN_B}\nTytul przelewu: x\n"
    assert _shipped(text) == "przelew"
    assert _shipped(text + invoice_words) is None


def test_odwolanie_needs_title_line_or_structure():
    words = "Zamawiajacy narusza przepisy. Odwolujacy wskazuje zarzut.\n"
    words += "Krajowa Izba Odwolawcza rozpozna odwolanie.\n"
    prose = "Pismo do Zamawiajacego\n" + words + "Prawo zamowien publicznych. Wnosze o wyjasnienie.\n"
    assert _shipped(prose) is None  # slowa domenowe bez tytulu i struktury
    assert _shipped("ODWOLANIE\n" + prose) == "odwolanie"
    assert _shipped(prose + "Odwolujacy: Alfa sp. z o.o.\n") == "odwolanie"
    assert _shipped(prose + "Zarzut nr 1: naruszenie art. 16\n") == "odwolanie"


def test_foreign_header_blocks_otherwise_matching_documents():
    prose = "Zamawiajacy. Odwolujacy: Alfa. Zarzut nr 1. Krajowa Izba Odwolawcza. Odwolanie. Wnosze o.\n"
    assert _shipped("ODWOLANIE\n" + prose) == "odwolanie"
    assert _shipped("WYROK\nODWOLANIE\n" + prose) is None
    plain = classify.classify(_doc("ODWOLANIE\n" + prose), _registry()).scores["odwolanie"]
    sygn = classify.classify(_doc("Sygn. akt KIO 1/25\nODWOLANIE\n" + prose), _registry())
    assert sygn.scores["odwolanie"] == plain - 10  # kara jest miekka: silne odwolanie nadal przechodzi


# -------------------------------------------- foreign_titles (E3-T3)


def _foreign(phrases, weight=-10.0, header_chars=200) -> ClassifySettings:
    ft = ForeignTitles(weight=weight, header_chars=header_chars, phrases=phrases)
    return ClassifySettings(foreign_titles=ft)


def _score_with(text: str, settings: ClassifySettings) -> float:
    reg = _reg(strong=["alfa", "beta"], min_score=1)
    return classify.classify(_doc(text), reg, settings).scores["t"]


def test_foreign_title_line_penalises_every_type():
    reg = {
        "a": DocTypeConfig(
            id="a", output_template="schemas/odwolanie.json", classify={"strong": ["alfa"], "min_score": 1}
        ),
        "b": DocTypeConfig(
            id="b", output_template="schemas/przelew.json", classify={"strong": ["alfa"], "min_score": 1}
        ),
    }
    c = classify.classify(_doc("WYROK\nz dnia 1 maja\nalfa"), reg, _foreign(["wyrok"]))
    assert c.scores == {"a": -8.0, "b": -8.0} and c.doc_type is None
    assert any("wyrok" in e for e in c.evidence)


def test_foreign_title_only_at_line_start_and_word_boundary():
    settings = _foreign(["wyrok", "sygn. akt"])
    base = _score_with("alfa beta", settings)
    assert _score_with("To jest wyrok sadu\nalfa beta", settings) == base  # w srodku linii
    assert _score_with("Wyroku nie dotyczy\nalfa beta", settings) == base  # granica slowa
    assert _score_with("Sygn. akt KIO 1/25\nalfa beta", settings) == base - 10  # prefiks
    assert _score_with("  - WYROK:\nalfa beta", settings) == base - 10  # znaki przy brzegach


def test_foreign_title_counts_once_and_respects_header_chars():
    settings = _foreign(["wyrok", "postanowienie"], weight=-7)
    base = _score_with("alfa beta", settings)
    assert _score_with("Wyrok\nPostanowienie\nalfa beta", settings) == base - 7
    assert _score_with("x\n" * 150 + "Wyrok\nalfa beta", settings) == base  # dalej niz header_chars


def test_foreign_titles_ignore_diacritics_and_collapse_spaced_letters():
    base = _score_with("alfa beta", _foreign([]))
    assert (
        _score_with("Ogłoszenie o zamówieniu - roboty\nalfa beta", _foreign(["ogloszenie o zamowieniu"]))
        == base - 10
    )
    assert _score_with("W Y R O K\nalfa beta", _foreign(["wyrok"])) == base - 10


def test_classify_without_settings_uses_shipped_global_file():
    shipped = load_classify_settings()
    assert shipped.foreign_titles.weight < 0
    for phrase in ("wyrok", "postanowienie", "faktura", "sygn. akt", "wezwanie", "umowa"):
        assert phrase in shipped.foreign_titles.phrases
    c = classify.classify(_doc("WYROK\nalfa"), _reg(strong=["alfa"], min_score=1))
    assert c.scores["t"] == 2.0 + shipped.foreign_titles.weight


def test_missing_classify_yaml_means_no_penalty(tmp_path):
    assert load_classify_settings(tmp_path).foreign_titles.phrases == []


def test_classify_yaml_loaded_from_config_dir(tmp_path):
    (tmp_path / "classify.yaml").write_text(
        "foreign_titles:\n  weight: -5\n  header_chars: 100\n  phrases: [raport]\n", encoding="utf-8"
    )
    ft = load_classify_settings(tmp_path).foreign_titles
    assert (ft.weight, ft.header_chars, ft.phrases) == (-5.0, 100, ["raport"])


# ------------------------------------ required_any: grupy (E3-T3)


def test_required_group_needs_all_items():
    reg = _reg(strong=["alfa"], min_score=1, required_any=[{"all_of": ["gamma", "re:\\bdelta\\d+"]}])
    assert classify.classify(_doc("alfa gamma"), reg).doc_type is None
    assert classify.classify(_doc("alfa delta1"), reg).doc_type is None
    assert classify.classify(_doc("alfa gamma delta1"), reg).doc_type == "t"


def test_required_any_mixes_plain_items_and_groups():
    reg = _reg(strong=["alfa"], min_score=1, required_any=["epsilon", {"all_of": ["gamma", "delta"]}])
    assert classify.classify(_doc("alfa epsilon"), reg).doc_type == "t"
    assert classify.classify(_doc("alfa gamma delta"), reg).doc_type == "t"
    c = classify.classify(_doc("alfa gamma"), reg)
    assert c.doc_type is None and any("required_any" in e for e in c.evidence)


def test_required_group_title_token():
    reg = _reg(
        title=["potwierdzenie"],
        title_mode="line",
        strong=["alfa"],
        min_score=1,
        required_any=[{"all_of": ["re:\\d{4}", "@title"]}, {"all_of": ["nadawca", "odbiorca"]}],
    )
    assert classify.classify(_doc("Potwierdzenie\nalfa 1234"), reg).doc_type == "t"
    assert classify.classify(_doc("Potwierdzenie\nalfa"), reg).doc_type is None  # brak cyfr
    assert classify.classify(_doc("Pismo\nalfa 1234"), reg).doc_type is None  # brak tytulu
    assert classify.classify(_doc("Pismo\nalfa nadawca odbiorca"), reg).doc_type == "t"


_ODW_BEZ_TYTULU = """Warszawa, 10 marca 2025 r.

Wykonawca:
Budimex Przykład sp. z o.o.
ul. Testowa 1, 00-001 Warszawa

Zamawiający:
Gmina Przykładowo

Do Prezesa Krajowej Izby Odwoławczej
ul. Postępowa 17a, 02-676 Warszawa

Działając w imieniu Wykonawcy, na podstawie art. 505 ustawy Prawo zamówień publicznych,
niniejszym wnoszę odwołanie od czynności Zamawiającego polegającej na odrzuceniu oferty.

Zarzut 1. Naruszenie art. 226 ust. 1 pkt 5 ustawy Pzp przez bezpodstawne odrzucenie oferty.
Zarzut 2. Naruszenie art. 16 ustawy Pzp przez naruszenie zasady równego traktowania.

Wnoszę o uwzględnienie odwołania i nakazanie unieważnienia czynności odrzucenia oferty.
"""

_PISMO_DO_ZAMAWIAJACEGO = """Warszawa, 10 marca 2025 r.

Gmina Przykładowo
Zamawiający

W związku z informacją o odrzuceniu oferty prosimy o udostępnienie protokołu postępowania.
Rozważamy skorzystanie ze środków ochrony prawnej, w tym odwołanie do Krajowej Izby Odwoławczej,
o ile wyjaśnienia Zamawiającego nie rozwieją naszych wątpliwości co do ustawy Prawo zamówień publicznych.

Z poważaniem
Wykonawca
"""


def test_odwolanie_without_title_or_label_recognized_by_filing_act():
    c = classify.classify(_doc(_ODW_BEZ_TYTULU), _registry())
    assert c.doc_type == "odwolanie"


def test_letter_mentioning_odwolanie_without_filing_act_is_unknown():
    assert classify.classify(_doc(_PISMO_DO_ZAMAWIAJACEGO), _registry()).doc_type is None
