"""Zadania przetwarzania (joby) dla GUI: pliki w `output/.jobs/<job_id>/`, stan w pamięci.

Przetwarzanie korzysta wyłącznie z publicznych API etapów (ingest -> classify -> extract),
tak jak `pipeline.process_file`, ale dodatkowo zwraca ostrzeżenia i liczbę stron dokumentu.
"""

from __future__ import annotations

import logging
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from odw2json import classify, extract, ingest
from odw2json.api.files import display_name, storage_name
from odw2json.config_loader import load_app_config, load_registry
from odw2json.contracts import IngestError

log = logging.getLogger("odw2json.api")

JOB_TTL_S = 24 * 3600
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass
class FileEntry:
    file: str  # nazwa do wyświetlenia (jak wgrana, bez ścieżki)
    name: str  # bezpieczna nazwa na dysku i w URL
    status: str = "pending"  # pending | done | error
    error: str | None = None
    classification: dict | None = None
    data: dict | None = None
    trace: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages: int | None = None


@dataclass
class Job:
    id: str
    dir: Path
    created: float
    status: str = "pending"  # pending | running | done | error
    error: str | None = None
    files: list[FileEntry] = field(default_factory=list)

    def entry(self, name: str) -> FileEntry | None:
        return next((f for f in self.files if f.name == name), None)


class JobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # --- tworzenie i odczyt ---
    def create(self, items: list[tuple]) -> Job:
        """items: (nazwa_wgrana, zawartość[, błąd_walidacji]). Pliki z błędem nie trafiają na dysk."""
        self.cleanup(JOB_TTL_S)
        job_id = uuid.uuid4().hex
        job = Job(id=job_id, dir=self.root / job_id, created=time.time())
        job.dir.mkdir(parents=True, exist_ok=True)
        taken: set[str] = set()
        for raw_name, content, *rest in items:
            shown = display_name(raw_name)
            entry = FileEntry(file=shown, name=storage_name(shown, taken))
            taken.add(entry.name)
            if rest and rest[0]:
                entry.status, entry.error = "error", rest[0]
            else:
                (job.dir / entry.name).write_bytes(content)
            job.files.append(entry)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        if not _JOB_ID.match(job_id or ""):
            return None
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self, job: Job) -> dict[str, Any]:
        with self._lock:
            files = [asdict(f) for f in job.files]
            return {
                "job_id": job.id,
                "status": job.status,
                "error": job.error,
                "processed": sum(f["status"] != "pending" for f in files),
                "total": len(files),
                "files": files,
            }

    # --- przetwarzanie ---
    def process(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        with self._lock:
            job.status = "running"
        try:
            registry = load_registry()
            ingest_cfg = load_app_config().get("ingest")
            for entry in job.files:
                if entry.status != "pending":
                    continue
                result = self._process_one(job.dir / entry.name, registry, ingest_cfg)
                with self._lock:
                    for k, v in result.items():
                        setattr(entry, k, v)
            with self._lock:
                job.status = "done"
        except Exception:  # awaria całego joba (np. zła konfiguracja)
            log.exception("job %s nieudany", job_id)
            with self._lock:
                job.status, job.error = (
                    "error",
                    "Nie udało się przetworzyć plików. Spróbuj ponownie.",
                )

    @staticmethod
    def _process_one(pdf: Path, registry, ingest_cfg) -> dict[str, Any]:
        try:
            doc = ingest.load(pdf, cfg=ingest_cfg)
            cls = classify.classify(doc, registry)
            res = extract.extract(doc, registry[cls.doc_type]) if cls.doc_type else None
        except IngestError as e:
            return {"status": "error", "error": f"Nie udało się odczytać pliku: {e}"}
        except Exception:
            log.exception("plik %s nieudany", pdf.name)
            return {"status": "error", "error": "Nie udało się przetworzyć pliku. Spróbuj ponownie."}
        return {
            "status": "done",
            "classification": {"doc_type": cls.doc_type, "confidence": cls.confidence, "method": cls.method},
            "data": res.data if res else {},
            "trace": [asdict(t) for t in res.trace] if res else [],
            "warnings": list(doc.warnings),
            "pages": len(doc.pages),
        }

    # --- sprzątanie ---
    def cleanup(self, max_age_s: float = JOB_TTL_S, drop_orphans: bool = False) -> None:
        """Usuwa joby starsze niż max_age_s oraz katalogi bez jobu w pamięci (stare albo wszystkie)."""
        now = time.time()
        with self._lock:
            expired = [j for j in self._jobs.values() if now - j.created >= max_age_s]
            for j in expired:
                del self._jobs[j.id]
            known = set(self._jobs)
        for j in expired:
            shutil.rmtree(j.dir, ignore_errors=True)
        if not self.root.is_dir():
            return
        for d in self.root.iterdir():
            if not d.is_dir() or d.name in known or not _JOB_ID.match(d.name):
                continue
            if drop_orphans or now - d.stat().st_mtime >= max_age_s:
                shutil.rmtree(d, ignore_errors=True)
