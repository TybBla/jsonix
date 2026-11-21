import json
import logging
import os
import re
import shutil
import subprocess
import sys

from odw2json import pipeline
from odw2json.config_loader import ROOT_DIR
from odw2json.logging_setup import reset_logging, setup_logging


def _inp(tmp_path, train_dir):
    inp = tmp_path / "in"
    inp.mkdir()
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "a.pdf")
    (inp / "broken.pdf").write_bytes(b"nie pdf")
    return inp


def test_run_id_format_and_idempotent(tmp_path):
    rid = setup_logging(False, tmp_path / "x.jsonl")
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{6}", rid)
    n = len(logging.getLogger("odw2json").handlers)
    setup_logging(False, tmp_path / "x.jsonl")
    assert len(logging.getLogger("odw2json").handlers) == n


def test_summary_jsonl_and_trace(tmp_path, train_dir):
    inp, out = _inp(tmp_path, train_dir), tmp_path / "out"
    rid = setup_logging(True, out / ".logs" / "r.jsonl")
    rep = pipeline.run(inp, out, app_cfg={"write_trace": True}, run_id=rid)
    for h in logging.getLogger("odw2json").handlers:
        h.flush()
    assert rep.run_id == rid
    s = json.loads((out / ".logs" / f"{rid}.summary.json").read_text(encoding="utf-8"))
    assert s["run_id"] == rid and s["processed"] == 1 and len(s["errors"]) == 1
    assert s["errors"][0]["file"].endswith("broken.pdf")
    assert sum(s["by_type"].values()) == 1 and "total_ms" in s
    lines = (out / ".logs" / "r.jsonl").read_text(encoding="utf-8").splitlines()
    recs = [json.loads(x) for x in lines]
    assert recs and all(r["run_id"] == rid for r in recs)
    assert {"file_processed", "file_error"} <= {r["event"] for r in recs}
    tr = json.loads((out / ".trace" / "a.trace.json").read_text(encoding="utf-8"))
    assert tr["run_id"] == rid


def test_summary_written_without_trace(tmp_path, train_dir):
    inp, out = _inp(tmp_path, train_dir), tmp_path / "out"
    rep = pipeline.run(inp, out, app_cfg={"write_trace": False})
    assert rep.run_id
    assert (out / ".logs" / f"{rep.run_id}.summary.json").exists()
    assert not (out / ".trace").exists()


def test_cli_polish_filename_cp1250(tmp_path, train_dir):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    shutil.copy(train_dir / "przyklad_01" / "odwolanie.pdf", inp / "zażółć gęślą.pdf")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    env["PYTHONIOENCODING"] = "ascii"  # CLI musi to nadpisac wlasnym reconfigure(utf-8)
    p = subprocess.run(
        [sys.executable, "-m", "odw2json", "run", str(inp), str(out)],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
    )
    assert p.returncode == 0, p.stderr
    assert (out / "zażółć gęślą.json").exists()
    assert "Przebieg" in p.stdout.decode("utf-8")


def test_reset_logging_closes_handlers(tmp_path):
    log = tmp_path / "l.jsonl"
    setup_logging(False, log)
    logging.getLogger("odw2json").info("x")
    reset_logging()
    lg = logging.getLogger("odw2json")
    assert lg.handlers == [] and lg.level == logging.NOTSET
    log.unlink()
    assert not log.exists()


def test_jsonl_exc_field(tmp_path):
    log = tmp_path / "l.jsonl"
    setup_logging(False, log)
    lg = logging.getLogger("odw2json")
    lg.info("ok")
    try:
        raise ZeroDivisionError("x")
    except ZeroDivisionError:
        lg.exception("boom")
    reset_logging()
    recs = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert recs[0]["exc"] is None
    assert "ZeroDivisionError" in recs[1]["exc"] and "Traceback" in recs[1]["exc"]
