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
    doc = ingest.load(odwolanie, cfg={"backend": "pypdf"})
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


def test_default_config_backend_is_pypdfium2(odwolanie):
    # Decyzja orkiestratora: docs/decyzje/E2-backend-pdf.md
    assert ingest.load(odwolanie).backend == "pypdfium2"


def test_unknown_backend_raises_ingest_error(odwolanie):
    with pytest.raises(IngestError, match="nieznany"):
        ingest.load(odwolanie, backend="nie_ma_takiego", cfg={"fallback_backends": []})


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
    doc = ingest.load(odwolanie, cfg={"backend": "pypdf", "fallback_backends": ["pdfplumber"], "ocr": {}})
    assert doc.pages == ["", ""]
    assert doc.warnings


def _fake_backend(pages):
    return lambda path: list(pages)


def clean_default_order():
    from odw2json.ingest.clean import DEFAULT_ORDER

    return list(DEFAULT_ORDER)


def test_clean_steps_applied_and_offsets_stay_exact(odwolanie, monkeypatch):
    from odw2json.ingest import clean

    monkeypatch.setitem(clean.CLEAN_STEPS, "upper", str.upper)
    doc = ingest.load(odwolanie, cfg={"clean": ["upper"]})
    assert "ODWOŁUJĄCY" in doc.text
    for off, page in zip(doc.page_offsets, doc.pages, strict=True):
        assert doc.text[off : off + len(page)] == page


def test_cleaning_runs_on_joined_document_footer_kept_on_first_page(odwolanie, monkeypatch):
    footer = "Kancelaria Prawna X, ul. Długa 1, tel. 000"
    pages = [
        f"Odwołujący strona jeden\n{footer}",
        f"Zarzut nr 2 treść\n{footer}",
        f"Trzecia strona\n{footer}",
    ]
    monkeypatch.setitem(backends.BACKENDS, "pypdf", _fake_backend(pages))
    doc = ingest.load(odwolanie, cfg={"backend": "pypdf", "clean": clean_default_order()})
    assert len(doc.pages) == 3
    assert footer in doc.pages[0]
    assert footer not in doc.pages[1]
    assert footer not in doc.pages[2]
    assert doc.text == "\n\f\n".join(doc.pages)
    for i, (off, page) in enumerate(zip(doc.page_offsets, doc.pages, strict=True)):
        assert doc.text[off : off + len(page)] == page
        assert doc.page_of(off) == i
    assert doc.page_of(doc.text.index("Zarzut nr 2")) == 1


def test_cleaning_that_removes_page_break_is_rejected(odwolanie, monkeypatch):
    from odw2json.ingest import clean

    monkeypatch.setitem(clean.CLEAN_STEPS, "zjedz_f", lambda t: t.replace("\f", ""))
    monkeypatch.setitem(backends.BACKENDS, "pypdf", _fake_backend(["a", "b"]))
    with pytest.raises(RuntimeError, match="liczb"):
        ingest.load(odwolanie, cfg={"backend": "pypdf", "clean": ["zjedz_f"], "ocr": {"enabled": False}})


def test_fix_pdfium_text_removes_soft_hyphen_marker_and_normalizes_newlines():
    assert backends._fix_pdfium_text("zidentyfiko￾wany") == "zidentyfikowany"
    assert backends._fix_pdfium_text("a\r\nb\rc￾\r\nd") == "a\nb\nc\nd"
    assert backends._fix_pdfium_text("Łódź ąęśćżźńó") == "Łódź ąęśćżźńó"


def test_pypdfium2_backend_has_no_fffe(odwolanie):
    assert all("￾" not in p for p in backends.BACKENDS["pypdfium2"](odwolanie))


# --- walidacja konfiguracji ---


def test_validate_ingest_cfg_accepts_defaults_and_empty():
    ingest.validate_ingest_cfg({})
    ingest.validate_ingest_cfg(
        {"backend": "pypdf", "fallback_backends": ["pypdfium2"], "clean": clean_default_order()}
    )


@pytest.mark.parametrize(
    ("cfg", "fragment"),
    [
        ({"backend": "nie_ma"}, "nie_ma"),
        ({"backend": "pypdf", "fallback_backends": ["pypdfium2", "zly_fallback"]}, "zly_fallback"),
        ({"clean": ["collapse_spaces", "zly_krok"]}, "zly_krok"),
    ],
)
def test_validate_ingest_cfg_rejects_unknown(cfg, fragment):
    with pytest.raises(ValueError, match="konfiguracj") as exc:
        ingest.validate_ingest_cfg(cfg)
    assert fragment in str(exc.value)


def test_validate_unknown_clean_step_lists_available():
    with pytest.raises(ValueError, match="dehyphenate"):
        ingest.validate_ingest_cfg({"clean": ["zly_krok"]})


def test_load_validates_explicit_cfg(odwolanie):
    with pytest.raises(ValueError, match="nie_ma"):
        ingest.load(odwolanie, cfg={"backend": "nie_ma"})
    with pytest.raises(ValueError, match="zly_krok"):
        ingest.load(odwolanie, cfg={"clean": ["zly_krok"]})


@pytest.mark.parametrize(
    "bad",
    [{"backend": "nie_ma"}, {"fallback_backends": ["nie_ma"]}, {"clean": ["zly_krok"]}],
)
def test_pipeline_run_fails_fast_on_bad_ingest_cfg(tmp_path, train_dir, monkeypatch, bad):
    inp = tmp_path / "input"
    inp.mkdir()
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "dobry.pdf")
    calls = []
    monkeypatch.setattr(pipeline, "process_file_ex", lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError):
        pipeline.run(inp, tmp_path / "output", app_cfg={"ingest": bad, "write_trace": False})
    assert calls == []


def test_pipeline_run_passes_ingest_cfg_to_load(tmp_path, train_dir, monkeypatch):
    inp = tmp_path / "input"
    inp.mkdir()
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "dobry.pdf")
    seen = []
    real_load = ingest.load
    monkeypatch.setattr(ingest, "load", lambda path, **kw: (seen.append(kw), real_load(path, **kw))[1])
    cfg = {"backend": "pdfplumber"}
    report = pipeline.run(inp, tmp_path / "output", app_cfg={"ingest": cfg, "write_trace": False})
    assert report.processed == 1 and not report.errors
    assert seen == [{"cfg": cfg}]


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


@pytest.mark.parametrize("junk", [b"\xef\xbb\xbf", b"JUNK\x00\x01 garbage\n", b"X" * 500])
def test_junk_before_pdf_header_is_accepted(tmp_path, odwolanie, junk):
    p = tmp_path / "smieci.pdf"
    p.write_bytes(junk + odwolanie.read_bytes())
    doc = ingest.load(p, cfg={})
    assert "Odwołujący" in doc.text


def test_header_beyond_first_kilobyte_is_rejected(tmp_path, odwolanie):
    p = tmp_path / "daleko.pdf"
    p.write_bytes(b"X" * 2000 + odwolanie.read_bytes())
    with pytest.raises(IngestError, match="nie jest PDF"):
        ingest.load(p, cfg={})


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


def test_default_config_enables_full_cleaning_order():
    from odw2json.config_loader import load_app_config
    from odw2json.ingest.clean import DEFAULT_ORDER

    assert load_app_config()["ingest"]["clean"] == DEFAULT_ORDER


# --- poprawki po review etapu E2 ---


@pytest.mark.parametrize(
    ("ocr_cfg", "fragment"),
    [
        ({"engine": "tesseract"}, "tesseract"),
        ({"min_chars_per_page": 0}, "min_chars_per_page"),
        ({"min_chars_per_page": "30"}, "min_chars_per_page"),
        ({"min_chars_per_page": True}, "min_chars_per_page"),
        ({"dpi": -5}, "dpi"),
        ({"dpi": 1.5}, "dpi"),
        ({"enabled": "tak"}, "enabled"),
    ],
)
def test_validate_ingest_cfg_rejects_bad_ocr_section(ocr_cfg, fragment):
    with pytest.raises(ValueError, match="konfiguracji ingest") as exc:
        ingest.validate_ingest_cfg({"ocr": ocr_cfg})
    assert fragment in str(exc.value)


def test_validate_ingest_cfg_accepts_good_ocr_section():
    ingest.validate_ingest_cfg(
        {"ocr": {"enabled": True, "engine": "rapidocr", "min_chars_per_page": 30, "dpi": 200}}
    )


@pytest.mark.parametrize("bad", [{"engine": "tesseract"}, {"min_chars_per_page": -1}])
def test_pipeline_run_fails_fast_on_bad_ocr_cfg(tmp_path, train_dir, monkeypatch, bad):
    inp = tmp_path / "input"
    inp.mkdir()
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "dobry.pdf")
    calls = []
    monkeypatch.setattr(pipeline, "process_file_ex", lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError):
        pipeline.run(inp, tmp_path / "output", app_cfg={"ingest": {"ocr": bad}, "write_trace": False})
    assert calls == []


def test_form_feed_in_backend_page_does_not_break_cleaning(odwolanie, monkeypatch):
    monkeypatch.setitem(backends.BACKENDS, "ff", lambda p: ["Strona\fjeden tekst", "Strona dwa tekst"])
    cfg = {"backend": "ff", "clean": ["collapse_spaces"], "ocr": {"enabled": False}}
    doc = ingest.load(odwolanie, cfg=cfg)
    assert len(doc.pages) == 2
    assert "\f" not in doc.pages[0]
    assert doc.pages[0] == "Strona\njeden tekst"


def test_partial_cfg_takes_missing_keys_from_app_yaml(odwolanie):
    from odw2json.config_loader import load_app_config

    cfg_file = load_app_config()["ingest"]
    off = {"enabled": False}
    partial = ingest.load(odwolanie, cfg={"backend": "pypdf", "ocr": off})
    explicit = ingest.load(odwolanie, cfg={"backend": "pypdf", "clean": cfg_file["clean"], "ocr": off})
    raw = ingest.load(odwolanie, cfg={"backend": "pypdf", "clean": [], "ocr": off})
    assert partial.text == explicit.text
    assert partial.text != raw.text  # czyszczenie z pliku zostało zastosowane


def test_default_backend_constant_is_pypdfium2():
    assert ingest.DEFAULT_BACKEND == "pypdfium2"
