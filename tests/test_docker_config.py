"""Docker Compose (wymóg nagrody §3.5): działa bez .env, ma healthcheck, obraz bez zbędnych plików.

Pełny test w kontenerze: `python scripts/smoke_docker.py` (wymaga Dockera, poza CI).
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_runs_without_env_file():
    app = _compose()["services"]["app"]
    env_files = app.get("env_file", [])
    assert env_files, "plik .env nadal wczytywany, gdy istnieje (klucz LLM)"
    for entry in env_files:
        optional = isinstance(entry, dict) and entry.get("required") is False
        assert optional, "brak .env nie może wywracać compose"


def test_compose_has_healthcheck_on_api_health():
    hc = _compose()["services"]["app"]["healthcheck"]
    assert "/api/health" in " ".join(hc["test"])
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile and "/api/health" in dockerfile


def test_compose_mounts_input_output_and_config():
    volumes = _compose()["services"]["app"]["volumes"]
    targets = {v.split(":")[1] for v in volumes}
    assert {"/app/input", "/app/output", "/app/config"} <= targets


def test_image_uses_python_313_and_skips_local_artifacts():
    assert (ROOT / "Dockerfile").read_text(encoding="utf-8").startswith("FROM python:3.13")
    ignored = set((ROOT / ".dockerignore").read_text(encoding="utf-8").split())
    for entry in (".env", ".venv", ".git", "output/", "input/", "data/"):
        assert entry in ignored, entry
