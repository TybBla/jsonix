"""Testy API pod GUI (etap E8E9, zadanie A1). Bez OCR: tylko PDF-y z warstwą tekstową."""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from odw2json import api
from odw2json.api.files import has_pdf_header
from odw2json.api.jobs import JobStore

ROOT = Path(__file__).resolve().parents[1]
P01 = ROOT / "data" / "train" / "przyklad_01"
FIXTURES = ROOT / "tests" / "fixtures" / "gui"
PDFS = ["odwolanie.pdf", "pelnomocnictwo.pdf", "potwierdzenie_przelewu.pdf"]

RESULT_KEYS = {"file", "name", "status", "error", "classification", "data", "trace", "warnings", "pages"}
TRACE_KEYS = {"path", "value", "method", "source_snippet", "page"}


@pytest.fixture
def store(tmp_path) -> JobStore:
    return JobStore(tmp_path / "jobs")


@pytest.fixture
def client(store):
    api.app.dependency_overrides[api.get_store] = lambda: store
    try:
        yield TestClient(api.app)
    finally:
        api.app.dependency_overrides.clear()


def _pdf(name: str) -> tuple[str, bytes, str]:
    return (name, (P01 / name).read_bytes(), "application/pdf")


def _submit(client, files) -> str:
    r = client.post("/api/jobs", files=[("files", f) for f in files])
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def _wait(client, job_id: str, timeout: float = 60.0) -> dict:
    t0 = time.monotonic()
    while True:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("done", "error"):
            return body
        assert time.monotonic() - t0 < timeout, body
        time.sleep(0.05)


@pytest.fixture
def done_job(client):
    job_id = _submit(client, [_pdf(n) for n in PDFS])
    return job_id, _wait(client, job_id)


def test_health_and_doctypes_unchanged(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    ids = {d["id"] for d in client.get("/api/doctypes").json()}
    assert {"odwolanie", "pelnomocnictwo", "przelew"} <= ids


def test_job_with_three_pdfs_finishes_with_contract(done_job):
    _, body = done_job
    assert body["status"] == "done"
    assert body["processed"] == body["total"] == 3
    results = {r["file"]: r for r in body["files"]}
    assert set(results) == set(PDFS)
    types = {r["classification"]["doc_type"] for r in results.values()}
    assert types == {"odwolanie", "pelnomocnictwo", "przelew"}
    for r in results.values():
        assert set(r) == RESULT_KEYS
        assert r["status"] == "done" and r["error"] is None
        assert set(r["classification"]) == {"doc_type", "confidence", "method", "evidence"}
        assert isinstance(r["pages"], int) and r["pages"] >= 1
        assert isinstance(r["warnings"], list)
        for t in r["trace"]:
            assert set(t) == TRACE_KEYS


def test_result_data_has_same_shape_as_gui_fixtures(done_job):
    _, body = done_job
    results = {r["file"]: r for r in body["files"]}
    for fx in FIXTURES.glob("przyklad_01_*.result.json"):
        expected = json.loads(fx.read_text(encoding="utf-8"))
        got = results[expected["file"]]
        assert set(got["data"]) == set(expected["data"])
        assert got["classification"]["doc_type"] == expected["classification"]["doc_type"]


def test_status_reports_progress_fields_while_pending(client, store):
    job = store.create([("a.pdf", b"%PDF-1.4\n")])
    r = client.get(f"/api/jobs/{job.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["processed"] == 0 and body["total"] == 1


def test_non_pdf_is_per_file_error_and_others_succeed(client):
    files = [
        _pdf("pelnomocnictwo.pdf"),
        ("notatka.txt", b"zwykly tekst", "text/plain"),
        ("udaje.pdf", b"to nie jest pdf, tylko tekst", "application/pdf"),
    ]
    body = _wait(client, _submit(client, files))
    assert body["status"] == "done"
    assert body["processed"] == body["total"] == 3
    by = {r["file"]: r for r in body["files"]}
    assert by["pelnomocnictwo.pdf"]["status"] == "done"
    for bad in ("notatka.txt", "udaje.pdf"):
        assert by[bad]["status"] == "error"
        assert "PDF" in by[bad]["error"]
        assert by[bad]["classification"] is None and by[bad]["data"] is None


def test_empty_file_error_in_polish(client):
    body = _wait(client, _submit(client, [("pusty.pdf", b"", "application/pdf")]))
    (r,) = body["files"]
    assert r["status"] == "error"
    assert r["error"] == "Wybrany plik jest pusty."


def test_too_large_file_rejected(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_FILE_BYTES", 1024)
    body = _wait(client, _submit(client, [_pdf("odwolanie.pdf")]))
    (r,) = body["files"]
    assert r["status"] == "error"
    assert "mniejszy niż" in r["error"]


def test_pdf_header_checked_within_first_1024_bytes():
    assert has_pdf_header(b"%PDF-1.7\n...")
    assert has_pdf_header(b"\x00" * 1000 + b"%PDF-1.4")
    assert not has_pdf_header(b"\x00" * 1024 + b"%PDF-1.4")
    assert not has_pdf_header(b"<html>")


@pytest.mark.parametrize("evil", ["../../zlo.pdf", "..\\..\\zlo.pdf", "/etc/zlo.pdf", "C:\\Windows\\zlo.pdf"])
def test_path_traversal_in_filename_is_neutralised(client, store, tmp_path, evil):
    content = (P01 / "pelnomocnictwo.pdf").read_bytes()
    job_id = _submit(client, [(evil, content, "application/pdf")])
    body = _wait(client, job_id)
    (r,) = body["files"]
    assert r["file"] == "zlo.pdf"
    assert "/" not in r["name"] and "\\" not in r["name"] and ".." not in r["name"]
    written = [p for p in tmp_path.rglob("*.pdf")]
    assert written and all(store.root in p.parents for p in written)
    assert client.get(f"/api/jobs/{job_id}/files/{r['name']}/pdf").content == content


def test_polish_characters_kept_in_display_name_and_download(client):
    name = "Odwołanie Łódź żółć.pdf"
    job_id = _submit(client, [(name, (P01 / "odwolanie.pdf").read_bytes(), "application/pdf")])
    body = _wait(client, job_id)
    (r,) = body["files"]
    assert r["file"] == name
    resp = client.get(f"/api/jobs/{job_id}/files/{r['name']}/json")
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert cd.startswith("attachment")
    assert unquote(cd.split("filename*=UTF-8''")[1]) == "Odwołanie Łódź żółć.json"


def test_duplicate_names_get_unique_storage_names(client):
    f = _pdf("pelnomocnictwo.pdf")
    body = _wait(client, _submit(client, [f, f]))
    names = [r["name"] for r in body["files"]]
    assert len(set(names)) == 2


def test_download_pdf_returns_original(client, done_job):
    job_id, body = done_job
    r0 = next(r for r in body["files"] if r["file"] == "odwolanie.pdf")
    resp = client.get(f"/api/jobs/{job_id}/files/{r0['name']}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == (P01 / "odwolanie.pdf").read_bytes()


def test_download_json_is_attachment_with_data(client, done_job):
    job_id, body = done_job
    r0 = next(r for r in body["files"] if r["file"] == "potwierdzenie_przelewu.pdf")
    resp = client.get(f"/api/jobs/{job_id}/files/{r0['name']}/json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert 'filename="potwierdzenie_przelewu.json"' in resp.headers["content-disposition"]
    assert resp.json() == r0["data"]


def test_download_json_of_failed_file_is_404(client):
    job_id = _submit(client, [("notatka.txt", b"tekst", "text/plain")])
    body = _wait(client, job_id)
    resp = client.get(f"/api/jobs/{job_id}/files/{body['files'][0]['name']}/json")
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_zip_contains_all_json(client, done_job):
    job_id, body = done_job
    resp = client.get(f"/api/jobs/{job_id}/zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert sorted(zf.namelist()) == ["odwolanie.json", "pelnomocnictwo.json", "potwierdzenie_przelewu.json"]
    by = {r["file"]: r for r in body["files"]}
    assert json.loads(zf.read("pelnomocnictwo.json")) == by["pelnomocnictwo.pdf"]["data"]


def test_unknown_document_gives_empty_object(client, train_dir):
    ted = next((train_dir / "przyklad_10").glob("2025-OJS107-*.pdf"))
    job_id = _submit(client, [("ogloszenie.pdf", ted.read_bytes(), "application/pdf")])
    body = _wait(client, job_id)
    (r,) = body["files"]
    assert r["status"] == "done"
    assert r["classification"]["doc_type"] is None
    assert r["data"] == {}
    assert client.get(f"/api/jobs/{job_id}/files/{r['name']}/json").json() == {}


@pytest.mark.parametrize(
    "url",
    [
        "/api/jobs/{u}",
        "/api/jobs/{u}/zip",
        "/api/jobs/{u}/files/a.pdf/pdf",
        "/api/jobs/{u}/files/a.pdf/json",
    ],
)
def test_unknown_job_is_404(client, url):
    for u in ("0" * 32, "..%2F..%2Fetc", "nie-ma"):
        resp = client.get(url.format(u=u))
        assert resp.status_code == 404, (u, resp.text)


def test_unknown_file_in_existing_job_is_404(client, done_job):
    job_id, _ = done_job
    assert client.get(f"/api/jobs/{job_id}/files/brak.pdf/pdf").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/files/..%2F..%2Fx/pdf").status_code == 404


def test_post_without_files_is_rejected(client):
    resp = client.post("/api/jobs")
    assert resp.status_code in (400, 422)


def test_cleanup_removes_old_and_orphaned_job_dirs(tmp_path):
    root = tmp_path / "jobs"
    old = root / ("a" * 32)
    old.mkdir(parents=True)
    (old / "x.pdf").write_bytes(b"%PDF-")
    past = time.time() - 25 * 3600
    os.utime(old, (past, past))
    store = JobStore(root)
    fresh = store.create([("b.pdf", b"%PDF-1.4")])
    store.cleanup(max_age_s=24 * 3600)
    assert not old.exists()
    assert (root / fresh.id).exists()
    store.cleanup(max_age_s=0)
    assert not (root / fresh.id).exists()
    assert store.get(fresh.id) is None


def test_legacy_process_endpoint_still_works(client):
    resp = client.post("/api/process", files=[("files", _pdf("pelnomocnictwo.pdf"))])
    assert resp.status_code == 200
    (r,) = resp.json()
    assert r["classification"]["doc_type"] == "pelnomocnictwo"


def test_cleanup_never_touches_dirs_that_are_not_jobs(tmp_path):
    root = tmp_path / "jobs"
    foreign = root / "moje_dane"
    foreign.mkdir(parents=True)
    past = time.time() - 30 * 24 * 3600
    os.utime(foreign, (past, past))
    store = JobStore(root)
    store.cleanup(drop_orphans=True)
    store.cleanup(max_age_s=0)
    assert foreign.exists()


@pytest.mark.parametrize(
    "reserved",
    ["NUL.pdf", "con.pdf", "COM1.pdf", "lpt9.PDF", "aux", "CON.txt.pdf", "nul.tar.pdf", "Aux .pdf"],
)
def test_windows_reserved_names_are_not_used_on_disk(reserved):
    from odw2json.api.files import storage_name

    # Windows traktuje jako zarezerwowaną część nazwy przed PIERWSZĄ kropką (CON.txt.pdf = CON)
    first = storage_name(reserved, set()).split(".")[0].strip()
    assert first.casefold() not in {"nul", "con", "com1", "lpt9", "aux"}


def test_failure_message_is_polish_without_internals(store, monkeypatch):
    from odw2json.api import jobs as jobs_mod

    def boom(*_a, **_k):
        raise RuntimeError(r"C:\sciezka\serwera boom")

    monkeypatch.setattr(jobs_mod.pipeline, "process_file_ex", boom)
    job = store.create([("a.pdf", (P01 / "pelnomocnictwo.pdf").read_bytes())])
    store.process(job.id)
    (f,) = store.snapshot(job)["files"]
    assert f["status"] == "error"
    assert "sciezka" not in f["error"] and "RuntimeError" not in f["error"]
    assert f["error"].startswith("Nie udało się")


def test_json_download_handles_non_json_types(client, store):
    import datetime as dt

    job = store.create([("a.pdf", b"%PDF-1.4")])
    e = job.files[0]
    e.status, e.data = "done", {"data": dt.date(2026, 3, 20)}
    resp = client.get(f"/api/jobs/{job.id}/files/{e.name}/json")
    assert resp.status_code == 200
    assert resp.json() == {"data": "2026-03-20"}


def test_zip_not_ready_or_empty_is_409_or_404(client, store):
    job = store.create([("a.pdf", b"%PDF-1.4")])
    resp = client.get(f"/api/jobs/{job.id}/zip")
    assert resp.status_code == 409
    assert "detail" in resp.json()
    bad = _submit(client, [("notatka.txt", b"tekst", "text/plain")])
    _wait(client, bad)
    assert client.get(f"/api/jobs/{bad}/zip").status_code == 404


def test_ascii_fallback_transliterates_polish_letters():
    from odw2json.api.files import content_disposition

    cd = content_disposition("Pełnomocnictwo Łódź żółć.json")
    assert 'filename="Pelnomocnictwo Lodz zolc.json"' in cd


def test_openapi_title_is_project_display_name(client):
    assert client.get("/openapi.json").json()["info"]["title"] == "jsonix"


# --- poprawki z review PR #4 ---


def test_job_uses_pipeline_and_gives_same_data_as_cli(store, monkeypatch):
    """GUI i CLI muszą dawać identyczne dane: job woła pipeline.process_file_ex."""
    from odw2json import pipeline
    from odw2json.api import jobs as jobs_mod
    from odw2json.config_loader import load_app_config, load_registry

    calls = []
    real = pipeline.process_file_ex

    def spy(pdf, registry, ingest_cfg=None):
        calls.append(Path(pdf).name)
        return real(pdf, registry, ingest_cfg)

    monkeypatch.setattr(jobs_mod.pipeline, "process_file_ex", spy)
    job = store.create([(n, (P01 / n).read_bytes()) for n in PDFS])
    store.process(job.id)
    assert calls == PDFS
    registry, cfg = load_registry(), load_app_config().get("ingest")
    for entry, name in zip(store.snapshot(job)["files"], PDFS, strict=True):
        doc, cls, res = real(P01 / name, registry, cfg)
        assert entry["classification"]["doc_type"] == cls.doc_type
        assert entry["data"] == (res.data if res else {})
        assert entry["trace"] == ([asdict(t) for t in res.trace] if res else [])
        assert entry["warnings"] == list(doc.warnings) and entry["pages"] == len(doc.pages)


def test_classification_evidence_is_passed_to_result(store, monkeypatch):
    from odw2json.api import jobs as jobs_mod
    from odw2json.contracts import Classification, Document

    def fake(pdf, registry, ingest_cfg=None):
        cls = Classification(doc_type=None, confidence=0.1, method="keywords")
        cls.evidence = ["brak słów kluczowych odwołania", "brak kwoty przelewu"]
        return Document(path=Path(pdf), text="x", pages=["x"]), cls, None

    monkeypatch.setattr(jobs_mod.pipeline, "process_file_ex", fake)
    job = store.create([("a.pdf", (P01 / "pelnomocnictwo.pdf").read_bytes())])
    store.process(job.id)
    (f,) = store.snapshot(job)["files"]
    assert f["classification"]["evidence"] == ["brak słów kluczowych odwołania", "brak kwoty przelewu"]
    assert f["data"] == {}


def test_classification_evidence_defaults_to_empty_list(done_job):
    _, body = done_job
    for f in body["files"]:
        assert isinstance(f["classification"]["evidence"], list)
        assert all(isinstance(e, str) for e in f["classification"]["evidence"])


def test_too_many_files_rejected_before_processing(client, store, monkeypatch):
    monkeypatch.setattr(api, "MAX_FILES", 3)
    files = [("files", (f"p{i}.pdf", b"%PDF-1.4 x", "application/pdf")) for i in range(4)]
    for url in ("/api/jobs", "/api/process"):
        resp = client.post(url, files=files)
        assert resp.status_code == 400, url
        assert "najwyżej 3 plik" in resp.json()["detail"]
    assert not store._jobs


def test_default_limit_is_50_files():
    assert api.MAX_FILES == 50
    assert api.MAX_TOTAL_BYTES >= api.MAX_FILE_BYTES


def test_total_size_limit_rejected_with_413(client, store, monkeypatch):
    monkeypatch.setattr(api, "MAX_TOTAL_BYTES", 1000)
    files = [("files", (f"p{i}.pdf", b"%PDF-1.4" + b"x" * 400, "application/pdf")) for i in range(3)]
    for url in ("/api/jobs", "/api/process"):
        resp = client.post(url, files=files)
        assert resp.status_code == 413, url
        assert "Łączny rozmiar" in resp.json()["detail"]
    assert not store._jobs


def test_jobs_are_processed_at_most_n_in_parallel(tmp_path, monkeypatch):
    import threading

    from odw2json.api import jobs as jobs_mod

    store = JobStore(tmp_path / "jobs", max_parallel=2)
    gate = threading.Event()
    lock = threading.Lock()
    running = {"now": 0, "max": 0}

    def slow(pdf, registry, ingest_cfg=None):
        with lock:
            running["now"] += 1
            running["max"] = max(running["max"], running["now"])
        gate.wait(10)
        with lock:
            running["now"] -= 1
        raise RuntimeError("koniec")

    monkeypatch.setattr(jobs_mod.pipeline, "process_file_ex", slow)
    jobs = [store.create([("a.pdf", b"%PDF-1.4")]) for _ in range(4)]
    threads = [threading.Thread(target=store.process, args=(j.id,)) for j in jobs]
    for th in threads:
        th.start()
    t0 = time.monotonic()
    while running["now"] < 2 and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    time.sleep(0.1)
    statuses = sorted(store.snapshot(j)["status"] for j in jobs)
    assert running["now"] == 2
    assert statuses == ["pending", "pending", "running", "running"], "pozostałe czekają w kolejce"
    gate.set()
    for th in threads:
        th.join(10)
    assert running["max"] == 2
    assert all(store.snapshot(j)["status"] == "done" for j in jobs)


@pytest.mark.parametrize("bad", ["..", ".", "...", "/", "a/.."])
def test_legacy_process_rejects_dot_names_with_400(client, bad):
    resp = client.post("/api/process", files=[("files", (bad, (P01 / "pelnomocnictwo.pdf").read_bytes()))])
    assert resp.status_code == 400, resp.text
    assert "nazw" in resp.json()["detail"]


def test_legacy_process_strips_path_from_name(client):
    content = (P01 / "pelnomocnictwo.pdf").read_bytes()
    resp = client.post("/api/process", files=[("files", ("../../zła nazwa.pdf", content))])
    assert resp.status_code == 200
    (r,) = resp.json()
    assert r["file"] == "zła nazwa.pdf"
    assert r["classification"]["doc_type"] == "pelnomocnictwo"


@pytest.mark.parametrize("bad", ["..", "."])
def test_jobs_report_dot_names_as_file_error(client, bad):
    job_id = _submit(client, [(bad, (P01 / "pelnomocnictwo.pdf").read_bytes(), "application/pdf")])
    (f,) = _wait(client, job_id)["files"]
    assert f["status"] == "error" and "nazw" in f["error"]


def test_queued_jobs_do_not_hold_server_threads(tmp_path, monkeypatch):
    """Joby czekają w kolejce własnego executora joba, a nie w wątkach puli serwera."""
    import threading

    from odw2json.api import jobs as jobs_mod

    store = JobStore(tmp_path / "jobs", max_parallel=2)
    gate = threading.Event()

    def slow(pdf, registry, ingest_cfg=None):
        gate.wait(10)
        raise RuntimeError("koniec")

    monkeypatch.setattr(jobs_mod.pipeline, "process_file_ex", slow)
    jobs = [store.create([("a.pdf", b"%PDF-1.4")]) for _ in range(6)]
    t0 = time.monotonic()
    for j in jobs:
        store.submit(j.id)  # nie blokuje wywołującego
    assert time.monotonic() - t0 < 1
    deadline = time.monotonic() + 5
    while sum(store.snapshot(j)["status"] == "running" for j in jobs) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    statuses = [store.snapshot(j)["status"] for j in jobs]
    assert statuses.count("running") == 2 and statuses.count("pending") == 4
    gate.set()
    store.shutdown()
    assert all(store.snapshot(j)["status"] == "done" for j in jobs)


def test_legacy_process_shares_processing_slots(client, store, monkeypatch):
    used = []
    real = store.run_limited

    def spy(fn, *args):
        used.append(fn.__name__)
        return real(fn, *args)

    monkeypatch.setattr(store, "run_limited", spy)
    resp = client.post("/api/process", files=[("files", _pdf("pelnomocnictwo.pdf"))])
    assert resp.status_code == 200
    assert used == ["process_file"]


def test_non_numeric_content_length_is_400(client):
    resp = client.post(
        "/api/jobs",
        content=b"x",
        headers={"content-length": "abc", "content-type": "multipart/form-data; boundary=x"},
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("raw", [".pdf", "...pdf", " .PDF"])
def test_name_made_only_of_extension_keeps_pdf_extension(raw):
    from odw2json.api.files import display_name, storage_name

    shown = display_name(raw)
    assert shown.lower().endswith(".pdf") and shown[:-4].strip(". ")
    assert storage_name(shown, set()).lower().endswith(".pdf")
