"""Testy API pod GUI (etap E8E9, zadanie A1). Bez OCR: tylko PDF-y z warstwą tekstową."""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
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
        assert set(r["classification"]) == {"doc_type", "confidence", "method"}
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


@pytest.mark.parametrize("reserved", ["NUL.pdf", "con.pdf", "COM1.pdf", "lpt9.PDF", "aux"])
def test_windows_reserved_names_are_not_used_on_disk(reserved):
    from odw2json.api.files import storage_name

    stem = storage_name(reserved, set()).split(".")[0]
    assert stem.casefold() not in {"nul", "con", "com1", "lpt9", "aux"}


def test_failure_message_is_polish_without_internals(store, monkeypatch):
    from odw2json.api import jobs as jobs_mod

    def boom(*_a, **_k):
        raise RuntimeError(r"C:\sciezka\serwera boom")

    monkeypatch.setattr(jobs_mod.ingest, "load", boom)
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
