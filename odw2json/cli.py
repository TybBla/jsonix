"""CLI: python -m odw2json run [input] [output]"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from odw2json import pipeline
from odw2json.config_loader import ROOT_DIR, load_registry


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="odw2json", description="Odwołania KIO: PDF -> JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="przetwórz folder input/ do output/")
    r.add_argument("input", nargs="?", default=str(ROOT_DIR / "input"))
    r.add_argument("output", nargs="?", default=str(ROOT_DIR / "output"))
    r.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("doctypes", help="lista skonfigurowanych typów dokumentów")
    s = sub.add_parser("serve", help="uruchom API + GUI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if getattr(a, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(message)s")
    if a.cmd == "doctypes":
        for k, cfg in load_registry().items():
            print(f"{k}\t{cfg.title}")
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("odw2json.api:app", host=a.host, port=a.port)
        return 0
    rep = pipeline.run(Path(a.input), Path(a.output))
    print(f"Przetworzono: {rep.processed}, typy: {rep.by_type}, błędy: {len(rep.errors)}")
    for e in rep.errors:
        print(f"  BŁĄD {e.path}: {e.error}", file=sys.stderr)
    return 1 if rep.errors and not rep.processed else 0
