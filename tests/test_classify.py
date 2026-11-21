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
from odw2json.config_loader import ClassifyConfig, DocTypeConfig, load_registry
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
    ],
)
def test_invalid_classify_config_raises(bad):
    with pytest.raises(ValidationError):
        ClassifyConfig(**bad)


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
