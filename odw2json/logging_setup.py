"""Konfiguracja logowania: konsola (czytelna) + plik JSON Lines, identyfikator przebiegu."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

LOGGER_NAME = "odw2json"
_FIELDS = ("file", "doc_type", "ms")


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


class JsonLinesFormatter(logging.Formatter):
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "run_id": self.run_id,
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        for k in _FIELDS:
            data[k] = getattr(record, k, None)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging(verbose: bool = False, log_file: Path | None = None, run_id: str | None = None) -> str:
    """Konfiguruje logger 'odw2json' (idempotentnie) i zwraca run_id."""
    run_id = run_id or new_run_id()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    for h in list(logger.handlers):
        if getattr(h, "_odw2json", False):
            logger.removeHandler(h)
            h.close()
    console = logging.StreamHandler()
    console.setLevel(logging.INFO if verbose else logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    console._odw2json = True  # type: ignore[attr-defined]
    logger.addHandler(console)
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(JsonLinesFormatter(run_id))
        fh._odw2json = True  # type: ignore[attr-defined]
        logger.addHandler(fh)
    return run_id
