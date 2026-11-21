"""Testy miary pokrycia wartosci GT w tekscie wyciagnietym z PDF (eval.ingest_coverage)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval.ingest_coverage import Coverage, coverage_for_doc
from odw2json.config_loader import ROOT_DIR

TRAIN = ROOT_DIR / "data" / "train"


def test_exact_hit():
    gt = {"Odwolujacy": [{"nazwa": "Belmoria Rozwiązania S.A."}]}
    cov = coverage_for_doc("Odwołujący: Belmoria  Rozwiązania\nS.A. z siedzibą", gt, "odwolanie")
    assert (cov.found, cov.found_fuzzy, cov.total, cov.missing) == (1, 0, 1, [])
    assert cov.rate == 1.0


def test_normalization_quotes_dashes_case():
    gt = {"ZamowieniePubliczne": {"tytul": "Dostawa „sprzętu” – etap II"}}
    cov = coverage_for_doc('DOSTAWA "SPRZĘTU" - ETAP II', gt, "odwolanie")
    assert cov.found == 1


def test_nip_with_dashes_and_spaces():
    gt = {"Odwolujacy": [{"nip": "9999284065"}]}
    assert coverage_for_doc("NIP: 999-928-40-65", gt, "odwolanie").found == 1
    assert coverage_for_doc("NIP: 999 928 40 65", gt, "odwolanie").found == 1


def test_iban_with_spaces():
    gt = {"przelew_bankowy": {"na_rachunek": "68438223049992295262834736"}}
    text = "PL 68 4382 2304 9992 2952 6283 4736"
    assert coverage_for_doc(text, gt, "przelew").found == 1


def test_digits_do_not_match_across_unrelated_numbers():
    gt = {"Odwolujacy": [{"krs": "1234"}]}
    assert coverage_for_doc("12 34", gt, "odwolanie").found == 1
    cov = coverage_for_doc("12 x 34", gt, "odwolanie")
    assert cov.found == 0
    assert cov.missing == [("Odwolujacy[].krs", "1234")]


def test_digits_not_embedded_in_longer_number():
    gt = {"Odwolujacy": [{"nip": "1234"}]}
    assert coverage_for_doc("nr 991234 5", gt, "odwolanie").found == 0


def test_name_in_genitive_is_fuzzy():
    gt = {"pelnomocnicy": [{"imie_nazwisko": "Aleksandra Marciniak", "pesel": None}]}
    cov = coverage_for_doc("pełnomocnictwa dla Aleksandry Marciniaka", gt, "pelnomocnictwo")
    assert (cov.found, cov.found_fuzzy, cov.total) == (0, 1, 1)
    assert cov.rate == 0.0
    assert cov.rate_with_fuzzy == 1.0
    assert cov.missing == []


def test_fuzzy_requires_every_word():
    gt = {"pelnomocnicy": [{"imie_nazwisko": "Aleksandra Marciniak"}]}
    cov = coverage_for_doc("Aleksandry Kowalskiego", gt, "pelnomocnictwo")
    assert (cov.found, cov.found_fuzzy) == (0, 0)
    assert cov.missing == [("pelnomocnicy[].imie_nazwisko", "Aleksandra Marciniak")]


def test_fuzzy_short_word_must_match_exactly():
    gt = {"pelnomocnicy": [{"imie_nazwisko": "Katarzyna Lis"}]}
    assert coverage_for_doc("Katarzyna Lisowski", gt, "pelnomocnictwo").total == 1
    assert coverage_for_doc("Katarzyna Lisowski", gt, "pelnomocnictwo").found_fuzzy == 0
    assert coverage_for_doc("Katarzyny Lis", gt, "pelnomocnictwo").found_fuzzy == 1


def test_fuzzy_only_for_imie_nazwisko():
    gt = {"Odwolujacy": [{"nazwa": "Belmoria Rozwiazania"}]}
    cov = coverage_for_doc("Belmorii Rozwiazaniom", gt, "odwolanie")
    assert (cov.found, cov.found_fuzzy, cov.total) == (0, 0, 1)


def test_missing_value():
    gt = {"przelew_bankowy": {"numer_transakcji": "CEN2604016344389"}}
    cov = coverage_for_doc("zupelnie inny tekst", gt, "przelew")
    assert cov.total == 1 and cov.found == 0
    assert cov.missing == [("przelew_bankowy.numer_transakcji", "CEN2604016344389")]


def test_skipped_and_empty_fields_not_counted():
    gt = {
        "OdwolanieKIO": {"data": "2026-03-20", "czynnosc_opis": "x", "miejscowosc": None},
        "przelew_bankowy": {"kwota": 200.0, "data_operacji": "2026-03-21"},
        "mocodawca": [{"data": {"typ": "osoba_prawna", "nazwa": "", "nip": None}}],
        "Zamawiajacy": [{"prowadzacy_postepowanie": "ABC"}],
        "ZamowieniePubliczne": {"numer_bzp": "2026/BZP00999778", "numer_ted": "999137-2026"},
    }
    assert coverage_for_doc("nic", gt, "odwolanie").total == 0


def test_leaf_paths_use_list_brackets():
    gt = {
        "Odwolujacy": [
            {"nazwa": "Alfa", "pelnomocnik": {"mail": "biuro@poczta.example"}},
            {"nazwa": "Beta"},
        ]
    }
    cov = coverage_for_doc("Alfa", gt, "odwolanie")
    assert cov.total == 3
    assert ("Odwolujacy[].pelnomocnik.mail", "biuro@poczta.example") in cov.missing
    assert ("Odwolujacy[].nazwa", "Beta") in cov.missing
    assert cov.by_field["Odwolujacy[].nazwa"].total == 2
    assert cov.by_field["Odwolujacy[].nazwa"].found == 1


def test_coverage_add():
    a = Coverage(found=1, found_fuzzy=1, total=3, missing=[("a", "x")])
    b = Coverage(found=2, found_fuzzy=0, total=2, missing=[("b", "y")])
    s = a + b
    assert (s.found, s.found_fuzzy, s.total) == (3, 1, 5)
    assert s.missing == [("a", "x"), ("b", "y")]
    assert s.rate == 3 / 5
    assert s.rate_with_fuzzy == 4 / 5
    assert Coverage().rate == 0.0


def test_przyklad_01_with_current_loader():
    from odw2json.ingest import load

    total = None
    for pdf_name, gt_name, dtype in [
        ("odwolanie.pdf", "odwolanie.json", "odwolanie"),
        ("pelnomocnictwo.pdf", "pelnomocnictwo.json", "pelnomocnictwo"),
        ("potwierdzenie_przelewu.pdf", "przelew.json", "przelew"),
    ]:
        doc = load(TRAIN / "przyklad_01" / pdf_name)
        gt = json.loads((TRAIN / "przyklad_01" / gt_name).read_text(encoding="utf-8"))
        cov = coverage_for_doc(doc.text, gt, dtype)
        total = cov if total is None else total + cov
    assert total is not None and total.total > 0
    assert total.rate_with_fuzzy > 0.9


@pytest.mark.slow
def test_cli_json_dump(tmp_path: Path):
    out = tmp_path / "cov.json"
    proc = subprocess.run(
        [sys.executable, "-m", "eval.ingest_coverage", "--split", "dev", "--json", str(out)],
        cwd=ROOT_DIR,
        capture_output=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert {"global", "by_type", "by_field"} <= set(data)
    assert data["global"]["total"] > 0
    assert "odwolanie" in data["by_type"]


def test_explicit_backend_has_no_fallback(monkeypatch):
    """Przy --backend padniecie backendu = blad wczytania, a nie ciche obsluzenie przez fallback."""
    import eval.ingest_coverage as ic
    from odw2json.ingest import backends

    def boom(path):
        raise RuntimeError("backend padl")

    monkeypatch.setitem(backends.BACKENDS, "pypdf", boom)
    monkeypatch.setattr(ic, "_cases", lambda split: ["przyklad_01"])
    rep = ic.run_coverage("dev", backend="pypdf")
    assert rep.docs > 0
    assert len(rep.load_errors) == rep.docs
    assert rep.total.found == 0
    assert rep.foreign_backend == []


def test_explicit_backend_serves_itself(monkeypatch):
    import eval.ingest_coverage as ic

    monkeypatch.setattr(ic, "_cases", lambda split: ["przyklad_01"])
    rep = ic.run_coverage("dev", backend="pypdfium2")
    assert rep.load_errors == []
    assert rep.foreign_backend == []
    assert rep.total.found > 0
