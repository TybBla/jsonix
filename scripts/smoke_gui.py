"""Smoke GUI/API: uruchamia serwer w tle, wysyła 3 PDF z przyklad_01, czeka na wynik, pobiera ZIP.

Użycie: python scripts/smoke_gui.py [--port 8799]. Kod wyjścia 0 = OK, 1 = błąd.
Bez zależności spoza requirements.txt (tylko biblioteka standardowa + uruchomiony serwer).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
P01 = REPO / "data" / "train" / "przyklad_01"
PDFS = ["odwolanie.pdf", "pelnomocnictwo.pdf", "potwierdzenie_przelewu.pdf"]
EXPECTED_TYPES = {"odwolanie", "pelnomocnictwo", "przelew"}
RESULT_KEYS = {"file", "name", "status", "error", "classification", "data", "trace", "warnings", "pages"}
TRACE_KEYS = {"path", "value", "method", "source_snippet", "page"}


class SmokeError(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SmokeError(msg)


def http(
    url: str, data: bytes | None = None, headers: dict | None = None, timeout: float = 30
) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def multipart(files: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for name, content in files:
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'.encode())
        buf.write(b"Content-Type: application/pdf\r\n\r\n")
        buf.write(content)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def wait_for_server(base: str, proc: subprocess.Popen, timeout: float = 60) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        check(proc.poll() is None, f"serwer zakończył się kodem {proc.returncode}")
        try:
            if http(f"{base}/api/health", timeout=2)[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.3)
    raise SmokeError("serwer nie wystartował w czasie")


def smoke(base: str) -> None:
    status, _, body = http(f"{base}/")
    check(status == 200 and b"jsonix" in body, "GET / nie zwraca strony GUI")
    status, headers, _ = http(f"{base}/static/vendor/pdfjs/pdf.min.mjs")
    check(
        status == 200 and "javascript" in headers.get("content-type", ""),
        "PDF.js niedostępny lub zły typ MIME",
    )

    data, ctype = multipart([(n, (P01 / n).read_bytes()) for n in PDFS])
    status, _, body = http(f"{base}/api/jobs", data, {"Content-Type": ctype})
    check(status == 202, f"POST /api/jobs: {status} {body[:200]!r}")
    job_id = json.loads(body)["job_id"]

    t0 = time.monotonic()
    while True:
        status, _, body = http(f"{base}/api/jobs/{job_id}")
        check(status == 200, f"GET /api/jobs/{job_id}: {status}")
        job = json.loads(body)
        if job["status"] in ("done", "error"):
            break
        check(time.monotonic() - t0 < 300, "przetwarzanie trwa za długo")
        time.sleep(0.5)
    check(job["status"] == "done", f"job zakończony statusem {job['status']}: {job.get('error')}")
    check(job["processed"] == job["total"] == 3, f"postęp {job['processed']}/{job['total']}")

    types = set()
    for f in job["files"]:
        check(set(f) == RESULT_KEYS, f"{f.get('file')}: pola wyniku {sorted(f)}")
        check(f["status"] == "done", f"{f['file']}: {f['error']}")
        cls_keys = {"doc_type", "confidence", "method", "evidence"}
        check(set(f["classification"]) == cls_keys, "pola classification")
        check(all(set(t) == TRACE_KEYS for t in f["trace"]), f"{f['file']}: pola trace")
        types.add(f["classification"]["doc_type"])
        status, headers, body = http(f"{base}/api/jobs/{job_id}/files/{f['name']}/json")
        check(status == 200 and "attachment" in headers.get("content-disposition", ""), "pobranie JSON")
        check(json.loads(body) == f["data"], f"{f['file']}: JSON różni się od wyniku")
        status, _, body = http(f"{base}/api/jobs/{job_id}/files/{f['name']}/pdf")
        check(status == 200 and body == (P01 / f["file"]).read_bytes(), f"{f['file']}: pobrany PDF różni się")
    check(types == EXPECTED_TYPES, f"rozpoznane typy: {types}")

    status, _, body = http(f"{base}/api/jobs/{job_id}/zip")
    check(status == 200, f"ZIP: {status}")
    names = sorted(zipfile.ZipFile(io.BytesIO(body)).namelist())
    check(names == ["odwolanie.json", "pelnomocnictwo.json", "potwierdzenie_przelewu.json"], f"ZIP: {names}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8799)
    a = ap.parse_args(argv)
    base = f"http://127.0.0.1:{a.port}"
    with tempfile.TemporaryDirectory() as jobs:
        env = {**os.environ, "ODW2JSON_JOBS_DIR": jobs, "LLM_MODE": os.environ.get("LLM_MODE", "replay")}
        proc = subprocess.Popen(
            [sys.executable, "-m", "odw2json", "serve", "--port", str(a.port)],
            cwd=REPO,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_server(base, proc)
            smoke(base)
        except (SmokeError, OSError, ValueError, KeyError) as e:
            print(f"SMOKE GUI FAIL: {e}", file=sys.stderr)
            return 1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("SMOKE GUI OK: 3 PDF -> done, kontrakt, JSON/PDF/ZIP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
