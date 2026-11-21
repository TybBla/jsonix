"""E3-T2: odpornosc klasyfikatora na dokumenty spoza puli i warianty pozytywow (bez OCR, bez zapisu PDF).

Negatywy: syntetyczne teksty z podchwytliwymi slowami domenowymi (tests/fixtures/classify/neg_*.txt).
Pozytywy: syntetyczne (pos_*.txt) oraz warianty prawdziwych tekstow z dev, w pamieci
(tylko 1. strona, szum OCR, tytul malymi literami / rozstrzelony, dodatkowe lamania wierszy).
"""

from __future__ import annotations

import random
import re
from functools import cache
from pathlib import Path

import pytest

from odw2json import classify, ingest
from odw2json.config_loader import DocTypeConfig, load_registry
from odw2json.contracts import Document
from odw2json.splits import load_splits

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data" / "train"
FIXTURES = Path(__file__).parent / "fixtures" / "classify"
NO_OCR = {"ocr": {"enabled": False}}

# Znane niepowodzenia: id przypadku -> powod (xfail strict - ma byc widoczne i pilnowane).
# Po E3-T3 (title_mode: line, foreign_titles, wymagania przelewu) lista jest pusta; nowy znany blad
# dopisujemy tu zamiast oslabiac test.
KNOWN_XFAIL: dict[str, str] = {}

# Regexy tytulu per typ (podmieniany fragment w pierwszych 1500 znakach tekstu).
TITLE_RE = {
    "odwolanie": r"(?im)^[ \t]*(odwo.anie)[ \t]*$",
    "pelnomocnictwo": r"(?im)^[ \t]*(pe.nomocnictwo)[ \t]*$",
    "przelew": r"(?i)(potwierdzenie (?:realizacji polecenia )?(?:przelewu|transakcji|operacji))",
}
REAL_CASES = ["przyklad_01", "przyklad_05", "przyklad_12"]
REAL_DOCS = [
    ("odwolanie", "odwolanie"),
    ("pelnomocnictwo", "pelnomocnictwo"),
    ("przelew", "potwierdzenie_przelewu"),
]


@cache
def _registry() -> dict[str, DocTypeConfig]:
    return load_registry()


def _doc(text: str, pages: list[str] | None = None) -> Document:
    return Document(path=Path("x.pdf"), text=text, pages=pages or [text])


@cache
def _real(case: str, stem: str) -> Document:
    return ingest.load(TRAIN / case / f"{stem}.pdf", cfg=NO_OCR)


# ------------------------------------------------------------------ warianty


def _first_page(doc: Document) -> str:
    return doc.pages[0]


def _ocr_noise(text: str, seed: int = 20260101) -> str:
    """Diakrytyki -> ASCII (ł->l, Ę->E, ó->o...) i 'o'->'0' w 3% liter 'o' (deterministycznie)."""
    rng = random.Random(seed)
    table = str.maketrans("łąęóśćźżń" + "ŁĄĘÓŚĆŹŻŃ", "laeosczzn" + "LAEOSCZZN")
    out = []
    for word in text.translate(table).split(" "):
        if word.isdigit():
            out.append(word)
            continue
        chars = list(word)
        for i, ch in enumerate(chars):
            if ch == "o" and len(word) > 1 and rng.random() < 0.03:
                chars[i] = "0"
        out.append("".join(chars))
    return " ".join(out)


def _map_title(text: str, doc_type: str, fn) -> str | None:
    head, tail = text[:1500], text[1500:]
    m = re.search(TITLE_RE[doc_type], head)
    if not m:
        return None
    return head[: m.start(1)] + fn(m.group(1)) + head[m.end(1) :] + tail


def _lower_title(text: str, doc_type: str) -> str | None:
    return _map_title(text, doc_type, str.lower)


def _spaced_title(text: str, doc_type: str) -> str | None:
    return _map_title(text, doc_type, lambda t: " ".join(t.upper().replace(" ", "")))


def _extra_breaks(text: str, every: int = 40) -> str:
    """Lamanie wiersza co ~40 znakow (w najblizszej spacji), jak w zlej ekstrakcji kolumn."""
    out, col = [], 0
    for tok in re.split(r"(\s+)", text):
        if "\n" in tok:
            col = 0
            out.append(tok)
            continue
        if tok.isspace():
            if col >= every:
                out.append("\n")
                col = 0
            else:
                out.append(tok)
                col += len(tok)
            continue
        out.append(tok)
        col += len(tok)
    return "".join(out)


VARIANTS = {
    "first_page": lambda d, t: _first_page(d),
    "ocr_noise": lambda d, t: _ocr_noise(d.text),
    "title_lower": lambda d, t: _lower_title(d.text, t),
    "title_spaced": lambda d, t: _spaced_title(d.text, t),
    "extra_breaks": lambda d, t: _extra_breaks(d.text),
}


def _real_variant_params():
    params = []
    for case in REAL_CASES:
        for doc_type, stem in REAL_DOCS:
            for vname in VARIANTS:
                cid = f"{case}-{doc_type}-{vname}"
                marks = (
                    [pytest.mark.xfail(strict=True, reason=KNOWN_XFAIL[cid])] if cid in KNOWN_XFAIL else []
                )
                params.append(pytest.param(case, doc_type, stem, vname, id=cid, marks=marks))
    return params


def _fixture_params(prefix: str):
    params = []
    for p in sorted(FIXTURES.glob(f"{prefix}_*.txt")):
        marks = [pytest.mark.xfail(strict=True, reason=KNOWN_XFAIL[p.stem])] if p.stem in KNOWN_XFAIL else []
        params.append(pytest.param(p, id=p.stem, marks=marks))
    return params


# -------------------------------------------------------------------- testy


def test_dev_cases_used_are_in_dev():
    dev = set(load_splits()["dev"])
    assert set(REAL_CASES) <= dev


@pytest.mark.parametrize("path", _fixture_params("neg"))
def test_synthetic_negatives_are_unknown(path: Path):
    c = classify.classify(_doc(path.read_text(encoding="utf-8")), _registry())
    assert c.doc_type is None, f"{path.name}: {c.doc_type} scores={c.scores} evidence={c.evidence}"


@pytest.mark.parametrize("path", _fixture_params("pos"))
def test_synthetic_positives(path: Path):
    expected = path.stem.removeprefix("pos_").split("_")[0]
    c = classify.classify(_doc(path.read_text(encoding="utf-8")), _registry())
    assert c.doc_type == expected, f"{path.name}: {c.doc_type} scores={c.scores} evidence={c.evidence}"


@pytest.mark.parametrize("case,doc_type,stem,variant", _real_variant_params())
def test_real_text_variants_keep_type(case, doc_type, stem, variant):
    doc = _real(case, stem)
    text = VARIANTS[variant](doc, doc_type)
    if text is None:
        pytest.skip(f"brak linii tytulowej w {case}/{stem} - wariant nie dotyczy")
    c = classify.classify(_doc(text), _registry())
    assert c.doc_type == doc_type, f"{c.doc_type} scores={c.scores} evidence={c.evidence}"


def test_unmodified_real_texts_are_baseline_ok():
    """Kontrola: bez przeksztalcen te same dokumenty sa klasyfikowane poprawnie."""
    for case in REAL_CASES:
        for doc_type, stem in REAL_DOCS:
            c = classify.classify(_real(case, stem), _registry())
            assert c.doc_type == doc_type, (case, stem, c.scores)


def test_noise_is_deterministic():
    t = "Rozstrzygnięcie ofert odwołującego oraz zamówienia " * 20
    assert _ocr_noise(t) == _ocr_noise(t)


# --------------------------------- sygnatura sprawy nie zmienia typu (poprawki po review E3)

SIGNATURE_PREFIXES = ["Sygn. akt KIO 1234/26\n", "KIO 1234/26\n"]
PER_TYPE = 12


@cache
def _dev_positives() -> list[tuple[str, str, Document]]:
    """Po PER_TYPE pozytywow tekstowych z dev na typ: (id, typ, dokument)."""
    out: list[tuple[str, str, Document]] = []
    counts = {t: 0 for t, _ in REAL_DOCS}
    for case in load_splits()["dev"]:
        if case.startswith("skany/"):
            continue
        for doc_type, stem in REAL_DOCS:
            if counts[doc_type] < PER_TYPE and (TRAIN / case / f"{stem}.pdf").exists():
                out.append((f"{case}/{stem}", doc_type, _real(case, stem)))
                counts[doc_type] += 1
    return out


def test_signature_sample_covers_all_types():
    counts = {t: sum(1 for _, dt, _ in _dev_positives() if dt == t) for t, _ in REAL_DOCS}
    assert all(n >= 10 for n in counts.values()), counts


@pytest.mark.parametrize("prefix", SIGNATURE_PREFIXES, ids=["sygn_akt", "kio_only"])
def test_case_signature_line_does_not_change_type(prefix):
    bad = []
    for ident, doc_type, doc in _dev_positives():
        got = classify.classify(_doc(prefix + doc.text), _registry())
        if got.doc_type != doc_type:
            bad.append(f"{ident}: oczekiwano {doc_type}, jest {got.doc_type} scores={got.scores}")
    assert not bad, f"{len(bad)} z {len(_dev_positives())} zmienilo typ:\n" + "\n".join(bad)
