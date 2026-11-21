"""CLI: python -m odw2json run [input] [output]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from odw2json import pipeline
from odw2json.config_loader import ROOT_DIR, load_registry
from odw2json.logging_setup import new_run_id, setup_logging


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    ap = argparse.ArgumentParser(prog="odw2json", description="Odwołania KIO: PDF -> JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="przetwórz folder input/ do output/")
    r.add_argument("input", nargs="?", default=str(ROOT_DIR / "input"))
    r.add_argument("output", nargs="?", default=str(ROOT_DIR / "output"))
    r.add_argument("-v", "--verbose", action="store_true")
    r.add_argument("--log-file", default=None, help="domyślnie <output>/.logs/<run_id>.jsonl")
    sub.add_parser("doctypes", help="lista skonfigurowanych typów dokumentów")
    s = sub.add_parser("serve", help="uruchom API + GUI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    if a.cmd == "doctypes":
        for k, cfg in load_registry().items():
            print(f"{k}\t{cfg.title}")
        return 0
    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("odw2json.api:app", host=a.host, port=a.port)
        return 0
    out = Path(a.output)
    run_id = new_run_id()
    log_file = Path(a.log_file) if a.log_file else out / ".logs" / f"{run_id}.jsonl"
    setup_logging(a.verbose, log_file, run_id=run_id)
    rep = pipeline.run(Path(a.input), out, run_id=run_id)
    print(f"Przebieg: {run_id}")
    print(
        f"Przetworzono: {rep.processed}, typy: {rep.by_type}, błędy: {len(rep.errors)}, "
        f"czas: {rep.total_ms} ms"
    )
    for e in rep.errors:
        print(f"  BŁĄD {e.path}: {e.error}", file=sys.stderr)
    return 1 if rep.errors and not rep.processed else 0
