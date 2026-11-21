"""Sektor C: REST API (FastAPI) + serwowanie zbudowanego GUI (web/dist).

Wersja bazowa: health, lista typów, przetworzenie wgranych PDF-ów. TODO(C): wyniki z trace,
podgląd PDF, edycja konfiguracji typów, front React.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.staticfiles import StaticFiles

from odw2json import pipeline
from odw2json.config_loader import ROOT_DIR, load_registry

app = FastAPI(title="Odwołania2JSON", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/doctypes")
def doctypes() -> list[dict]:
    return [{"id": k, "title": c.title} for k, c in load_registry().items()]


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


_dist = ROOT_DIR / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
