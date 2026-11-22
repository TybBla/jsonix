"""Test dymny sondy odporności (scripts/robustness_probe.py): warianty i pętla na dokumencie w pamięci."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from odw2json.config_loader import load_registry

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("robustness_probe", ROOT / "scripts" / "robustness_probe.py")
probe = importlib.util.module_from_spec(_spec)
sys.modules["robustness_probe"] = probe  # dataclass (Python 3.14) szuka modułu po nazwie
_spec.loader.exec_module(probe)

TYTUL = (
    "opłata skarbowa od pełnomocnictwa dla Jan Kowalski w postępowaniu przed KIO w przetargu "
    "ZS.791.2026 CEN2604016344389"
)
PRZELEW_TEXT = f"""POLECENIE PRZELEWU
Płatnik
Firma Alfa sp. z o.o.
Rachunek obciążany
PL05470680287581539721455024
Adresat przelewu
Firma Beta S.A.
Rachunek odbiorcy
PL68438223049992295262834736
Kwota operacji
200,00 PLN
Data transakcji
2026-03-21
Opis
{TYTUL}
Nr ref.
CEN2604016344389
ZREALIZOWANO
"""

PRZELEW_GT = {
    "przelew_bankowy": {
        "z_rachunku": "PL05470680287581539721455024",
        "na_rachunek": "PL68438223049992295262834736",
        "kwota": 200.0,
        "data_operacji": "2026-03-21",
        "tytul": TYTUL,
        "numer_transakcji": "CEN2604016344389",
    }
}


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.fixture
def sample():
    return probe.Sample("syntetyczny_01", "przelew", PRZELEW_TEXT, PRZELEW_GT)


def test_label_variant_rewrites_text_only_where_label_stands_at_line_start(sample):
    t2, gt2 = probe.VARIANTS["a9 data operacji->Data przelewu"](sample.text, sample.gt, "przelew")
    assert "Data przelewu\n2026-03-21" in t2
    assert "Data transakcji" not in t2
    assert gt2 == sample.gt  # zmiana etykiety nie zmienia wartości oczekiwanej


def test_variant_for_other_type_is_a_noop(sample):
    t2, gt2 = probe.VARIANTS["a4 Odwołujący:->Wykonawca wnoszący odwołanie:"](
        sample.text, sample.gt, "przelew"
    )
    assert (t2, gt2) == (sample.text, sample.gt)


def test_amount_variant_changes_text_and_ground_truth_together(sample):
    t2, gt2 = probe.VARIANTS["b4 kwota 10.000,00 zł"](sample.text, sample.gt, "przelew")
    assert "10.000,00 zł" in t2
    assert gt2["przelew_bankowy"]["kwota"] == 10000.0
    assert sample.gt["przelew_bankowy"]["kwota"] == 200.0  # oryginał nietknięty


def test_iban_variant_rewrites_ground_truth_to_document_form(sample):
    t2, gt2 = probe.VARIANTS["b9 IBAN ciągiem bez PL"](sample.text, sample.gt, "przelew")
    assert "PL05470680287581539721455024" not in t2
    assert "05470680287581539721455024" in t2
    assert gt2["przelew_bankowy"]["na_rachunek"] == "68438223049992295262834736"


def test_whitespace_artifacts_are_removed_by_ingest_cleaning(sample):
    # podwójne spacje i CRLF usuwa ingest, więc wariant jest tożsamością (dokument pomijany)
    for name in ("c9 podwójne spacje", "c11 CRLF", "c10 spacje na końcu linii"):
        t2, _ = probe.VARIANTS[name](sample.text, sample.gt, "przelew")
        assert t2 == sample.text.rstrip("\n") or t2 == sample.text, name


def test_evaluate_runs_on_in_memory_document(sample, registry):
    names = ["a9 data operacji->Data przelewu", "b4 kwota 10.000,00 zł", "d4 brak nr ref. przelewu"]
    variants = {n: probe.VARIANTS[n] for n in names}
    rep = probe.evaluate([sample], registry, variants=variants, split="test", max_examples=1)

    assert rep.base_docs == {"przelew": 1}
    assert rep.base["przelew"].f1 == pytest.approx(1.0)
    assert {r.variant for r in rep.rows} == set(names)
    assert all(r.n == 1 and r.type == "przelew" for r in rep.rows)
    # wariant „brak nr ref.” usuwa też wartość oczekiwaną, a ekstrakcja nie zgaduje numeru
    assert not any(b.variant == "d4 brak nr ref. przelewu" for b in rep.breaks)


def test_evaluate_reports_a_break_with_example(sample, registry):
    def mangle(t: str, gt: dict, typ: str):
        return t.replace("Kwota operacji\n200,00 PLN\n", ""), gt  # kwota znika, GT zostaje -> FN

    rep = probe.evaluate([sample], registry, variants={"x brak kwoty": mangle}, max_examples=2)
    assert [(b.variant, b.path, b.cases) for b in rep.breaks] == [
        ("x brak kwoty", "przelew_bankowy.kwota", ["syntetyczny_01"])
    ]
    assert rep.rows[0].broke
    text = probe.format_report(rep)
    assert "x brak kwoty" in text and "przelew_bankowy.kwota" in text
    assert "PRED [null]" in text and "GT   [200.0]" in text


def test_variant_prefix_filter(sample, registry):
    rep = probe.evaluate([sample], registry, only="b4")
    assert [r.variant for r in rep.rows] == ["b4 kwota 10.000,00 zł"]


def test_main_prints_report_and_exits_zero(monkeypatch, capsys, tmp_path, sample):
    monkeypatch.setattr(probe, "build_corpus", lambda split, registry=None: [sample])
    out = tmp_path / "raport" / "odpornosc.txt"
    code = probe.main(["--split", "dev", "--variant", "b4", "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "F1 bazowe" in printed and "b4 kwota" in printed
    assert out.read_text(encoding="utf-8") == printed


def test_build_corpus_rejects_unknown_split():
    with pytest.raises(ValueError, match="nieznany split"):
        probe.build_corpus("losowy")
