"""REST API (FastAPI) + serwowanie GUI (statyczne pliki z web/static).

Endpointy pod GUI (etap E8E9): joby przetwarzania wielu PDF w tle, pobieranie PDF/JSON/ZIP.
`POST /api/process` zostaje dla zgodności (przetwarzanie synchroniczne, bez zapisu).
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import tempfile
import zipfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from odw2json import pipeline
from odw2json.api.files import (
    content_disposition,
    display_name,
    has_pdf_header,
    json_name,
    storage_name,
    valid_name,
)
from odw2json.api.jobs import Job, JobStore
from odw2json.config_loader import ROOT_DIR, load_registry

MAX_FILE_BYTES = int(float(os.environ.get("ODW2JSON_MAX_FILE_MB", "25")) * 1024 * 1024)
MAX_FILES = int(os.environ.get("ODW2JSON_MAX_FILES", "50"))  # plików na jedno żądanie
MAX_TOTAL_BYTES = int(float(os.environ.get("ODW2JSON_MAX_TOTAL_MB", "200")) * 1024 * 1024)
MAX_PARALLEL_JOBS = int(os.environ.get("ODW2JSON_MAX_PARALLEL_JOBS", "2"))
UPLOAD_PATHS = ("/api/jobs", "/api/process")
JOBS_DIR = Path(os.environ.get("ODW2JSON_JOBS_DIR", ROOT_DIR / "output" / ".jobs"))
STATIC_DIR = ROOT_DIR / "web" / "static"

# Rejestr Windows potrafi podać text/plain dla .js/.mjs — przeglądarka odrzuci wtedy moduł ES.
for _type, _ext in (
    ("text/javascript", ".js"),
    ("text/javascript", ".mjs"),
    ("text/css", ".css"),
    ("font/woff2", ".woff2"),
):
    mimetypes.add_type(_type, _ext)

_store = JobStore(JOBS_DIR, max_parallel=MAX_PARALLEL_JOBS)


def get_store() -> JobStore:
    return _store


StoreDep = Annotated[JobStore, Depends(get_store)]


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _store.cleanup(drop_orphans=True)  # katalogi jobów z poprzedniego uruchomienia
    yield
    _store.shutdown()


app = FastAPI(title="jsonix", version="0.2.0", lifespan=_lifespan)


def _too_big() -> str:
    limit = _mb(MAX_TOTAL_BYTES)
    return f"Łączny rozmiar plików musi być mniejszy niż {limit}. Wyślij pliki w mniejszych częściach."


@app.middleware("http")
async def _limit_upload_size(request, call_next):
    """Odrzuca za duże żądanie po nagłówku Content-Length, zanim serwer odczyta i rozpakuje treść."""
    if request.method == "POST" and request.url.path in UPLOAD_PATHS:
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Nieprawidłowy nagłówek Content-Length."}, status_code=400)
        # zapas na nagłówki części multipart (ok. 1 KB na plik)
        if length > MAX_TOTAL_BYTES + MAX_FILES * 1024:
            return JSONResponse({"detail": _too_big()}, status_code=413)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/doctypes")
def doctypes() -> list[dict]:
    return [{"id": k, "title": c.title} for k, c in load_registry().items()]


# --- joby (GUI) ---


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):g} MB"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    """Odczyt plików z limitami żądania: liczba plików (400) i łączny rozmiar (413).

    Każdy plik jest czytany najwyżej do MAX_FILE_BYTES + 1 (za duży plik to błąd tego pliku).
    """
    if len(files) > MAX_FILES:
        raise HTTPException(
            400,
            f"Możesz wysłać najwyżej {MAX_FILES} {_plural(MAX_FILES, 'plik', 'pliki', 'plików')} naraz. "
            "Podziel pliki na mniejsze części.",
        )
    out, total = [], 0
    for f in files:
        content = await f.read(MAX_FILE_BYTES + 1)
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(413, _too_big())
        out.append((f.filename or "", content))
    return out


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
    files: Annotated[list[UploadFile], File()],
    store: StoreDep,
) -> dict:
    items = [
        (name, content, _validate(name.replace("\\", "/").rsplit("/", 1)[-1], content))
        for name, content in await _read_uploads(files)
    ]
    job = await run_in_threadpool(store.create, items)
    store.submit(job.id)  # kolejka jobów magazynu (najwyżej MAX_PARALLEL_JOBS naraz)
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
async def process(files: list[UploadFile], store: StoreDep) -> list[dict]:
    uploads = await _read_uploads(files)
    for raw, _ in uploads:
        if not valid_name(raw):
            raise HTTPException(
                400, f"Nieprawidłowa nazwa pliku: „{raw}”. Zmień nazwę pliku i wyślij go ponownie."
            )
    registry = load_registry()
    out = []
    taken: set[str] = set()
    with tempfile.TemporaryDirectory() as tmp:
        for raw, content in uploads:
            shown = display_name(raw)  # te same funkcje nazw co w jobach (bez ścieżki, bez `..`)
            if len(content) > MAX_FILE_BYTES:
                out.append(
                    {"file": shown, "error": f"Wybrany plik musi być mniejszy niż {_mb(MAX_FILE_BYTES)}."}
                )
                continue
            p = Path(tmp) / storage_name(shown, taken)
            taken.add(p.name)
            p.write_bytes(content)
            try:
                # wspólny limit równoległości z jobami (ciężkie przetwarzanie, np. OCR)
                cls, res = await run_in_threadpool(store.run_limited, pipeline.process_file, p, registry)
                out.append(
                    {
                        "file": shown,
                        "classification": asdict(cls),
                        "data": res.data if res else None,
                        "trace": [asdict(t) for t in res.trace] if res else [],
                    }
                )
            except Exception as e:
                out.append({"file": shown, "error": f"{type(e).__name__}: {e}"})
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
