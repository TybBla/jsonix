"""Pomiar wariantu hybrydowego: same reguły vs reguły + LLM dla pól null (``llm_enabled``).

Dla każdej pary (split, źródło) uruchamia bramkę F1 (``eval.gate.run_gate``) dwa razy: bez LLM i z nakładką
``config/app.llm.yaml`` (``llm_enabled: true``). Przed pomiarem jest przebieg rozgrzewający (cache OCR
w pamięci procesu), więc czasy obu wariantów są porównywalne. Każde pole uzupełnione przez LLM
jest porównywane z GT: poprawne (FN -> TP), błędne (FN -> FP) albo zmyślone (TN -> FP, w GT jest null).

    python scripts/bench_hybryda.py                         # dev: tekst i skany (w próbie: na dev stroimy)
    python scripts/bench_hybryda.py --splits holdout        # ocena: TYLKO po zamrożeniu promptów
    python scripts/bench_hybryda.py --dry                   # bez sieci: LLM zwraca {} (zapytania, wycinki)

Konfiguracja LLM z .env (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY; opcjonalnie LLM_TEMPERATURE, LLM_EXTRA_BODY,
LLM_MIN_INTERVAL_S). Odpowiedzi trafiają do kaset w ``output/.cache/llm`` (``hybryda.cassette_dir``), więc
powtórny przebieg nie wysyła zapytań; wtedy czas LLM w raporcie jest oznaczony jako „z kaset”. Wynik:
``<out>/bench_hybryda.json`` i ``.md``. Kod wyjścia 1, gdy LLM zwracał błędy (pomiar niepełny).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OVERLAY = "config/app.llm.yaml"
VARIANTS = ("reguly", "hybryda")
COUNT_KEYS = ("tp", "tn", "fp", "fn")
LABEL = {"dev": "w próbie (strojenie)", "holdout": "ocena"}


class _DryClient:
    """Bez sieci: model „nic nie znalazł” - mierzy liczbę zapytań i rozmiar wycinków."""

    usage: dict = {}

    def complete_json(self, system: str, user: str) -> dict:
        return {}


def field_diff(base: dict, hyb: dict) -> list[dict]:
    """Pola, w których liczniki TP/TN/FP/FN różnią się między wariantami (z deltą)."""
    out = []
    for name in sorted(set(base) | set(hyb)):
        b = {k: base.get(name, {}).get(k, 0) for k in COUNT_KEYS}
        h = {k: hyb.get(name, {}).get(k, 0) for k in COUNT_KEYS}
        if b != h:
            out.append(
                {"pole": name, "reguly": b, "hybryda": h, "delta": {k: h[k] - b[k] for k in COUNT_KEYS}}
            )
    return out


def train_pdf(doc_path: Path, train_dir: Path) -> Path | None:
    """PDF w ``data/train`` dla pliku z katalogu roboczego bramki (``<tmp>/in/<ścieżka względna>``)."""
    parts = Path(doc_path).parts
    if "in" not in parts:
        return None
    i = len(parts) - 1 - parts[::-1].index("in")
    return train_dir.joinpath(*parts[i + 1 :])


def gt_leaf(gt: Any, path: str) -> tuple[bool, Any]:
    """Wartość liścia GT po ścieżce ``A[0].b``; (False, None), gdy ścieżki nie ma (np. krótsza lista)."""
    import re

    cur = gt
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            idx = int(part[1:-1])
            if not isinstance(cur, list) or idx >= len(cur):
                return False, None
            cur = cur[idx]
        else:
            if not isinstance(cur, dict) or part not in cur:
                return False, None
            cur = cur[part]
    return True, cur


def judge_fill(value: Any, gt_value: Any, path: str) -> str:
    """poprawne | bledne | zmyslone (GT null) - te same reguły równości co ``eval/score.py``."""
    from eval import score
    from odw2json.llm_fill import dsl_path

    cfg = score.ScoreConfig()
    p, g = score._norm(value), score._norm(gt_value)
    if g is None:
        return "zmyslone"
    return "poprawne" if score._values_equal(p, g, dsl_path(path) in cfg.fuzzy_paths, cfg) else "bledne"


def _fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:.4f}".replace(".", ",")


def to_markdown(rows: list[dict]) -> str:
    lines = [
        "| Zbiór | Wariant | F1 | Precyzja | Pełność | TP | TN | FP | FN | Dokumenty z zapytaniem"
        " | Pola pytane | Uzupełnione: poprawne / błędne / zmyślone | Odrzucone | Błędy LLM"
        " | Czas LLM [s] | Czas [s] |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        t, s, hyb = r["total"], r.get("llm") or {}, r["variant"] == "hybryda"
        j = r.get("fills_judged") or {}
        cached = s.get("usage_cached_calls", 0)
        llm_time = f"{s.get('llm_ms', 0) / 1000:.1f}" + (f" (z kaset: {cached})" if cached else "")
        dash = "—"
        lines.append(
            f"| {r['section']} ({LABEL.get(r['section'].split('@')[0], '')}) | {r['variant']} "
            f"| {_fmt(t.get('f1'))} | {_fmt(t.get('precision'))} | {_fmt(t.get('recall'))} "
            f"| {t['tp']} | {t['tn']} | {t['fp']} | {t['fn']} "
            f"| {s.get('docs_asked', 0) if hyb else dash} | {s.get('fields_asked', 0) if hyb else dash} "
            + (
                f"| {j.get('poprawne', 0)} / {j.get('bledne', 0)} / {j.get('zmyslone', 0)} "
                if hyb
                else f"| {dash} "
            )
            + f"| {s.get('rejected', 0) if hyb else dash} | {s.get('errors', 0) if hyb else dash} "
            f"| {llm_time if hyb else dash} | {r['seconds']:.1f} |"
        )
    return "\n".join(lines)


@contextmanager
def _variant(variant: str, dry: bool, fills: list):
    """Środowisko jednego przebiegu: nakładka LLM, rejestr uzupełnień, tryb --dry; potem przywrócenie."""
    from odw2json import llm_fill
    from odw2json.config_loader import load_llm_config

    prev_env = os.environ.get("JSONIX_APP_CONFIG")
    orig = llm_fill.from_app_config

    def patched(app_cfg: dict):
        if not app_cfg.get("llm_enabled"):
            return None
        filler = (
            llm_fill.LLMFiller(_DryClient(), load_llm_config().get("hybryda") or {}) if dry else orig(app_cfg)
        )
        filler.on_fill = lambda doc, path, value: fills.append((doc.path, path, value))
        return filler

    if variant == "hybryda":
        os.environ["JSONIX_APP_CONFIG"] = OVERLAY
    else:
        os.environ.pop("JSONIX_APP_CONFIG", None)
    llm_fill.from_app_config = patched
    llm_fill.STATS.clear()
    try:
        yield
    finally:
        llm_fill.from_app_config = orig
        if prev_env is None:
            os.environ.pop("JSONIX_APP_CONFIG", None)
        else:
            os.environ["JSONIX_APP_CONFIG"] = prev_env


def run_one(split: str, source: str, variant: str, out_dir: Path, dry: bool) -> dict:
    from eval.gate import TRAIN_DIR, run_gate
    from eval.score import gt_path_for_pdf
    from odw2json import llm_fill

    fills: list = []
    with _variant(variant, dry, fills):
        t0 = time.perf_counter()
        res = run_gate(split, source=source, gate_dir=out_dir / f"gate-{variant}")
        seconds = time.perf_counter() - t0
        stats = dict(llm_fill.STATS) if variant == "hybryda" else None
    judged, details = {"poprawne": 0, "bledne": 0, "zmyslone": 0}, []
    for doc_path, path, value in fills:
        pdf = train_pdf(doc_path, TRAIN_DIR)
        gt_file = gt_path_for_pdf(pdf) if pdf else None
        gt = json.loads(gt_file.read_text(encoding="utf-8")) if gt_file else None
        _, gt_value = gt_leaf(gt, path) if gt is not None else (False, None)
        verdict = judge_fill(value, gt_value, path)
        judged[verdict] += 1
        rel = str(pdf.relative_to(TRAIN_DIR)) if pdf else str(doc_path)
        details.append({"plik": rel, "pole": path, "llm": value, "gt": gt_value, "ocena": verdict})
    score = res.details["score"]
    return {
        "section": res.section,
        "variant": variant,
        "seconds": round(seconds, 1),
        "total": {k: score["total"][k] for k in (*COUNT_KEYS, "f1", "precision", "recall")},
        "fields": score["fields"],
        "llm": stats,
        "fills_judged": judged if variant == "hybryda" else None,
        "fills": details,
        "pipeline_errors": res.metrics.get("pipeline_errors"),
        "schema_errors": res.metrics.get("schema_errors"),
    }


def check_llm_config() -> str:
    """Fail-fast przed długim przebiegiem: opis konfiguracji albo wyjątek z brakującym ustawieniem."""
    from odw2json.llm import LLMClient

    c = LLMClient.from_config()
    base_url, key = c._conn[0], c._conn[1]
    if c.mode != "replay" and not (base_url and key and c.model):
        raise SystemExit(
            "Brak LLM_BASE_URL / LLM_MODEL / LLM_API_KEY w .env (albo użyj --dry lub LLM_MODE=replay)"
        )
    return (
        f"model={c.model} url={base_url} tryb={c.mode} temperatura={c.temperature} "
        f"extra_body={c.extra_body} odstęp={c.min_interval_s}s"
    )


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--splits", nargs="+", default=["dev"], choices=["dev", "holdout"])
    ap.add_argument("--sources", nargs="+", default=["tekst", "skan"], choices=["tekst", "skan"])
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "bench_hybryda")
    ap.add_argument("--dry", action="store_true", help="bez sieci: LLM zwraca {} (liczba zapytań, wycinki)")
    ap.add_argument("--no-warmup", action="store_true", help="bez przebiegu rozgrzewającego (cache OCR)")
    a = ap.parse_args(argv)
    llm_desc = "dry (bez sieci)" if a.dry else check_llm_config()
    print(f"LLM: {llm_desc}", flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for split in a.splits:
        for source in a.sources:
            if not a.no_warmup:
                print(f"== {split}@{source} rozgrzewka (bez pomiaru) ...", flush=True)
                run_one(split, source, "reguly", a.out / "rozgrzewka", True)
            for variant in a.variants:
                print(f"== {split}@{source} [{variant}] ...", flush=True)
                row = run_one(split, source, variant, a.out, a.dry)
                print(
                    f"   F1={row['total']['f1']:.4f} fp={row['total']['fp']} fn={row['total']['fn']} "
                    f"czas={row['seconds']}s llm={row['llm']} ocena={row['fills_judged']}",
                    flush=True,
                )
                rows.append(row)
    diffs = {}
    for r in rows:
        base = next((b for b in rows if b["section"] == r["section"] and b["variant"] == "reguly"), None)
        if r["variant"] == "hybryda" and base:
            diffs[r["section"]] = field_diff(base["fields"], r["fields"])
    errors = sum((r.get("llm") or {}).get("errors", 0) for r in rows)
    payload = {"llm": llm_desc, "dry": a.dry, "llm_errors": errors, "rows": rows, "field_diffs": diffs}
    (a.out / "bench_hybryda.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    md = f"LLM: {llm_desc}\n\n" + to_markdown(rows)
    if errors:
        md += f"\n\n**UWAGA: {errors} zapytań LLM z błędem - pomiar niepełny (zostały wyniki reguł).**"
    for section, d in diffs.items():
        md += f"\n\nZmiany per pole ({section}): " + (
            "brak"
            if not d
            else "; ".join(
                f"{x['pole']} " + ", ".join(f"{k} {v:+d}" for k, v in x["delta"].items() if v) for x in d
            )
        )
    for r in rows:
        for f in r.get("fills") or []:
            md += f"\n- {r['section']} {f['plik']} `{f['pole']}`: "
            md += f"LLM={f['llm']!r}, GT={f['gt']!r}: {f['ocena']}"
    (a.out / "bench_hybryda.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
