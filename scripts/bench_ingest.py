"""Benchmark backendow PDF (E2-T4): backend x czyszczenie na wszystkich PDF-ach treningowych.

Fallbacki wylaczone (wywolujemy backendy bezposrednio), wiec kazdy wynik nalezy tylko do danego backendu.
Miary (poza pokryciem T1, ktore jest nasycone i nie rankuje backendow):
  * placement   - czy wartosci GT leza na tej samej stronie co w bazie (pypdf bez czyszczenia),
  * damaged     - uszkodzone znaki w tekscie koncowym,
  * polish      - suma polskich liter i dokumenty tracace > 1% wzgledem najlepszego backendu,
  * order       - kolejnosc Odwolujacy/Zamawiajacy i tytul/Zarzut jak w bazie,
  * lines       - zachowanie wierszy etykieta+wartosc (KRS/NIP/REGON, Kwota przelewu),
  * time/errors - czas (mediana, p95, suma) i bledy,
  * classify    - pomylki klasyfikatora (pozytywy/negatywy).

Uzycie: python scripts/bench_ingest.py [--workers 1] [--use-cache] [--limit N] [--out bench_out/ingest]
Wyniki: <out>/report.json, <out>/report.md.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rapidfuzz import fuzz  # noqa: E402

from eval.ingest_coverage import (  # noqa: E402
    DIGIT_KEYS,
    LITERAL_KEYS,
    TRAIN_DIR,
    Coverage,
    _digits_pattern,
    _key_of,
    _leaves,
    coverage_for_doc,
    normalize,
)
from eval.score import GT_NAME_FOR_PDF  # noqa: E402
from odw2json.classify import classify  # noqa: E402
from odw2json.config_loader import load_registry  # noqa: E402
from odw2json.contracts import Document  # noqa: E402
from odw2json.ingest import _clean_pages, _join, backends, clean  # noqa: E402
from odw2json.textnorm import fold  # noqa: E402

BACKEND_NAMES = ["pypdf", "pdfplumber", "pypdfium2"]
CLEAN_MODES = {
    "none": [],
    "clean": list(clean.DEFAULT_ORDER),
    "clean-bez-dashes": [s for s in clean.DEFAULT_ORDER if s != "dashes"],
}
BASELINE = ("pypdf", "none")
POLISH = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
KNOWN_BAD = {"￾": "U+FFFE", "�": "U+FFFD", "￿": "U+FFFF"}
ZERO_WIDTH = set("­​‌‍⁠﻿")
LABEL_RE = re.compile(r"^\s*(KRS|NIP|REGON)\b.*\d{9,}|^\s*Kwota przelewu.*\d", re.M)
LABEL_ANY_RE = re.compile(r"\b(KRS|NIP|REGON)\b[^\n]*\d{9,}|Kwota przelewu[^\n]*\d")


# --------------------------------------------------------------------- zbior


def collect_docs(train_dir: Path) -> list[dict]:
    docs = []
    for pdf in sorted(train_dir.rglob("*.pdf")):
        case = pdf.parent.name
        gt_stem = GT_NAME_FOR_PDF.get(pdf.stem, pdf.stem)
        gt_path = pdf.parent / f"{gt_stem}.json"
        gt = json.loads(gt_path.read_text(encoding="utf-8-sig")) if gt_path.is_file() else None
        docs.append({"rel": f"{case}/{pdf.name}", "path": pdf, "gt": gt, "type": gt_stem if gt else None})
    return docs


def _extract_one(args: tuple[str, str]) -> tuple[str, str, list[str] | None, float, str | None]:
    backend, path = args
    t0 = time.perf_counter()
    try:
        pages = backends.BACKENDS[backend](Path(path))
        err = None
    except Exception as e:  # noqa: BLE001 - narzedzie pomiarowe
        pages, err = None, f"{type(e).__name__}: {e}"
    return backend, path, pages, time.perf_counter() - t0, err


def extract_all(docs: list[dict], workers: int) -> dict:
    jobs = [(b, str(d["path"])) for b in BACKEND_NAMES for d in docs]
    out: dict = {}
    if workers <= 1:
        results = map(_extract_one, jobs)
    else:
        results = ProcessPoolExecutor(max_workers=workers).map(_extract_one, jobs, chunksize=4)
    for n, (backend, path, pages, secs, err) in enumerate(results, 1):
        out[(backend, path)] = {"pages": pages, "secs": secs, "error": err}
        if n % 100 == 0:
            print(f"  ekstrakcja {n}/{len(jobs)}", file=sys.stderr, flush=True)
    return out


# --------------------------------------------------------------------- miary


def value_matchers(gt: dict) -> list[tuple[str, str, object]]:
    """(sciezka, rodzaj, wzorzec) dla wartosci GT liczonych jak w eval.ingest_coverage."""
    items = []
    for path, raw in _leaves(gt):
        key = _key_of(path)
        if raw is None or isinstance(raw, bool) or key not in LITERAL_KEYS | DIGIT_KEYS:
            continue
        value = str(raw)
        if key in DIGIT_KEYS:
            digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", value))
            if digits:
                items.append((path, "d", _digits_pattern(digits)))
        else:
            nv = normalize(value)
            if nv:
                items.append((path, "l", re.compile(r"(?<!\w)" + re.escape(nv) + r"(?!\w)")))
    return items


def hit_pages(pages: list[str], matchers: list) -> list[set[int]]:
    nfkc = [unicodedata.normalize("NFKC", p) for p in pages]
    norm = [normalize(p) for p in pages]
    res = []
    for _, kind, pat in matchers:
        src = nfkc if kind == "d" else norm
        res.append({i for i, t in enumerate(src) if pat.search(t)})
    return res


def damaged_counts(text: str) -> Counter:
    c: Counter = Counter()
    for ch in text:
        if ch in KNOWN_BAD:
            c[KNOWN_BAD[ch]] += 1
        elif ch in ZERO_WIDTH:
            c["zero_width_shy"] += 1
        elif unicodedata.category(ch) == "Cc" and ch not in "\n\f\t":
            c["control"] += 1
        elif "ﬀ" <= ch <= "ﬆ":
            c["ligature"] += 1
        elif unicodedata.category(ch) == "Zs" and ch != " ":
            c["nbsp_like"] += 1
    return c


def polish_count(text: str) -> int:
    return sum(1 for ch in text if ch in POLISH)


def order_signature(text: str, gt: dict | None) -> tuple:
    """(Odwolujacy przed Zamawiajacy, tytul przed Zarzut); None gdy brak jednego z elementow."""
    f = fold(normalize(text))
    o, z = f.find("odwolujacy"), f.find("zamawiajacy")
    a = None if o < 0 or z < 0 else o < z
    title = ((gt or {}).get("ZamowieniePubliczne") or {}).get("tytul")
    b = None
    if title:
        # pozycje w tekscie po fold (znaki zachowuja dlugosc), tytul szukany po zwinieciu bialych znakow
        compact = " ".join(f.split())
        t = compact.find(" ".join(fold(normalize(str(title))).split()))
        zz = compact.find("zarzut")
        b = None if t < 0 or zz < 0 else t < zz
    return (a, b)


def line_counts(text: str) -> dict:
    anchored = len(LABEL_RE.findall(text))
    containing = sum(1 for ln in text.split("\n") if LABEL_ANY_RE.search(ln))
    return {"anchored": anchored, "containing": containing}


def pct(vals: list[float], q: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))] if s else 0.0


# --------------------------------------------------------------------- glowna petla


def build_texts(docs: list[dict], raw: dict) -> dict:
    """texts[(backend, mode)][rel] = dict(pages, text, secs, error)."""
    texts: dict = {}
    for b in BACKEND_NAMES:
        for mode, steps in CLEAN_MODES.items():
            per = {}
            for d in docs:
                r = raw[(b, str(d["path"]))]
                pages, secs, err = r["pages"], r["secs"], r["error"]
                if pages is None:
                    per[d["rel"]] = {"pages": [], "text": "", "secs": secs, "error": err}
                    continue
                if steps and pages:
                    t0 = time.perf_counter()
                    pages = _clean_pages(pages, steps)
                    secs += time.perf_counter() - t0
                text, offs = _join(pages)
                per[d["rel"]] = {"pages": pages, "text": text, "secs": secs, "error": err, "offsets": offs}
            texts[(b, mode)] = per
    return texts


def run(docs: list[dict], texts: dict) -> dict:
    registry = load_registry()
    positives = [d for d in docs if d["gt"] is not None]
    matchers = {d["rel"]: value_matchers(d["gt"]) for d in positives}
    base = texts[BASELINE]
    base_hits = {d["rel"]: hit_pages(base[d["rel"]]["pages"], matchers[d["rel"]]) for d in positives}
    base_sig = {d["rel"]: order_signature(base[d["rel"]]["text"], d["gt"]) for d in docs}
    base_lines = {d["rel"]: line_counts(base[d["rel"]]["text"]) for d in docs}
    odw = [d for d in positives if d["type"] == "odwolanie"]
    # maks. liczba polskich liter na dokument w obrebie trybu czyszczenia
    pol = {k: {rel: polish_count(v["text"]) for rel, v in per.items()} for k, per in texts.items()}
    pol_max = {
        mode: {d["rel"]: max(pol[(b, mode)][d["rel"]] for b in BACKEND_NAMES) for d in docs}
        for mode in CLEAN_MODES
    }

    results: dict = {}
    examples: dict = {}
    for key, per in texts.items():
        backend, mode = key
        name = f"{backend}|{mode}"
        ex: dict = {"placement": [], "polish": [], "order": [], "lines": [], "similar": []}

        # pokrycie T1
        cov = None
        for d in positives:
            c = coverage_for_doc(per[d["rel"]]["text"], d["gt"], d["type"])
            cov = c if cov is None else cov + c
        cov = cov or Coverage()

        # scisle trafienia dosłowne: wartosc GT znak w znak (bez casefold, bez ujednolicania myslnikow)
        strict_n = strict_hit = 0
        for d in positives:
            t = " ".join(per[d["rel"]]["text"].split())
            for p_, v_ in _leaves(d["gt"]):
                if _key_of(p_) in LITERAL_KEYS and isinstance(v_, str) and v_.strip():
                    strict_n += 1
                    strict_hit += " ".join(v_.split()) in t

        # polozenie na stronach
        same = moved = lost = n_base = 0
        for d in positives:
            hits = hit_pages(per[d["rel"]]["pages"], matchers[d["rel"]])
            doc_moved = 0
            for bh, h in zip(base_hits[d["rel"]], hits, strict=True):
                if not bh:
                    continue
                n_base += 1
                bp = min(bh)
                if bp in h:
                    same += 1
                elif h:
                    moved += 1
                    doc_moved += 1
                else:
                    lost += 1
            if doc_moved:
                ex["placement"].append((doc_moved, d["rel"]))

        # uszkodzone znaki
        dmg: Counter = Counter()
        dmg_docs = 0
        for d in docs:
            c = damaged_counts(per[d["rel"]]["text"])
            dmg += c
            dmg_docs += bool(c)

        # polskie litery
        pol_total = sum(pol[key].values())
        flagged = []
        for d in docs:
            m, v = pol_max[mode][d["rel"]], pol[key][d["rel"]]
            if m and v < 0.99 * m:
                flagged.append((d["rel"], v, m))
        ex["polish"] = sorted(flagged, key=lambda x: x[1] - x[2])[:8]

        # kolejnosc czytania (odwolania)
        same_order = 0
        for d in odw:
            sig = order_signature(per[d["rel"]]["text"], d["gt"])
            if sig == base_sig[d["rel"]]:
                same_order += 1
            else:
                ex["order"].append((d["rel"], base_sig[d["rel"]], sig))
        # wspolna miara dla pelnego sygnalu: ile odwolan ma kolejnosc "poprawna" (True, True lub None)
        order_ok = sum(1 for d in odw if False not in order_signature(per[d["rel"]]["text"], d["gt"]))

        # wiersze etykieta/wartosc
        lc = [line_counts(per[d["rel"]]["text"]) for d in docs]
        for d, x in zip(docs, lc, strict=True):
            if x["anchored"] != base_lines[d["rel"]]["anchored"]:
                ex["lines"].append((d["rel"], x["anchored"], base_lines[d["rel"]]["anchored"]))
        anchored = sum(x["anchored"] for x in lc)
        containing = sum(x["containing"] for x in lc)
        base_anchored = sum(base_lines[d["rel"]]["anchored"] for d in docs)

        # podobienstwo tekstu do bazy (wykrywa zmiane kolejnosci blokow, np. wielokolumnowe TED)
        sims = []
        for d in docs:
            a_ = " ".join(base[d["rel"]]["text"].split())
            b_ = " ".join(per[d["rel"]]["text"].split())
            sim = fuzz.ratio(a_, b_) / 100 if (a_ or b_) else 1.0
            sims.append(sim)
            if sim < 0.97:
                ex["similar"].append((round(sim, 4), d["rel"]))

        # czas
        secs = [per[d["rel"]]["secs"] for d in docs]
        errors = [(d["rel"], per[d["rel"]]["error"]) for d in docs if per[d["rel"]]["error"]]
        empty = [d["rel"] for d in docs if not per[d["rel"]]["text"].strip()]

        # klasyfikacja
        fp = fn = 0
        wrong = []
        for d in docs:
            r = per[d["rel"]]
            doc = Document(path=d["path"], text=r["text"], pages=r["pages"])
            got = classify(doc, registry).doc_type
            if d["gt"] is None and got is not None:
                fp += 1
                wrong.append((d["rel"], "negatyw->" + got))
            elif d["gt"] is not None and got != d["type"]:
                fn += 1
                wrong.append((d["rel"], f"{d['type']}->{got}"))

        results[name] = {
            "backend": backend,
            "clean": mode,
            "coverage": cov.to_dict() | {"missing": len(cov.missing)},
            "literal_strict": {"hit": strict_hit, "total": strict_n},
            "placement": {
                "values_in_baseline": n_base,
                "same_page": same,
                "other_page": moved,
                "lost": lost,
                "same_page_rate": same / n_base if n_base else 0.0,
            },
            "damaged": {"total": sum(dmg.values()), "docs": dmg_docs, "by_kind": dict(dmg)},
            "polish": {"total": pol_total, "docs_losing_gt1pct": len(flagged)},
            "order": {
                "odwolania": len(odw),
                "same_as_baseline": same_order,
                "ratio_same": same_order / len(odw) if odw else 0.0,
                "correct_order_docs": order_ok,
            },
            "lines": {
                "anchored": anchored,
                "containing": containing,
                "share_anchored": anchored / containing if containing else 0.0,
                "vs_baseline": anchored / base_anchored if base_anchored else 0.0,
            },
            "similarity_to_baseline": {
                "median": statistics.median(sims),
                "min": min(sims),
                "docs_below_0.97": sum(1 for x in sims if x < 0.97),
            },
            "time": {
                "median_s": statistics.median(secs),
                "p95_s": pct(secs, 0.95),
                "total_s": sum(secs),
            },
            "errors": {"count": len(errors), "list": errors, "empty_text": len(empty), "empty_docs": empty},
            "classify": {
                "positives_misclassified": fn,
                "negatives_misclassified": fp,
                "wrong": wrong,
            },
        }
        examples[name] = {
            "placement_docs_with_moved_values": sorted(ex["placement"], reverse=True)[:8],
            "polish_loss": ex["polish"],
            "order_diffs": ex["order"][:8],
            "line_diffs": ex["lines"][:10],
            "least_similar_to_baseline": sorted(ex["similar"])[:10],
        }
    return {"docs": len(docs), "positives": len(positives), "results": results, "examples": examples}


# --------------------------------------------------------------------- raport


def markdown(rep: dict) -> str:
    rs = rep["results"]
    hdr = (
        "| backend | czyszczenie | pokr. exact | +fuzzy | braki | dosl. scisle | strona zgodna | uszk. znaki "
        "| polskie litery | dok. -1% PL | kolejnosc = baza | wiersze etykiet vs baza | med. s | p95 s "
        "| suma s | bledy | zle poz. | zle neg. | podob. min |\n"
        "|" + "---|" * 19
    )
    rows = [hdr]
    for r in rs.values():
        rows.append(
            "| {b} | {c} | {ce:.2%} | {cf:.2%} | {cm} | {ls} | {pl:.2%} | {dm} | {pt} | {pd} | {od:.1%} "
            "| {ln:.1%} "
            "| {tm:.3f} | {tp:.3f} | {tt:.1f} | {er} | {fn} | {fp} | {sm:.3f} |".format(
                sm=r["similarity_to_baseline"]["min"],
                b=r["backend"],
                c=r["clean"],
                ce=r["coverage"]["rate"],
                cf=r["coverage"]["rate_with_fuzzy"],
                cm=r["coverage"]["missing"],
                ls=r["literal_strict"]["hit"],
                pl=r["placement"]["same_page_rate"],
                dm=r["damaged"]["total"],
                pt=r["polish"]["total"],
                pd=r["polish"]["docs_losing_gt1pct"],
                od=r["order"]["ratio_same"],
                ln=r["lines"]["vs_baseline"],
                tm=r["time"]["median_s"],
                tp=r["time"]["p95_s"],
                tt=r["time"]["total_s"],
                er=r["errors"]["count"],
                fn=r["classify"]["positives_misclassified"],
                fp=r["classify"]["negatives_misclassified"],
            )
        )
    rows.append("")
    rows.append("Uszkodzone znaki wg rodzaju:")
    for name, r in rs.items():
        rows.append(f"- {name}: {r['damaged']['by_kind']} (dokumentow: {r['damaged']['docs']})")
    return "\n".join(rows)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark backendow PDF (E2-T4)")
    ap.add_argument("--out", type=Path, default=ROOT / "bench_out" / "ingest")
    ap.add_argument("--workers", type=int, default=1, help="1 = uczciwe pomiary czasu")
    ap.add_argument(
        "--use-cache", action="store_true", help="uzyj zapisanej ekstrakcji (bez czasow z nowego biegu)"
    )
    ap.add_argument("--limit", type=int, default=0, help="tylko N pierwszych PDF-ow (test skryptu)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    a.out.mkdir(parents=True, exist_ok=True)
    docs = collect_docs(TRAIN_DIR)
    if a.limit:
        docs = docs[:: max(1, len(docs) // a.limit)]
    cache = a.out / "raw_pages.pkl"
    if a.use_cache and cache.is_file():
        raw = pickle.loads(cache.read_bytes())
    else:
        print(f"Ekstrakcja: {len(docs)} PDF x {len(BACKEND_NAMES)} backendy", file=sys.stderr)
        raw = extract_all(docs, a.workers)
        cache.write_bytes(pickle.dumps(raw))
    rep = run(docs, build_texts(docs, raw))
    (a.out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    md = markdown(rep)
    (a.out / "report.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
