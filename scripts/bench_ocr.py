"""Benchmark OCR na skanach (E2b-T3): czas na strone/dokument i pokrycie wartosci GT.

Kazdy wariant to (DPI, parametry RapidOCR, rownoleglosc). Strony sa renderowane i rozpoznawane bez
cache (pomiar zimny). Rownoleglosc dotyczy stron jednego dokumentu (tak dziala pipeline); czas
dokumentu to czas scienny od wyslania stron do pul do ostatniego wyniku.

Uzycie:
    python scripts/bench_ocr.py --list
    python scripts/bench_ocr.py --skany data/train/skany --variants dpi200_seq dpi150_seq
    python scripts/bench_ocr.py --variants all --limit-docs 5      # szybki przebieg probny
Wyniki: bench_out/ocr/<wariant>.json oraz bench_out/ocr/summary.md (gitignored).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TYPE_BY_DIR = {"odwolania": "odwolanie", "pelnomocnictwa": "pelnomocnictwo", "potwierdzenia": "przelew"}
DEFAULT_SKANY = ROOT / "data" / "train" / "skany"
DEFAULT_OUT = ROOT / "bench_out" / "ocr"


@dataclass(frozen=True)
class Variant:
    name: str
    dpi: int = 200
    params: dict = field(default_factory=dict)  # klucze RapidOCR(params=...), np. "Global.use_cls"
    workers: int = 1
    mode: str = "seq"  # seq | thread | process


def _v(name, dpi=200, workers=1, mode="seq", **params) -> Variant:
    return Variant(name, dpi, {k.replace("__", "."): v for k, v in params.items()}, workers, mode)


VARIANTS: list[Variant] = [
    _v("dpi200_seq"),  # stan wyjsciowy E2
    _v("dpi150_seq", dpi=150),
    _v("dpi300_seq", dpi=300),
    _v("dpi200_nocls", Global__use_cls=False),
    _v("dpi150_nocls", dpi=150, Global__use_cls=False),
    _v("dpi200_nocls_max1600", Global__use_cls=False, Global__max_side_len=1600),
    _v("dpi200_nocls_max1200", Global__use_cls=False, Global__max_side_len=1200),
    _v("dpi300_nocls_max2800", dpi=300, Global__use_cls=False, Global__max_side_len=2800),
    _v("dpi200_nocls_t4", Global__use_cls=False, EngineConfig__onnxruntime__intra_op_num_threads=4),
    _v("dpi200_nocls_t8", Global__use_cls=False, EngineConfig__onnxruntime__intra_op_num_threads=8),
    _v("dpi200_nocls_t16", Global__use_cls=False, EngineConfig__onnxruntime__intra_op_num_threads=16),
    _v(
        "dpi200_nocls_thr2x8",
        workers=2,
        mode="thread",
        Global__use_cls=False,
        EngineConfig__onnxruntime__intra_op_num_threads=8,
    ),
    _v(
        "dpi200_nocls_thr4x4",
        workers=4,
        mode="thread",
        Global__use_cls=False,
        EngineConfig__onnxruntime__intra_op_num_threads=4,
    ),
    _v(
        "dpi200_nocls_proc2x8",
        workers=2,
        mode="process",
        Global__use_cls=False,
        EngineConfig__onnxruntime__intra_op_num_threads=8,
    ),
    _v(
        "dpi200_nocls_proc4x4",
        workers=4,
        mode="process",
        Global__use_cls=False,
        EngineConfig__onnxruntime__intra_op_num_threads=4,
    ),
    _v(
        "dpi200_nocls_proc8x2",
        workers=8,
        mode="process",
        Global__use_cls=False,
        EngineConfig__onnxruntime__intra_op_num_threads=2,
    ),
    _v("dpi200_cls_proc4x4", workers=4, mode="process", EngineConfig__onnxruntime__intra_op_num_threads=4),
]
_T = "EngineConfig__onnxruntime__intra_op_num_threads"
VARIANTS += [
    _v("dpi200_nocls_rb1_t4", Global__use_cls=False, Rec__rec_batch_num=1, **{_T: 4}),
    _v("dpi150_nocls_rb1_t4", dpi=150, Global__use_cls=False, Rec__rec_batch_num=1, **{_T: 4}),
    _v("dpi150_nocls_rb1_t8", dpi=150, Global__use_cls=False, Rec__rec_batch_num=1, **{_T: 8}),
    _v(
        "dpi150_nocls_rb1_proc4x2",
        dpi=150,
        workers=4,
        mode="process",
        Global__use_cls=False,
        Rec__rec_batch_num=1,
        **{_T: 2},
    ),
    _v(
        "dpi150_nocls_rb1_proc2x4",
        dpi=150,
        workers=2,
        mode="process",
        Global__use_cls=False,
        Rec__rec_batch_num=1,
        **{_T: 4},
    ),
    _v(
        "dpi150_nocls_rb1_thr4x2",
        dpi=150,
        workers=4,
        mode="thread",
        Global__use_cls=False,
        Rec__rec_batch_num=1,
        **{_T: 2},
    ),
    _v(
        "dpi300_nocls_rb1_t4_max2800",
        dpi=300,
        Global__use_cls=False,
        Global__max_side_len=2800,
        Rec__rec_batch_num=1,
        **{_T: 4},
    ),
]
BY_NAME = {v.name: v for v in VARIANTS}


# --- praca na stronie (importowalna przez procesy potomne) --------------------------------------

_LOCAL = threading.local()


def _engine(params: dict):
    from rapidocr import RapidOCR

    return RapidOCR(params=params or None)


def _init_proc(params: dict) -> None:
    global _PROC_ENGINE
    _PROC_ENGINE = _engine(params)


_PROC_ENGINE = None


def _run_page(engine, pdf: str, idx: int, dpi: int) -> tuple[str, float]:
    import numpy as np

    from odw2json.ingest import ocr

    t0 = time.perf_counter()
    img = ocr.render_page(Path(pdf), idx, dpi)
    res = engine(np.asarray(img.convert("RGB")))
    boxes, texts = getattr(res, "boxes", None), getattr(res, "txts", None)
    text = "" if boxes is None or texts is None else ocr._group_lines(boxes, texts)
    return text, time.perf_counter() - t0


def _task_proc(pdf: str, idx: int, dpi: int) -> tuple[str, float]:
    return _run_page(_PROC_ENGINE, pdf, idx, dpi)


def _task_thread(params: dict, pdf: str, idx: int, dpi: int) -> tuple[str, float]:
    eng = getattr(_LOCAL, "engine", None)
    if eng is None:
        eng = _LOCAL.engine = _engine(params)
    return _run_page(eng, pdf, idx, dpi)


# --- dane ---------------------------------------------------------------------------------------


def discover(skany: Path) -> list[dict]:
    import pypdfium2 as pdfium

    docs = []
    for pdf in sorted(skany.glob("*/*/*.pdf")):
        gt_path = pdf.with_suffix(".json")
        typ = TYPE_BY_DIR.get(pdf.parent.parent.name)
        if typ is None or not gt_path.exists():
            continue
        d = pdfium.PdfDocument(str(pdf))
        n = len(d)
        d.close()
        docs.append(
            {
                "id": f"{pdf.parent.parent.name}/{pdf.stem}",
                "pdf": str(pdf),
                "typ": typ,
                "gt": json.loads(gt_path.read_text(encoding="utf-8-sig")),
                "pages": n,
            }
        )
    return docs


def _clean_steps() -> list[str]:
    from odw2json.config_loader import load_app_config
    from odw2json.ingest import clean

    steps = (load_app_config().get("ingest", {}) or {}).get("clean") or clean.DEFAULT_ORDER
    return [s for s in steps if s in clean.CLEAN_STEPS]


# --- uruchomienie wariantu ----------------------------------------------------------------------


def run_variant(var: Variant, docs: list[dict]) -> dict:
    from eval.ingest_coverage import Coverage, coverage_for_doc
    from odw2json.ingest import PAGE_SEPARATOR, clean

    steps = _clean_steps()
    t_start = time.perf_counter()
    pool = None
    engine = None
    if var.mode == "process":
        pool = ProcessPoolExecutor(max_workers=var.workers, initializer=_init_proc, initargs=(var.params,))
    elif var.mode == "thread":
        pool = ThreadPoolExecutor(max_workers=var.workers)
    else:
        engine = _engine(var.params)
    # rozgrzewka: modele ladowane przed pomiarem (osobno raportowany koszt startu)
    first = docs[0]
    if pool is None:
        _run_page(engine, first["pdf"], 0, var.dpi)
    else:
        warm = [
            pool.submit(_task_proc, first["pdf"], 0, var.dpi)
            if var.mode == "process"
            else pool.submit(_task_thread, var.params, first["pdf"], 0, var.dpi)
            for _ in range(var.workers * 2)
        ]
        for f in warm:
            f.result()
    startup = time.perf_counter() - t_start

    per_doc, page_times = [], []
    total = Coverage()
    by_type: dict[str, Coverage] = {}
    t_run = time.perf_counter()
    for d in docs:
        t0 = time.perf_counter()
        if pool is None:
            res = [_run_page(engine, d["pdf"], i, var.dpi) for i in range(d["pages"])]
        else:
            fn = (
                (lambda i, d=d: pool.submit(_task_proc, d["pdf"], i, var.dpi))
                if var.mode == "process"
                else (lambda i, d=d: pool.submit(_task_thread, var.params, d["pdf"], i, var.dpi))
            )
            res = [f.result() for f in [fn(i) for i in range(d["pages"])]]
        wall = time.perf_counter() - t0
        pages = [t for t, _ in res]
        page_times += [s for _, s in res]
        text = clean.clean_text("\f".join(pages), steps).replace("\f", PAGE_SEPARATOR)
        cov = coverage_for_doc(text, d["gt"], d["typ"])
        cov.missing = [(f"{d['id']}: {p}", v) for p, v in cov.missing]
        total = total + cov
        by_type[d["typ"]] = by_type.get(d["typ"], Coverage()) + cov
        per_doc.append(
            {
                "id": d["id"],
                "pages": d["pages"],
                "wall_s": round(wall, 3),
                "found": cov.found,
                "fuzzy": cov.found_fuzzy,
                "total": cov.total,
                "missing": [list(m) for m in cov.missing],
                "text": text,
            }
        )
    run_wall = time.perf_counter() - t_run
    if pool is not None:
        pool.shutdown()
    n_pages = sum(d["pages"] for d in docs)
    ps = sorted(page_times)
    doc_walls = [x["wall_s"] for x in per_doc]
    return {
        "variant": var.name,
        "dpi": var.dpi,
        "params": var.params,
        "workers": var.workers,
        "mode": var.mode,
        "pages": n_pages,
        "docs": len(docs),
        "startup_s": round(startup, 2),
        "total_s": round(run_wall, 2),
        "s_per_page_throughput": round(run_wall / n_pages, 3),
        "page_latency_mean_s": round(statistics.fmean(page_times), 3),
        "page_latency_p95_s": round(ps[min(len(ps) - 1, int(0.95 * len(ps)))], 3),
        "doc_wall_mean_s": round(statistics.fmean(doc_walls), 3),
        "doc_wall_p95_s": round(sorted(doc_walls)[min(len(doc_walls) - 1, int(0.95 * len(doc_walls)))], 3),
        "coverage": {
            "global": total.to_dict(),
            "by_type": {k: v.to_dict() for k, v in sorted(by_type.items())},
            "by_field": {k: v.to_dict() for k, v in sorted(total.by_field.items())},
        },
        "missing": [list(m) for m in total.missing],
        "per_doc": per_doc,
    }


def write_summary(out: Path) -> None:
    rows = []
    for f in sorted(out.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        g = r["coverage"]["global"]
        bt = r["coverage"]["by_type"]
        rows.append(
            f"| {r['variant']} | {r['dpi']} | {r['mode']}x{r['workers']} | {r['startup_s']} | "
            f"{r['s_per_page_throughput']} | {r['page_latency_mean_s']} | {r['page_latency_p95_s']} | "
            f"{r['total_s']} | {g['found']}/{g['total']} | {g['found_fuzzy']} | "
            + " | ".join(f"{bt[t]['found']}+{bt[t]['found_fuzzy']}/{bt[t]['total']}" for t in sorted(bt))
            + " |"
        )
    head = (
        "| wariant | dpi | rownoleglosc | start s | s/str (przepustowosc) | latencja sr. | latencja p95 | "
        "razem s | exact | fuzzy | "
        + " | ".join(sorted(TYPE_BY_DIR.values()))
        + " |\n|"
        + "---|" * (10 + len(TYPE_BY_DIR))
        + "\n"
    )
    (out / "summary.md").write_text(head + "\n".join(rows) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--skany",
        type=Path,
        default=DEFAULT_SKANY,
        help="katalog skanow (odwolania/pelnomocnictwa/potwierdzenia)",
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--variants", nargs="+", default=["dpi200_seq"], help="nazwy wariantow lub 'all'")
    ap.add_argument("--limit-docs", type=int, default=None, help="tylko pierwsze N dokumentow (proba)")
    ap.add_argument(
        "--stride", type=int, default=1, help="co N-ty dokument (rowny przekroj typow, szybsza siatka)"
    )
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    if a.list:
        for v in VARIANTS:
            print(f"{v.name:28} dpi={v.dpi} {v.mode}x{v.workers} {v.params}")
        return 0
    names = [v.name for v in VARIANTS] if a.variants == ["all"] else a.variants
    unknown = [n for n in names if n not in BY_NAME]
    if unknown:
        print(f"Nieznane warianty: {unknown}", file=sys.stderr)
        return 2
    docs = discover(a.skany)
    docs = docs[:: max(1, a.stride)]
    if a.limit_docs:
        docs = docs[: a.limit_docs]
    if not docs:
        print(f"Brak skanow w {a.skany}", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(docs)} dokumentow, {sum(d['pages'] for d in docs)} stron")
    for n in names:
        try:
            r = run_variant(BY_NAME[n], docs)
        except Exception as e:  # noqa: BLE001 - np. brak pamieci przy wielu procesach: jedziemy dalej
            print(f"{n:28} BLAD {type(e).__name__}: {str(e)[:200]}", flush=True)
            continue
        (a.out / f"{n}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        g = r["coverage"]["global"]
        print(
            f"{n:28} {r['s_per_page_throughput']:6.2f} s/str (lat {r['page_latency_mean_s']:.2f}/"
            f"p95 {r['page_latency_p95_s']:.2f}) razem {r['total_s']:7.1f}s start {r['startup_s']:.1f}s "
            f"exact {g['found']}/{g['total']} fuzzy {g['found_fuzzy']}",
            flush=True,
        )
    write_summary(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
