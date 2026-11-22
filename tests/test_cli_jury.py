"""Profil jury: w output tylko <sprawa>/<plik>.json; logi poza output (log_dir)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from odw2json import cli, pipeline
from odw2json.config_loader import CONFIG_DIR

ROOT = Path(__file__).resolve().parents[1]
P01 = ROOT / "data" / "train" / "przyklad_01"
NAMES = ("odwolanie.pdf", "pelnomocnictwo.pdf")


def _input(tmp_path: Path) -> tuple[Path, Path]:
    case = tmp_path / "in" / "sprawa"
    case.mkdir(parents=True)
    for name in NAMES:
        shutil.copy(P01 / name, case / name)
    return tmp_path / "in", tmp_path / "out"


def _jury_overlay(tmp_path: Path) -> Path:
    """Prawdziwy config/app.jury.yaml, tylko ścieżki /tmp/... zamienione na katalogi testu (hermetyczność)."""
    cfg = yaml.safe_load((CONFIG_DIR / "app.jury.yaml").read_text(encoding="utf-8"))
    cfg["log_dir"] = str(tmp_path / "logs")
    cfg["ingest"]["ocr"]["cache_dir"] = str(tmp_path / "ocr-cache")
    f = tmp_path / "jury-test.yaml"
    f.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return f


def test_jury_profile_output_has_only_result_json(tmp_path, monkeypatch):
    inp, out = _input(tmp_path)
    monkeypatch.setenv("JSONIX_APP_CONFIG", str(_jury_overlay(tmp_path)))
    assert cli.main(["run", str(inp), str(out)]) == 0
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert files == sorted(f"sprawa/{n.replace('.pdf', '.json')}" for n in NAMES)
    for p in out.rglob("*.json"):
        assert isinstance(json.loads(p.read_text(encoding="utf-8")), dict)
    assert not any(p.name.startswith(".") for p in out.rglob("*")), "żadnych ukrytych katalogów w output"
    # logi i podsumowanie przebiegu są poza output
    logs = list((tmp_path / "logs").iterdir())
    assert any(p.suffix == ".jsonl" for p in logs) and any(p.name.endswith(".summary.json") for p in logs)


def test_default_profile_keeps_logs_and_trace_in_output(tmp_path, monkeypatch):
    """Bez nakładki zachowanie jak dotąd: <output>/.logs i <output>/.trace."""
    inp, out = _input(tmp_path)
    monkeypatch.delenv("JSONIX_APP_CONFIG", raising=False)
    assert cli.main(["run", str(inp), str(out)]) == 0
    assert list((out / ".logs").glob("*.jsonl")) and list((out / ".logs").glob("*.summary.json"))
    assert list((out / ".trace").rglob("*.trace.json"))


def test_log_file_flag_beats_log_dir(tmp_path, monkeypatch):
    inp, out = _input(tmp_path)
    monkeypatch.setenv("JSONIX_APP_CONFIG", str(_jury_overlay(tmp_path)))
    mine = tmp_path / "moj" / "log.jsonl"
    assert cli.main(["run", str(inp), str(out), "--log-file", str(mine)]) == 0
    assert mine.is_file()
    assert not list((tmp_path / "logs").glob("*.jsonl"))


def test_resolve_log_dir():
    out = Path("wyniki")
    assert pipeline.resolve_log_dir({}, out) == out / ".logs"
    assert pipeline.resolve_log_dir({"log_dir": None}, out) == out / ".logs"
    assert pipeline.resolve_log_dir({"log_dir": "logi"}, out) == ROOT / "logi"
    assert pipeline.resolve_log_dir({"log_dir": str(ROOT / "x")}, out) == ROOT / "x"


def test_dockerignore_keeps_jury_files_in_image():
    """RUN.md, config/app.jury.yaml i scripts/ są potrzebne w obrazie (docker run bez montowania config)."""
    patterns = [
        ln.strip().rstrip("/")
        for ln in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    for needed in ("RUN.md", "config", "config/app.jury.yaml", "scripts"):
        assert needed not in patterns, f"{needed} wykluczone z obrazu przez .dockerignore"
    assert (ROOT / "RUN.md").is_file() and (ROOT / "config" / "app.jury.yaml").is_file()


def test_run_md_command_is_single_noninteractive_docker_run():
    text = (ROOT / "RUN.md").read_text(encoding="utf-8")
    block = text.split("```")[1].removeprefix("bash").strip()
    assert "\n" not in block, "jedna komenda w jednej linii"
    assert block.startswith("docker run --rm ")
    for bad in (" -it", " -i ", " -t ", " -p ", " -d "):
        assert bad not in block
    assert "JSONIX_APP_CONFIG=config/app.jury.yaml" in block
    assert "-v /opt/solution/input:/app/input" in block and "-v /opt/solution/output:/app/output" in block
