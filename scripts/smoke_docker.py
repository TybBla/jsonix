"""Smoke Docker Compose: build, start z healthcheckiem, GUI/API, wsad CLI w kontenerze = wynik CLI na hoście.

Użycie: python scripts/smoke_docker.py [--port 8798] [--keep] [--no-build] [--no-host-compare]
Kod wyjścia 0 = OK, 1 = błąd, 2 = brak Dockera.

Kroki:
1. `docker compose up -d --build` (osobny projekt `jsonix-smoke`, bez pliku .env — tryb bez LLM),
2. czekanie na status `healthy` (healthcheck z docker-compose.yml),
3. te same sprawdzenia GUI/API co `scripts/smoke_gui.py` (3 PDF z przyklad_01, kontrakt, JSON/PDF/ZIP),
4. wsad `python -m odw2json run` w kontenerze na przyklad_01 + jednym skanie (OCR w obrazie),
5. porównanie JSON-ów z wsadu w kontenerze z CLI uruchomionym na hoście (te same dane w obu miejscach),
6. `docker compose down` (chyba że --keep).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_gui import P01, REPO, SmokeError, check, smoke  # noqa: E402

PROJECT = "jsonix-smoke"
SCAN = REPO / "data" / "train" / "skany" / "potwierdzenia" / "0007" / "0007.pdf"
HEALTH_TIMEOUT_S = 300


def compose(*args: str, env: dict, capture: bool = False) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-p", PROJECT, *args]
    return subprocess.run(
        cmd,
        cwd=REPO,
        env=env,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def wait_healthy(env: dict) -> None:
    cid = compose("ps", "-q", "app", env=env, capture=True).stdout.strip()
    check(bool(cid), "kontener app nie wystartował")
    t0 = time.monotonic()
    while True:
        r = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", cid],
            capture_output=True,
            text=True,
            check=False,
        )
        status = r.stdout.strip()
        if status == "healthy":
            return
        check(status != "unhealthy", "healthcheck: unhealthy")
        waited = time.monotonic() - t0
        check(waited < HEALTH_TIMEOUT_S, f"healthcheck: brak 'healthy' po {HEALTH_TIMEOUT_S} s ({status})")
        time.sleep(2)


def prepare_input(root: Path, with_scan: bool) -> Path:
    inp = root / "input"
    case = inp / "przyklad_01"
    case.mkdir(parents=True)
    for pdf in P01.glob("*.pdf"):
        shutil.copy2(pdf, case / pdf.name)
    if with_scan and SCAN.is_file():
        (inp / "skan").mkdir()
        shutil.copy2(SCAN, inp / "skan" / SCAN.name)
    return inp


def results(out: Path) -> dict[str, object]:
    """Wynikowe JSON-y (bez katalogów technicznych .trace/.logs/.jobs)."""
    found = {}
    for p in sorted(out.rglob("*.json")):
        rel = p.relative_to(out)
        if any(part.startswith(".") for part in rel.parts):
            continue
        found[rel.as_posix()] = json.loads(p.read_text(encoding="utf-8"))
    return found


def batch_in_container(inp: Path, out: Path, env: dict) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    r = compose(
        "run",
        "--rm",
        "--no-deps",
        "-v",
        f"{inp}:/app/input:ro",
        "-v",
        f"{out}:/app/output",
        "app",
        "python",
        "-m",
        "odw2json",
        "run",
        "/app/input",
        "/app/output",
        env=env,
        capture=True,
    )
    check(r.returncode == 0, f"wsad w kontenerze: kod {r.returncode}\n{r.stderr[-2000:]}")
    return results(out)


def batch_on_host(inp: Path, out: Path) -> dict[str, object]:
    env = {**os.environ, "LLM_MODE": os.environ.get("LLM_MODE", "replay")}
    r = subprocess.run(
        [sys.executable, "-m", "odw2json", "run", str(inp), str(out)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    check(r.returncode == 0, f"wsad na hoście: kod {r.returncode}\n{r.stderr[-2000:]}")
    return results(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8798)
    ap.add_argument("--keep", action="store_true", help="nie zatrzymuj kontenera po teście")
    ap.add_argument("--no-build", action="store_true", help="użyj zbudowanego obrazu")
    ap.add_argument(
        "--no-host-compare",
        action="store_true",
        help="pomiń porównanie z CLI na hoście (np. host bez zależności OCR)",
    )
    a = ap.parse_args(argv)
    if shutil.which("docker") is None:
        print("SMOKE DOCKER: brak polecenia docker", file=sys.stderr)
        return 2
    env = {**os.environ, "JSONIX_PORT": str(a.port), "MSYS_NO_PATHCONV": "1"}
    base = f"http://127.0.0.1:{a.port}"
    try:
        up = compose("up", "-d", *([] if a.no_build else ["--build"]), env=env)
        check(up.returncode == 0, f"docker compose up: kod {up.returncode}")
        wait_healthy(env)
        smoke(base)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # skan porównujemy tylko w kontenerze (host może nie mieć OCR); na hoście tylko PDF z tekstem
            inp = prepare_input(root, with_scan=True)
            in_docker = batch_in_container(inp, root / "out-docker", env)
            names = set(in_docker)
            for pdf in P01.glob("*.pdf"):
                check(f"przyklad_01/{pdf.stem}.json" in names, f"brak wyniku dla {pdf.name}")
            if SCAN.is_file():
                scan = in_docker.get(f"skan/{SCAN.stem}.json")
                check(bool(scan), "skan: brak danych (OCR w obrazie nie działa?)")
            if not a.no_host_compare:
                text_only = prepare_input(root / "host", with_scan=False)
                on_host = batch_on_host(text_only, root / "out-host")
                for name, data in on_host.items():
                    same = in_docker.get(name) == data
                    check(same, f"{name}: wynik w kontenerze różni się od CLI na hoście")
    except (SmokeError, OSError, ValueError, KeyError) as e:
        print(f"SMOKE DOCKER FAIL: {e}", file=sys.stderr)
        if not a.keep:
            compose("down", env=env)
        return 1
    if not a.keep:
        compose("down", env=env)
    print("SMOKE DOCKER OK: healthy, GUI/API, wsad w kontenerze (w tym skan OCR) = CLI na hoście")
    return 0


if __name__ == "__main__":
    sys.exit(main())
