"""Slepy zestaw syntetyczny do oceny odpornosci klasyfikatora.

Uruchom: RUN_BLIND=1 python -m pytest tests/test_classify_blind.py -q -s
"""

import os
from pathlib import Path

import pytest
import yaml

from odw2json.classify import classify
from odw2json.config_loader import load_registry
from odw2json.contracts import Document

pytestmark = pytest.mark.skipif(os.environ.get("RUN_BLIND") != "1", reason="blind eval: run with RUN_BLIND=1")

DIR = Path(__file__).parent / "fixtures" / "classify_blind"
EXPECTED = yaml.safe_load((DIR / "expected.yaml").read_text(encoding="utf-8"))
_results: list[tuple[str, str | None, str | None]] = []


@pytest.fixture(scope="module", autouse=True)
def _summary():
    yield
    ok = sum(1 for _, e, g in _results if e == g)
    print("\n\nBLIND SUMMARY")
    print(f"{'plik':40} {'oczekiwano':16} {'wynik':16} ok")
    for name, exp, got in _results:
        print(f"{name:40} {exp!s:16} {got!s:16} {'OK' if exp == got else 'BLAD'}")
    print(f"razem: {ok}/{len(_results)}")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_blind(name):
    text = (DIR / name).read_text(encoding="utf-8")
    doc = Document(path=Path(name), text=text, pages=[text])
    result = classify(doc, load_registry())
    got = result.doc_type
    expected = EXPECTED[name]["expected"]
    _results.append((name, expected, got))
    assert got == expected, EXPECTED[name].get("note", "")
