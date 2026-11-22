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


# --- limit czasu UZP (kryteria pkt 5a): kolejność, lista wejść, zapis atomowy ---


def _scan_and_text(tmp_path, train_dir):
    inp = tmp_path / "in"
    (inp / "sprawa").mkdir(parents=True)
    # alfabetycznie skan byłby pierwszy; ma trafić na koniec
    shutil.copy(train_dir / "skany" / "potwierdzenia" / "0007" / "0007.pdf", inp / "sprawa" / "a_skan.pdf")
    shutil.copy(train_dir / "przyklad_01" / "pelnomocnictwo.pdf", inp / "sprawa" / "b_tekst.pdf")
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "c_tekst_luzem.pdf")
    (inp / "sprawa" / "notatka.txt").write_text("x", encoding="utf-8")
    return inp


def test_list_inputs_puts_text_layer_pdfs_before_scans(tmp_path, train_dir):
    inp = _scan_and_text(tmp_path, train_dir)
    order = pipeline.list_inputs(inp)
    assert order[-1].name == "a_skan.pdf", "skan (OCR) na końcu"
    text = order[:-1]
    assert {p.name for p in text} == {"b_tekst.pdf", "c_tekst_luzem.pdf"}
    assert text == sorted(text, key=str), "wśród dokumentów z tekstem: stabilnie wg ścieżki"


def test_list_inputs_keeps_unreadable_pdf_and_sorts_it_first(tmp_path):
    (tmp_path / "zly.pdf").write_bytes(b"to nie jest pdf")
    assert [p.name for p in pipeline.list_inputs(tmp_path)] == ["zly.pdf"], "błąd zgłosi potok, nie lista"


def test_run_processes_in_list_inputs_order(tmp_path, train_dir, monkeypatch):
    inp = _scan_and_text(tmp_path, train_dir)
    seen = []
    real = pipeline.process_file_ex

    def spy(pdf, *a, **k):
        seen.append(pdf.name)
        return real(pdf, *a, **k)

    monkeypatch.setattr(pipeline, "process_file_ex", spy)
    pipeline.run(inp, tmp_path / "out")
    assert seen == [p.name for p in pipeline.list_inputs(inp)]


def test_write_outputs_is_atomic(tmp_path, train_dir, monkeypatch):
    """Przerwanie w trakcie zapisu nie zostawia uciętego JSON-a: stary plik zostaje do os.replace."""
    pdf = train_dir / "przyklad_01" / "pelnomocnictwo.pdf"
    inp = tmp_path / "in"
    inp.mkdir()
    shutil.copy(pdf, inp / "p.pdf")
    out = tmp_path / "out"
    target = out / "p.json"
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")
    registry = pipeline.load_registry()
    _, cls, res = pipeline.process_file_ex(inp / "p.pdf", registry)

    def killed(*_a, **_k):
        raise KeyboardInterrupt  # proces zatrzymany tuż przed podmianą pliku

    monkeypatch.setattr(pipeline.os, "replace", killed)
    try:
        pipeline.write_outputs(inp / "p.pdf", inp, out, cls, res, {"write_trace": False})
    except KeyboardInterrupt:
        pass
    assert target.read_text(encoding="utf-8") == "{}", "docelowy plik bez zmian aż do os.replace"
    monkeypatch.undo()
    pipeline.write_outputs(inp / "p.pdf", inp, out, cls, res, {"write_trace": False})
    assert json.loads(target.read_text(encoding="utf-8")) == res.data
    assert not list(out.glob("*.tmp")), "bez plików tymczasowych po udanym zapisie"
