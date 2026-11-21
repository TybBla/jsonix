"""Sklejenie etapów: ingest -> classify -> extract -> zapis JSON (+ trace)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from odw2json import classify, extract, ingest
from odw2json.config_loader import DocTypeConfig, load_app_config, load_registry
from odw2json.contracts import Classification, ExtractionResult

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


def process_file(
    pdf: Path, registry: dict[str, DocTypeConfig]
) -> tuple[Classification, ExtractionResult | None]:
    doc = ingest.load(pdf)
    cls = classify.classify(doc, registry)
    if cls.doc_type is None:
        return cls, None
    return cls, extract.extract(doc, registry[cls.doc_type])


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def write_outputs(
    pdf: Path,
    input_dir: Path,
    output_dir: Path,
    cls: Classification,
    res: ExtractionResult | None,
    app_cfg: dict,
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
                    "source": str(pdf),
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
) -> RunReport:
    """Przetwarza wszystkie PDF-y z input_dir (case'y w podfolderach lub luzem)."""
    app_cfg = app_cfg if app_cfg is not None else load_app_config()
    registry = registry or load_registry()
    report = RunReport()
    pdfs = sorted(p for p in Path(input_dir).rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    for pdf in pdfs:
        try:
            cls, res = process_file(pdf, registry)
            write_outputs(pdf, Path(input_dir), Path(output_dir), cls, res, app_cfg)
            report.processed += 1
            key = cls.doc_type or "nieznany"
            report.by_type[key] = report.by_type.get(key, 0) + 1
            report.unknown += cls.doc_type is None
            log.info("%s -> %s (%.2f)", pdf.relative_to(input_dir), key, cls.confidence)
        except Exception as e:  # jeden zły plik nie przerywa batcha
            log.error("%s: %s", pdf, e)
            report.errors.append(FileError(pdf, f"{type(e).__name__}: {e}"))
    return report
