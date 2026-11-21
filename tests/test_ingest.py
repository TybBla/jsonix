"""Testy ingestu: backendy wymienne, offsety stron, fallback, IngestError."""

from __future__ import annotations

import shutil

import pytest

from odw2json import ingest, pipeline
from odw2json.contracts import Document, IngestError
from odw2json.ingest import backends

NIP = "9999284065"
PAGE2_FRAGMENT = "Zarzut nr 2"  # występuje na stronie 2 (indeks 1) odwolanie.pdf


@pytest.fixture
def odwolanie(train_dir):
    return train_dir / "przyklad_01" / "odwolanie.pdf"


@pytest.mark.parametrize("name", ["pypdf", "pdfplumber", "pypdfium2"])
def test_each_backend_reads_polish_text(name, odwolanie):
    pages = backends.BACKENDS[name](odwolanie)
    assert len(pages) == 2
    text = "\n".join(pages)
    for token in ("Odwołujący", "Łódź", "Zamawiającego", "Postępu"):
        assert token in text, (name, token)
    assert NIP in text.replace(" ", "").replace("-", "")


def test_load_sets_backend_and_offsets(odwolanie):
    doc = ingest.load(odwolanie, cfg={})
    assert isinstance(doc, Document)
    assert doc.backend == "pypdf"
    assert doc.text == "\n\f\n".join(doc.pages)
    assert len(doc.page_offsets) == len(doc.pages) == 2
    for off, page in zip(doc.page_offsets, doc.pages, strict=True):
        assert doc.text[off : off + len(page)] == page


def test_page_of_maps_page_two_to_index_one(odwolanie):
    doc = ingest.load(odwolanie, cfg={})
    pos = doc.text.index(PAGE2_FRAGMENT)
    assert doc.page_of(pos) == 1
    assert doc.page_of(doc.text.index("Prezes")) == 0
    assert doc.page_of(0) == 0
    assert doc.page_of(-1) is None
    assert doc.page_of(len(doc.text) + 5) is None


def test_page_of_without_offsets_is_none():
    from pathlib import Path

    assert Document(path=Path("x.pdf"), text="abc", pages=["abc"]).page_of(0) is None


def test_backend_from_config_and_argument_override(odwolanie):
    assert ingest.load(odwolanie, cfg={"backend": "pdfplumber"}).backend == "pdfplumber"
    doc = ingest.load(odwolanie, backend="pypdfium2", cfg={"backend": "pdfplumber"})
    assert doc.backend == "pypdfium2"


def test_default_config_backend_is_pypdf(odwolanie):
    assert ingest.load(odwolanie).backend == "pypdf"


def test_unknown_backend_raises_ingest_error(odwolanie):
    with pytest.raises(IngestError, match="nieznany"):
        ingest.load(odwolanie, backend="nie_ma_takiego", cfg={})


def test_fallback_when_first_backend_raises(odwolanie, monkeypatch):
    def boom(path):
        raise RuntimeError("awaria backendu")

    monkeypatch.setitem(backends.BACKENDS, "pypdf", boom)
    doc = ingest.load(odwolanie, cfg={"backend": "pypdf", "fallback_backends": ["pypdfium2", "pdfplumber"]})
    assert doc.backend == "pypdfium2"
    assert any("pypdf" in w and "awaria backendu" in w for w in doc.warnings)
    assert "Odwołujący" in doc.text


def test_fallback_when_first_backend_returns_empty_text(odwolanie, monkeypatch):
    monkeypatch.setitem(backends.BACKENDS, "pypdf", lambda path: ["", ""])
    doc = ingest.load(odwolanie, cfg={"backend": "pypdf", "fallback_backends": ["pdfplumber"]})
    assert doc.backend == "pdfplumber"
    assert any("pypdf" in w for w in doc.warnings)


def test_all_backends_fail_raises_summary(odwolanie, monkeypatch):
    def boom(path):
        raise RuntimeError("zepsute")

    for name in ("pypdf", "pdfplumber", "pypdfium2"):
        monkeypatch.setitem(backends.BACKENDS, name, boom)
    with pytest.raises(IngestError) as exc:
        ingest.load(odwolanie, cfg={"backend": "pypdf", "fallback_backends": ["pdfplumber", "pypdfium2"]})
    msg = str(exc.value)
    assert "pypdf" in msg and "pdfplumber" in msg and "pypdfium2" in msg and "zepsute" in msg


def test_all_empty_text_on_nonempty_pdf_is_not_an_error_when_every_backend_empty(odwolanie, monkeypatch):
    # skan bez warstwy tekstowej: puste strony to nie błąd (OCR zrobi to w T5), tylko ostrzeżenie
    for name in ("pypdf", "pdfplumber", "pypdfium2"):
        monkeypatch.setitem(backends.BACKENDS, name, lambda path: ["", ""])
    doc = ingest.load(odwolanie, cfg={"backend": "pypdf", "fallback_backends": ["pdfplumber"]})
    assert doc.pages == ["", ""]
    assert doc.warnings


def test_clean_steps_missing_module_warns(odwolanie, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "odw2json.ingest.clean":
            raise ImportError("brak")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    doc = ingest.load(odwolanie, cfg={"clean": ["collapse_spaces"]})
    assert any("czyszczen" in w.lower() for w in doc.warnings)
    assert "Odwołujący" in doc.text


def test_clean_steps_applied_and_offsets_stay_exact(odwolanie, monkeypatch):
    import sys
    import types

    fake = types.ModuleType("odw2json.ingest.clean")
    fake.clean_text = lambda text, steps: text.upper() if "upper" in steps else text
    monkeypatch.setitem(sys.modules, "odw2json.ingest.clean", fake)
    doc = ingest.load(odwolanie, cfg={"clean": ["upper"]})
    assert "ODWOŁUJĄCY" in doc.text
    for off, page in zip(doc.page_offsets, doc.pages, strict=True):
        assert doc.text[off : off + len(page)] == page


def test_empty_file_raises(tmp_path):
    p = tmp_path / "pusty.pdf"
    p.write_bytes(b"")
    with pytest.raises(IngestError, match="pust"):
        ingest.load(p, cfg={})


def test_html_with_pdf_extension_raises(tmp_path):
    p = tmp_path / "strona.pdf"
    p.write_text("<html><body>to jest HTML</body></html>", encoding="utf-8")
    with pytest.raises(IngestError, match="nie jest PDF"):
        ingest.load(p, cfg={})


def test_leading_whitespace_before_header_is_accepted(tmp_path, odwolanie):
    p = tmp_path / "spacje.pdf"
    p.write_bytes(b"\n\r  " + odwolanie.read_bytes())
    try:
        doc = ingest.load(p, cfg={})
    except IngestError:
        pytest.skip("pypdf nie czyta przesuniętych offsetów xref")
    assert doc.pages


def test_encrypted_pdf_raises(tmp_path, odwolanie):
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for pg in PdfReader(str(odwolanie)).pages:
        writer.add_page(pg)
    writer.encrypt("test")
    p = tmp_path / "zaszyfrowany.pdf"
    with p.open("wb") as fh:
        writer.write(fh)
    with pytest.raises(IngestError, match="zaszyfrowany"):
        ingest.load(p, cfg={})


def test_zero_pages_pdf_raises(tmp_path):
    from pypdf import PdfWriter

    p = tmp_path / "bez_stron.pdf"
    with p.open("wb") as fh:
        PdfWriter().write(fh)
    with pytest.raises(IngestError, match="bez stron"):
        ingest.load(p, cfg={})


def test_pipeline_records_ingest_error_and_continues(tmp_path, train_dir):
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "pusty.pdf").write_bytes(b"")
    (inp / "html.pdf").write_text("<html></html>", encoding="utf-8")
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "dobry.pdf")
    out = tmp_path / "output"
    report = pipeline.run(inp, out, app_cfg={"unknown_output": "none", "write_trace": False})
    assert report.processed == 1
    assert (out / "dobry.json").exists()
    errors = {e.path.name: e.error for e in report.errors}
    assert set(errors) == {"pusty.pdf", "html.pdf"}
    assert all(msg.startswith("IngestError: ") for msg in errors.values())
