import json
import shutil

from odw2json import pipeline


def _mk_input(tmp_path, train_dir):
    inp = tmp_path / "input"
    case = inp / "case1"
    case.mkdir(parents=True)
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", case / "przyklad odwolanie.pdf")
    shutil.copy(train_dir / "przyklad_01" / "potwierdzenie_przelewu.pdf", case / "potwierdzenie_przelewu.pdf")
    ted = next((train_dir / "przyklad_10").glob("2025-OJS107-*.pdf"))
    shutil.copy(ted, case / "negatywny przyklad.pdf")
    (case / "broken.pdf").write_bytes(b"to nie jest pdf")
    (case / "notatka.txt").write_text("ignoruj", encoding="utf-8")
    shutil.copy(train_dir / "przyklad_01" / "pelnomocnictwo.pdf", inp / "luzem.pdf")
    return inp


def test_run_writes_outputs_with_same_names(tmp_path, train_dir):
    inp, out = _mk_input(tmp_path, train_dir), tmp_path / "output"
    report = pipeline.run(inp, out, app_cfg={"unknown_output": "none", "write_trace": True})
    data = json.loads((out / "case1" / "przyklad odwolanie.json").read_text(encoding="utf-8"))
    assert "OdwolanieKIO" in data
    assert (out / "case1" / "potwierdzenie_przelewu.json").exists()
    assert (out / "luzem.json").exists()
    assert not (out / "case1" / "negatywny przyklad.json").exists()
    assert not (out / "case1" / "notatka.json").exists()
    assert [e.path.name for e in report.errors] == ["broken.pdf"]
    assert report.processed == 4
    assert (out / ".trace" / "case1" / "przyklad odwolanie.trace.json").exists()


def test_unknown_as_empty_object_default(tmp_path, train_dir):
    # UZP (Discord 21.11, 13:27): nieznany dokument -> pusty JSON z nazwą oryginalnego pliku
    inp, out = _mk_input(tmp_path, train_dir), tmp_path / "output"
    pipeline.run(inp, out, app_cfg={"unknown_output": "empty_object", "write_trace": False})
    assert json.loads((out / "case1" / "negatywny przyklad.json").read_text(encoding="utf-8")) == {}


def test_default_app_config_is_empty_object():
    from odw2json.config_loader import load_app_config

    assert load_app_config()["unknown_output"] == "empty_object"


def test_unknown_as_empty_file(tmp_path, train_dir):
    inp, out = _mk_input(tmp_path, train_dir), tmp_path / "output"
    pipeline.run(inp, out, app_cfg={"unknown_output": "empty_file", "write_trace": False})
    assert (out / "case1" / "negatywny przyklad.json").read_text(encoding="utf-8") == ""
    assert not (out / ".trace").exists()


def test_output_is_utf8_not_escaped():
    raw = pipeline._dump({"nazwa": "Zespół Szkół Łódź"})
    assert "Zespół Szkół Łódź" in raw


def test_trace_has_ocr_used_backend_and_warnings(tmp_path, train_dir):
    inp, out = _mk_input(tmp_path, train_dir), tmp_path / "output"
    pipeline.run(inp, out, app_cfg={"unknown_output": "none", "write_trace": True})
    tr = json.loads((out / ".trace" / "case1" / "przyklad odwolanie.trace.json").read_text(encoding="utf-8"))
    assert tr["ocr_used"] is False
    assert tr["backend"] == "pypdfium2"
    assert isinstance(tr["warnings"], list)
    assert "classification" in tr and "trace" in tr


def test_trace_marks_ocr_used(tmp_path, train_dir, monkeypatch):
    from odw2json import ingest

    inp, out = _mk_input(tmp_path, train_dir), tmp_path / "output"
    real_load = ingest.load

    def fake_load(path, **kw):
        doc = real_load(path, **kw)
        doc.ocr_used, doc.backend, doc.warnings = True, "pypdfium2+ocr:rapidocr", ["OCR strony 1"]
        return doc

    monkeypatch.setattr(ingest, "load", fake_load)
    pipeline.run(inp, out, app_cfg={"unknown_output": "none", "write_trace": True})
    tr = json.loads((out / ".trace" / "case1" / "przyklad odwolanie.trace.json").read_text(encoding="utf-8"))
    assert tr["ocr_used"] is True
    assert tr["backend"] == "pypdfium2+ocr:rapidocr"
    assert tr["warnings"] == ["OCR strony 1"]


def test_process_file_signature_unchanged(train_dir):
    from odw2json.config_loader import load_registry

    cls, res = pipeline.process_file(train_dir / "przyklad_01" / "odwolanie.pdf", load_registry())
    assert cls.doc_type and res is not None
