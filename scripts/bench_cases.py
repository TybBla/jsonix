"""Czas przetwarzania na dokument i na sprawę (CPU), z podziałem na etapy, przy zimnym cache OCR.

UZP ogranicza czas na rozwiązanie (docs/kryteria-uzp.md, pkt 5a), więc mierzymy to, co zobaczy jury:
pierwsze uruchomienie na nowych dokumentach (pusty cache OCR), bez LLM.

Użycie:
    python scripts/bench_cases.py                       # wszystkie sprawy z data/train (dev + holdout)
    python scripts/bench_cases.py --split dev --limit 10
    python scripts/bench_cases.py --workers 1,2,4       # dodatkowo: czas całości przy N procesach równolegle
    python scripts/bench_cases.py --json output/bench.json

Etapy: `ingest` (tekst z PDF + OCR stron bez tekstu), `classify`, `extract` — przez publiczne API modułów,
jak `pipeline.process_file_ex`. Cache OCR jest przekierowany do pustego katalogu tymczasowego (zimny start).
Pomiar `--workers` uruchamia osobne procesy na dokumenty (bez zmian w potoku) i pokazuje, ile dałoby
równoległe przetwarzanie wsadu.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import platform
import statistics
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def case_dirs(split: str, limit: int | None) -> list[Path]:
    from odw2json.splits import load_splits

    splits = load_splits()
    names = splits["dev"] + splits["holdout"] if split == "all" else splits[split]
    dirs = [REPO / "data" / "train" / n for n in names]
    dirs = [d for d in dirs if d.is_dir()]
    return dirs[:limit] if limit else dirs


def _ingest_cfg(cache_dir: str) -> dict:
    from odw2json.config_loader import load_app_config

    cfg = dict(load_app_config().get("ingest") or {})
    cfg["ocr"] = {**(cfg.get("ocr") or {}), "cache_dir": cache_dir}
    return cfg


def time_document(pdf: str, cache_dir: str) -> dict:
    """Czas etapów dla jednego PDF-a (wołane także w osobnym procesie)."""
    from odw2json import classify, extract, ingest
    from odw2json.config_loader import load_registry

    registry = load_registry()
    cfg = _ingest_cfg(cache_dir)
    t0 = time.perf_counter()
    doc = ingest.load(Path(pdf), cfg=cfg)
    t1 = time.perf_counter()
    cls = classify.classify(doc, registry)
    t2 = time.perf_counter()
    if cls.doc_type:
        extract.extract(doc, registry[cls.doc_type])
    t3 = time.perf_counter()
    return {
        "pdf": Path(pdf).relative_to(REPO).as_posix(),
        "pages": len(doc.pages),
        "ocr": bool(doc.ocr_used),
        "doc_type": cls.doc_type,
        "ingest_s": t1 - t0,
        "classify_s": t2 - t1,
        "extract_s": t3 - t2,
        "total_s": t3 - t0,
    }


def _stats(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "p50": statistics.median(values),
        "p95": p95,
        "max": ordered[-1],
        "sum": sum(values),
    }


def summarize(docs: list[dict], cases: list[Path]) -> dict:
    per_case: dict[str, float] = {}
    for d in docs:
        case = d["pdf"].rsplit("/", 1)[0]
        per_case[case] = per_case.get(case, 0.0) + d["total_s"]
    return {
        "dokumenty": _stats([d["total_s"] for d in docs]),
        "dokumenty_tekst": _stats([d["total_s"] for d in docs if not d["ocr"]]),
        "dokumenty_ocr": _stats([d["total_s"] for d in docs if d["ocr"]]),
        "sprawy": _stats(list(per_case.values())),
        "etapy_suma_s": {k: sum(d[f"{k}_s"] for d in docs) for k in ("ingest", "classify", "extract")},
        "sprawy_n": len(cases),
    }


def parallel_wall(pdfs: list[str], workers: int) -> float:
    with tempfile.TemporaryDirectory(prefix="jsonix-bench-par-") as cache:
        t0 = time.perf_counter()
        # spawn: świeże procesy bez pamięci OCR z pomiaru sekwencyjnego (fork na Linuksie by ją dziedziczył)
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
            list(ex.map(time_document, pdfs, [cache] * len(pdfs)))
        return time.perf_counter() - t0


def _fmt(s: dict) -> str:
    if not s:
        return "—"
    return (
        f"n={s['n']}, średnio {s['mean']:.2f} s, mediana {s['p50']:.2f} s, "
        f"p95 {s['p95']:.2f} s, max {s['max']:.2f} s"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None, help="tylko pierwsze N spraw")
    ap.add_argument("--workers", default="", help="np. 1,2,4: czas całości przy N procesach")
    ap.add_argument("--json", default=None, help="zapisz wyniki do pliku JSON")
    a = ap.parse_args(argv)
    os.environ.setdefault("LLM_MODE", "replay")

    cases = case_dirs(a.split, a.limit)
    pdfs = [str(p) for c in cases for p in sorted(c.rglob("*.pdf"))]
    print(
        f"[bench] {len(cases)} spraw, {len(pdfs)} PDF, "
        f"Python {platform.python_version()}, CPU {os.cpu_count()}"
    )
    with tempfile.TemporaryDirectory(prefix="jsonix-bench-") as cache:
        t0 = time.perf_counter()
        docs = [time_document(p, cache) for p in pdfs]
        wall = time.perf_counter() - t0
    summary = summarize(docs, cases)
    summary["sekwencyjnie_s"] = wall

    print(f"[bench] dokument:       {_fmt(summary['dokumenty'])}")
    print(f"[bench]   z tekstem:    {_fmt(summary['dokumenty_tekst'])}")
    print(f"[bench]   skan (OCR):   {_fmt(summary['dokumenty_ocr'])}")
    print(f"[bench] sprawa:         {_fmt(summary['sprawy'])}")
    stages = summary["etapy_suma_s"]
    total = sum(stages.values()) or 1.0
    print("[bench] udział etapów:  " + ", ".join(f"{k} {v / total:.0%}" for k, v in stages.items()))
    print(f"[bench] całość sekwencyjnie: {wall:.1f} s")
    slowest = sorted(docs, key=lambda d: d["total_s"], reverse=True)[:5]
    for d in slowest:
        print(
            f"[bench]   najwolniejszy: {d['pdf']} ({d['pages']} str., OCR={d['ocr']}): {d['total_s']:.2f} s"
        )

    par = {}
    for w in [int(x) for x in a.workers.split(",") if x.strip()]:
        par[w] = parallel_wall(pdfs, w)
        print(f"[bench] całość przy {w} procesach: {par[w]:.1f} s (x{wall / par[w]:.2f})")
    summary["rownolegle_s"] = par

    if a.json:
        out = Path(a.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = {"python": platform.python_version(), "cpu": os.cpu_count(), "summary": summary, "docs": docs}
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
