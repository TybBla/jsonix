"""REST API (FastAPI) + serwowanie GUI (statyczne pliki z web/static).

Endpointy pod GUI (etap E8E9): joby przetwarzania wielu PDF w tle, pobieranie PDF/JSON/ZIP.
`POST /api/process` zostaje dla zgodności (przetwarzanie synchroniczne, bez zapisu).
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from odw2json import pipeline
from odw2json.api.files import content_disposition, has_pdf_header, json_name
from odw2json.api.jobs import Job, JobStore
from odw2json.config_loader import ROOT_DIR, load_registry

MAX_FILE_BYTES = int(float(os.environ.get("ODW2JSON_MAX_FILE_MB", "25")) * 1024 * 1024)
JOBS_DIR = Path(os.environ.get("ODW2JSON_JOBS_DIR", ROOT_DIR / "output" / ".jobs"))
STATIC_DIR = ROOT_DIR / "web" / "static"

_store = JobStore(JOBS_DIR)


def get_store() -> JobStore:
    return _store


StoreDep = Annotated[JobStore, Depends(get_store)]


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _store.cleanup(drop_orphans=True)  # katalogi jobów z poprzedniego uruchomienia
    yield


app = FastAPI(title="Odwołania2JSON", version="0.2.0", lifespan=_lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/doctypes")
def doctypes() -> list[dict]:
    return [{"id": k, "title": c.title} for k, c in load_registry().items()]


# --- joby (GUI) ---


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):g} MB"


def _validate(name: str, content: bytes) -> str | None:
    """Komunikat błędu po polsku (wg wzorców GOV.UK/Gov.pl) albo None."""
    if not name.lower().endswith(".pdf"):
        return "Wybrany plik musi być w formacie PDF."
    if not content:
        return "Wybrany plik jest pusty."
    if len(content) > MAX_FILE_BYTES:
        return f"Wybrany plik musi być mniejszy niż {_mb(MAX_FILE_BYTES)}."
    if not has_pdf_header(content[:1024]):
        return "Wybrany plik nie jest prawidłowym dokumentem PDF."
    return None


@app.post("/api/jobs", status_code=202)
async def create_job(
    background: BackgroundTasks,
    files: Annotated[list[UploadFile], File()],
    store: StoreDep,
) -> dict:
    items = []
    for f in files:
        content = await f.read(MAX_FILE_BYTES + 1)
        name = f.filename or ""
        items.append((name, content, _validate(name.replace("\\", "/").rsplit("/", 1)[-1], content)))
    job = await run_in_threadpool(store.create, items)
    background.add_task(store.process, job.id)
    return {"job_id": job.id, "status_url": f"/api/jobs/{job.id}"}


def _job(job_id: str, store: JobStore) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Nie znaleziono zadania. Mogło wygasnąć — wgraj pliki ponownie.")
    return job


def _dump(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, store: StoreDep) -> dict:
    return store.snapshot(_job(job_id, store))


@app.get("/api/jobs/{job_id}/files/{name}/pdf")
def job_file_pdf(job_id: str, name: str, store: StoreDep):
    job = _job(job_id, store)
    entry = job.entry(name)
    path = job.dir / name if entry else None
    if entry is None or path is None or not path.is_file():
        raise HTTPException(404, "Nie znaleziono pliku w tym zadaniu.")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(entry.file).replace("attachment", "inline", 1)},
    )


@app.get("/api/jobs/{job_id}/files/{name}/json")
def job_file_json(job_id: str, name: str, store: StoreDep):
    job = _job(job_id, store)
    entry = job.entry(name)
    if entry is None:
        raise HTTPException(404, "Nie znaleziono pliku w tym zadaniu.")
    if entry.status != "done" or entry.data is None:
        raise HTTPException(404, "Ten plik nie ma wyniku. Sprawdź komunikat błędu przy pliku.")
    return Response(
        _dump(entry.data),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": content_disposition(json_name(entry.file))},
    )


@app.get("/api/jobs/{job_id}/zip")
def job_zip(job_id: str, store: StoreDep):
    job = _job(job_id, store)
    snap = store.snapshot(job)
    if snap["status"] in ("pending", "running"):
        raise HTTPException(409, "Analiza jeszcze trwa. Poczekaj na jej zakończenie i spróbuj ponownie.")
    if not any(f["status"] == "done" and f["data"] is not None for f in snap["files"]):
        raise HTTPException(404, "Brak wyników do pobrania. Żaden plik nie został przetworzony.")
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in snap["files"]:
            if f["status"] != "done" or f["data"] is None:
                continue
            arc, n = json_name(f["file"]), 2
            while arc in used:
                arc, n = f"{json_name(f['file'])[:-5]}_{n}.json", n + 1
            used.add(arc)
            zf.writestr(arc, _dump(f["data"]))
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition("wyniki.zip")},
    )


# --- zgodność wstecz ---


@app.post("/api/process")
async def process(files: list[UploadFile]) -> list[dict]:
    registry = load_registry()
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            p = Path(tmp) / Path(f.filename or "dokument.pdf").name
            p.write_bytes(await f.read())
            try:
                cls, res = pipeline.process_file(p, registry)
                out.append(
                    {
                        "file": p.name,
                        "classification": asdict(cls),
                        "data": res.data if res else None,
                        "trace": [asdict(t) for t in res.trace] if res else [],
                    }
                )
            except Exception as e:
                out.append({"file": p.name, "error": f"{type(e).__name__}: {e}"})
    return out


# --- GUI ---


@app.get("/", include_in_schema=False)
def index():
    page = STATIC_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(404, "GUI nie jest dostępne (brak web/static/index.html).")
    return FileResponse(page, media_type="text/html; charset=utf-8")


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
