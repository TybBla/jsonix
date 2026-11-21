"""Bramka regresji F1: uruchamia pipeline na splicie, liczy metryki i porownuje z baseline.

Uzycie:
    python -m eval.gate [--split dev|holdout|all] [--update-baseline] [--tolerance 0.0] [--json PATH]

Kody wyjscia: 0 = ok, 1 = regresja albo awaria (blad schematu / wyjatek pipeline),
2 = blad uzycia albo brak sekcji w baseline (bez --update-baseline).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval.score import GT_NAME_FOR_PDF, Report, load_json, score_dirs
from odw2json import pipeline
from odw2json.config_loader import ROOT_DIR, DocTypeConfig, load_app_config, load_registry
from odw2json.logging_setup import new_run_id
from odw2json.schema import is_unknown_output, validate_output
from odw2json.splits import load_splits

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"
TRAIN_DIR = ROOT_DIR / "data" / "train"
GATE_DIR = ROOT_DIR / "output" / ".gate"
SPLITS = ("dev", "holdout")
EPS = 1e-9
_GLOBAL_ROWS = {
    "f1",
    "precision",
    "recall",
    "neg_rate",
    "schema_errors",
    "classification_errors",
    "pipeline_errors",
}
_MAX_DETAILS = 50


# ------------------------------------------------------------------ wyniki


@dataclass
class Row:
    """Jeden wiersz tabeli roznic."""

    name: str
    base: Any
    cur: Any
    delta: float | None
    arrow: str  # "↑" "↓" "=" (kierunek zmiany wartosci)
    flag: str  # "" | "REGRESSION" | "FAIL" | "new" | "gone" | "info"


@dataclass
class GateResult:
    split: str
    exit_code: int = 0
    metrics: dict = field(default_factory=dict)
    regressions: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    report: str = ""
    updated: bool = False
    baseline: dict | None = None
    details: dict = field(default_factory=dict)
    parts: list[GateResult] = field(default_factory=list)  # tylko dla split="all"

    def to_dict(self) -> dict:
        return {
            "split": self.split,
            "exit_code": self.exit_code,
            "metrics": self.metrics,
            "regressions": self.regressions,
            "baseline_updated": self.updated,
            "rows": [vars(r) for r in self.rows],
            **self.details,
        }


# ----------------------------------------------------------- baseline I/O


def load_baseline(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"baseline {path} nie jest poprawnym JSON: {e}") from e
    return data if isinstance(data, dict) else {}


def save_baseline(path: Path, sections: dict) -> None:
    ordered = {k: sections[k] for k in SPLITS if k in sections}
    ordered.update({k: sections[k] for k in sorted(sections) if k not in ordered})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _git_commit() -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and out else None


# ------------------------------------------------------------ przygotowanie


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _prepare(
    work: Path,
    train_dir: Path,
    cases: list[str],
    neg_dirs: list[str],
    negatives: list[str] | None,
) -> tuple[Path, Path]:
    """Buduje work/in (PDF-y) i work/gt (GT JSON + puste atrapy PDF, bo score_dirs iteruje po PDF)."""
    in_dir, gt_dir = work / "in", work / "gt"
    in_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)

    def add_pdf(pdf: Path) -> None:
        rel = pdf.relative_to(train_dir)
        _link_or_copy(pdf, in_dir / rel)
        placeholder = gt_dir / rel
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_bytes(b"")

    for case in cases:
        src = train_dir / case
        if not src.is_dir():
            raise ValueError(f"brak sprawy {case!r} w {train_dir}")
        for f in sorted(src.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() == ".pdf":
                add_pdf(f)
            elif f.suffix.lower() == ".json":
                target = gt_dir / f.relative_to(train_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)

    found: set[str] = set()
    for d in neg_dirs:
        for pdf in sorted((train_dir / d).glob("*.pdf")):
            if negatives is None or pdf.name in negatives:
                add_pdf(pdf)
                found.add(pdf.name)
    missing = sorted(set(negatives or []) - found)
    if missing:
        raise ValueError(f"brak negatywow: {missing}")
    return in_dir, gt_dir


# ------------------------------------------------------------------ metryki


def _inspect_outputs(
    out_dir: Path, gt_dir: Path, registry: dict[str, DocTypeConfig]
) -> tuple[int, int, list[str], list[str]]:
    """(bledy schematu, bledy klasyfikacji, szczegoly schematu, szczegoly klasyfikacji)."""
    schema_n = cls_n = 0
    schema_msgs: list[str] = []
    cls_msgs: list[str] = []
    for pdf in sorted(gt_dir.rglob("*.pdf")):
        rel_dir = pdf.parent.relative_to(gt_dir)
        rel = (rel_dir / pdf.name).as_posix()
        gt_stem = GT_NAME_FOR_PDF.get(pdf.stem, pdf.stem)
        positive = (gt_dir / rel_dir / f"{gt_stem}.json").is_file()
        data = load_json(out_dir / rel_dir / f"{pdf.stem}.json")  # None: brak/pusty/zepsuty plik
        if not positive:
            if data is not None and not is_unknown_output(data):
                cls_n += 1
                cls_msgs.append(f"{rel}: negatyw ma niepusty wynik")
            continue
        cfg = registry.get(gt_stem)
        if data is None or not isinstance(data, dict) or is_unknown_output(data):
            cls_n += 1
            cls_msgs.append(f"{rel}: oczekiwano {gt_stem}, wynik pusty/niepoprawny")
            continue
        if cfg is None:
            continue
        if not set(data) & set(cfg.template()):
            cls_n += 1
            cls_msgs.append(f"{rel}: oczekiwano {gt_stem}, klucze {sorted(data)} to inny typ")
            continue  # zly typ to blad klasyfikacji, nie schematu
        errs = validate_output(data, cfg)
        schema_n += len(errs)
        schema_msgs.extend(f"{rel}: {e}" for e in errs)
    return schema_n, cls_n, schema_msgs, cls_msgs


def build_metrics(rep: Report, schema_errors: int, classification_errors: int, pipeline_errors: int) -> dict:
    t = rep.total
    return {
        "f1": t.f1,
        "precision": t.precision,
        "recall": t.recall,
        "f1_by_type": {k: v.f1 for k, v in sorted(rep.by_type.items()) if k != "negative"},
        "f1_by_field": {k: v.f1 for k, v in sorted(rep.fields.items())},
        "neg_correct": rep.neg_correct,
        "neg_total": rep.neg_total,
        "schema_errors": schema_errors,
        "classification_errors": classification_errors,
        "pipeline_errors": pipeline_errors,
    }


# ----------------------------------------------------------------- porownanie


def _neg_rate(m: dict) -> float | None:
    total = m.get("neg_total") or 0
    return m.get("neg_correct", 0) / total if total else None


def _arrow(base: float | None, cur: float | None) -> str:
    if base is None or cur is None or abs(cur - base) <= EPS:
        return "="
    return "↑" if cur > base else "↓"


def compare_metrics(base: dict, cur: dict, tolerance: float) -> tuple[list[Row], list[str]]:
    """Tabela roznic baseline -> biezace oraz lista powodow kodu wyjscia 1.

    Wyzsze=lepsze (f1, odsetek poprawnych negatywow): spadek wiekszy niz tolerancja (+1e-9) to regresja.
    schema_errors i pipeline_errors > 0 to awaria niezaleznie od baseline; classification_errors powyzej
    baseline to regresja. Pola/typy nieobecne w baseline to "new" (bez bledu).
    """
    rows: list[Row] = []
    reg: list[str] = []

    def higher(name: str, b: float | None, c: float | None, gated: bool = True) -> None:
        if c is None:
            rows.append(Row(name, b, None, None, "=", "gone"))
            return
        if b is None:
            rows.append(Row(name, None, c, None, "=", "new"))
            return
        d = c - b
        flag = "" if gated else "info"
        if gated and c < b - tolerance - EPS:
            flag = "REGRESSION"
            reg.append(f"{name}: {b:.4f} -> {c:.4f} (spadek {-d:.4f} > tolerancja {tolerance})")
        rows.append(Row(name, b, c, d, _arrow(b, c), flag))

    higher("f1", base.get("f1"), cur.get("f1"))
    higher("precision", base.get("precision"), cur.get("precision"), gated=False)
    higher("recall", base.get("recall"), cur.get("recall"), gated=False)
    br, cr = _neg_rate(base), _neg_rate(cur)
    if br is not None or cr is not None:
        higher("neg_rate", br, cr)
    for group in ("f1_by_type", "f1_by_field"):
        b_map, c_map = base.get(group) or {}, cur.get(group) or {}
        for k in sorted(set(b_map) | set(c_map)):
            higher(f"{group}[{k}]", b_map.get(k), c_map.get(k))

    for key in ("schema_errors", "pipeline_errors", "classification_errors"):
        b, c = base.get(key, 0), cur.get(key, 0)
        flag = ""
        if key == "classification_errors":
            if c > b:
                flag = "REGRESSION"
                reg.append(f"{key}: {b} -> {c}")
        elif c > 0:
            flag = "FAIL"
            reg.append(f"{key}: {c} (musi byc 0)")
        rows.append(Row(key, b, c, c - b, _arrow(b, c), flag))
    return rows, reg


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def format_table(rows: list[Row], show_all: bool = False) -> str:
    """ASCII-owa tabela (strzalki Unicode tylko w kolumnie statusu)."""
    shown = [
        r
        for r in rows
        if show_all or r.name in _GLOBAL_ROWS or r.arrow != "=" or r.flag in ("new", "gone", "REGRESSION")
    ]
    hidden = len(rows) - len(shown)
    w = max([len("metric")] + [len(r.name) for r in shown])
    lines = [f"{'metric':<{w}}  {'baseline':>9}  {'current':>9}  {'delta':>8}  status"]
    for r in shown:
        if r.delta is None:
            delta = "-"
        elif isinstance(r.delta, int):
            delta = f"{r.delta:+d}"
        else:
            delta = f"{r.delta:+.4f}"
        status = " ".join(x for x in (r.arrow, r.flag) if x)
        lines.append(f"{r.name:<{w}}  {_fmt(r.base):>9}  {_fmt(r.cur):>9}  {delta:>8}  {status}")
    if hidden:
        lines.append(f"({hidden} wierszy bez zmian pominieto)")
    return "\n".join(lines)


# ---------------------------------------------------------------------- bramka


def run_gate(
    split: str,
    cases: list[str] | None = None,
    baseline_path: Path = BASELINE_PATH,
    update: bool = False,
    tolerance: float = 0.0,
    train_dir: Path = TRAIN_DIR,
    negatives: list[str] | None = None,
    gate_dir: Path | None = None,
) -> GateResult:
    """Uruchamia bramke dla splitu ('dev', 'holdout' albo 'all').

    cases: nadpisuje liste spraw splitu (szybkie testy); negatives: nazwy PDF-ow z katalogu negatywow
    (domyslnie wszystkie); gate_dir: gdzie zapisac wynik (domyslnie output/.gate).
    """
    if split == "all":
        if cases is not None:
            raise ValueError("--split all nie laczy sie z lista spraw")
        parts = [
            run_gate(s, None, baseline_path, update, tolerance, train_dir, negatives, gate_dir)
            for s in SPLITS
        ]
        codes = [p.exit_code for p in parts]
        return GateResult(
            split="all",
            exit_code=1 if 1 in codes else (2 if 2 in codes else 0),
            metrics={p.split: p.metrics for p in parts},
            regressions=[f"[{p.split}] {r}" for p in parts for r in p.regressions],
            report="\n\n".join(p.report for p in parts),
            updated=any(p.updated for p in parts),
            parts=parts,
        )
    if split not in SPLITS:
        raise ValueError(f"nieznany split {split!r} (dozwolone: dev, holdout, all)")

    splits = load_splits()
    case_list = list(cases) if cases is not None else splits[split]
    registry = load_registry()
    app_cfg = load_app_config()
    run_id = f"gate-{split}-{new_run_id()}"

    with tempfile.TemporaryDirectory(prefix=f"odw2json-gate-{split}-", ignore_cleanup_errors=True) as tmp:
        work = Path(tmp)
        in_dir, gt_dir = _prepare(work, Path(train_dir), case_list, splits["negatives"], negatives)
        out_dir = work / "out"
        run_report = pipeline.run(in_dir, out_dir, app_cfg=app_cfg, registry=registry, run_id=run_id)
        rep = score_dirs(out_dir, gt_dir)
        schema_n, cls_n, schema_msgs, cls_msgs = _inspect_outputs(out_dir, gt_dir, registry)

    pipe_errors = [{"file": str(e.path.name), "error": e.error} for e in run_report.errors]
    metrics = build_metrics(rep, schema_n, cls_n, len(pipe_errors))
    metrics["updated"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    metrics["commit"] = _git_commit()

    res = GateResult(split=split, metrics=metrics)
    res.details = {
        "cases": case_list,
        "run_id": run_id,
        "pipeline_error_details": pipe_errors,
        "schema_error_details": schema_msgs[:_MAX_DETAILS],
        "classification_error_details": cls_msgs[:_MAX_DETAILS],
        "score": rep.to_dict(),
    }

    sections = load_baseline(baseline_path)
    base = sections.get(split)
    res.baseline = base
    lines = [f"== gate[{split}] =="]
    broken = []
    if schema_n:
        broken.append(f"schema_errors: {schema_n} (musi byc 0)")
    if pipe_errors:
        broken.append(f"pipeline_errors: {len(pipe_errors)} (musi byc 0)")

    if update:
        if broken:
            res.exit_code = 1
            res.regressions = broken
            lines.append("Baseline NIE zaktualizowany - wynik ma bledy:")
            lines += [f"  {b}" for b in broken]
        else:
            if base:
                res.rows, _ = compare_metrics(base, metrics, tolerance)
                lines += ["Roznice wzgledem poprzedniego baseline:", format_table(res.rows)]
            else:
                lines.append("Nowa sekcja baseline (brak poprzedniej).")
            sections[split] = metrics
            save_baseline(baseline_path, sections)
            res.updated = True
            lines.append(f"Zapisano baseline[{split}] -> {baseline_path}")
    elif not base:
        res.exit_code = 2
        lines.append(f"Brak sekcji '{split}' w {baseline_path}. Uruchom z --update-baseline.")
    else:
        res.rows, res.regressions = compare_metrics(base, metrics, tolerance)
        res.exit_code = 1 if res.regressions else 0
        lines.append(format_table(res.rows))
        if res.regressions:
            lines += ["", "REGRESJE / AWARIE:"] + [f"  - {r}" for r in res.regressions]
        else:
            lines.append("OK: brak regresji.")
    lines.append(
        f"f1={metrics['f1']:.4f} neg={metrics['neg_correct']}/{metrics['neg_total']} "
        f"schema={schema_n} klasyfikacja={cls_n} pipeline={len(pipe_errors)} -> exit {res.exit_code}"
    )
    res.report = "\n".join(lines)

    out_gate = Path(gate_dir) if gate_dir is not None else GATE_DIR
    out_gate.mkdir(parents=True, exist_ok=True)
    (out_gate / f"{split}.json").write_text(
        json.dumps(res.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return res


# ------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Bramka regresji F1 (baseline per split)")
    ap.add_argument("--split", choices=[*SPLITS, "all"], default="dev")
    ap.add_argument(
        "--update-baseline", action="store_true", help="nadpisz sekcje baseline biezacym wynikiem"
    )
    ap.add_argument("--tolerance", type=float, default=0.0, help="dopuszczalny spadek metryk (domyslnie 0)")
    ap.add_argument("--json", type=Path, default=None, help="zapisz pelny wynik jako JSON")
    ap.add_argument("--baseline", type=Path, default=BASELINE_PATH, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        res = run_gate(a.split, baseline_path=a.baseline, update=a.update_baseline, tolerance=a.tolerance)
    except ValueError as e:
        print(f"blad: {e}", file=sys.stderr)
        return 2
    print(res.report)
    if a.json:
        parts = res.parts or [res]
        payload = {p.split: p.to_dict() for p in parts}
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
