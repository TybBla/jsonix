"""Sklejenie etapów: ingest -> classify -> extract -> zapis JSON (+ trace)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from odw2json import classify, extract, ingest
from odw2json.config_loader import DocTypeConfig, load_app_config, load_registry
from odw2json.contracts import Classification, Document, ExtractionResult
from odw2json.logging_setup import new_run_id

log = logging.getLogger("odw2json")


@dataclass
class FileError:
    path: Path
    error: str


@dataclass
class RunReport:
    processed: int = 0
    unknown: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    errors: list[FileError] = field(default_factory=list)
    run_id: str = ""
    total_ms: int = 0


def process_file_ex(
    pdf: Path, registry: dict[str, DocTypeConfig], ingest_cfg: dict | None = None
) -> tuple[Document, Classification, ExtractionResult | None]:
    """Jak ``process_file``, ale zwraca też ``Document`` (``ocr_used``/``backend``/``warnings`` do trace)."""
    doc = ingest.load(pdf, cfg=ingest_cfg)
    cls = classify.classify(doc, registry)
    if cls.doc_type is None:
        return doc, cls, None
    return doc, cls, extract.extract(doc, registry[cls.doc_type])


def process_file(
    pdf: Path, registry: dict[str, DocTypeConfig], ingest_cfg: dict | None = None
) -> tuple[Classification, ExtractionResult | None]:
    _, cls, res = process_file_ex(pdf, registry, ingest_cfg)
    return cls, res


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def write_outputs(
    pdf: Path,
    input_dir: Path,
    output_dir: Path,
    cls: Classification,
    res: ExtractionResult | None,
    app_cfg: dict,
    run_id: str | None = None,
    doc: Document | None = None,
) -> Path | None:
    rel = pdf.relative_to(input_dir).with_suffix(".json")
    target = output_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if res is not None:
        target.write_text(_dump(res.data), encoding="utf-8")
    elif app_cfg.get("unknown_output", "empty_object") == "empty_object":
        target.write_text("{}", encoding="utf-8")
    elif app_cfg.get("unknown_output") == "empty_file":
        target.write_text("", encoding="utf-8")
    else:
        target = None
    if app_cfg.get("write_trace", True):
        tr = output_dir / ".trace" / rel.with_suffix(".trace.json")
        tr.parent.mkdir(parents=True, exist_ok=True)
        tr.write_text(
            _dump(
                {
                    "run_id": run_id,
                    "source": str(pdf),
                    "ocr_used": doc.ocr_used if doc else None,
                    "backend": doc.backend if doc else None,
                    "warnings": list(doc.warnings) if doc else [],
                    "classification": asdict(cls),
                    "trace": [asdict(f) for f in res.trace] if res else [],
                }
            ),
            encoding="utf-8",
        )
    return target


def run(
    input_dir: Path,
    output_dir: Path,
    app_cfg: dict | None = None,
    registry: dict[str, DocTypeConfig] | None = None,
    run_id: str | None = None,
) -> RunReport:
    """Przetwarza wszystkie PDF-y z input_dir (case'y w podfolderach lub luzem)."""
    app_cfg = app_cfg if app_cfg is not None else load_app_config()
    registry = registry or load_registry()
    ingest_cfg = app_cfg.get("ingest")
    effective = ingest_cfg if ingest_cfg is not None else load_app_config().get("ingest") or {}
    ingest.validate_ingest_cfg(effective)  # błąd konfiguracji przerywa run
    run_id = run_id or new_run_id()
    report = RunReport(run_id=run_id)
    started = datetime.now(UTC)
    t_run = time.perf_counter()
    pdfs = sorted(p for p in Path(input_dir).rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    for pdf in pdfs:
        t0 = time.perf_counter()
        rel = str(pdf.relative_to(input_dir))
        try:
            doc, cls, res = process_file_ex(pdf, registry, ingest_cfg)
            write_outputs(pdf, Path(input_dir), Path(output_dir), cls, res, app_cfg, run_id, doc=doc)
            report.processed += 1
            key = cls.doc_type or "nieznany"
            report.by_type[key] = report.by_type.get(key, 0) + 1
            report.unknown += cls.doc_type is None
            log.info(
                "%s -> %s (%.2f)",
                rel,
                key,
                cls.confidence,
                extra={
                    "event": "file_processed",
                    "file": rel,
                    "doc_type": cls.doc_type,
                    "ms": round((time.perf_counter() - t0) * 1000),
                },
            )
        except Exception as e:  # jeden zły plik nie przerywa batcha
            msg = f"{type(e).__name__}: {e}"
            log.error(
                "%s: %s",
                pdf,
                e,
                extra={
                    "event": "file_error",
                    "file": rel,
                    "doc_type": None,
                    "ms": round((time.perf_counter() - t0) * 1000),
                },
            )
            report.errors.append(FileError(pdf, msg))
    report.total_ms = round((time.perf_counter() - t_run) * 1000)
    summary = {
        "run_id": run_id,
        "started": started.isoformat(),
        "finished": datetime.now(UTC).isoformat(),
        "total_ms": report.total_ms,
        "processed": report.processed,
        "by_type": report.by_type,
        "unknown": report.unknown,
        "errors": [{"file": str(e.path), "error": e.error} for e in report.errors],
    }
    logs = Path(output_dir) / ".logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / f"{run_id}.summary.json").write_text(_dump(summary), encoding="utf-8")
    return report
