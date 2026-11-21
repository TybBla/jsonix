"""Raport jakości do zgłoszenia: F1 wg reguł UZP (dev/holdout, tekst/skan) per typ i pole + czas na dokument.

Użycie:
    python scripts/quality_report.py                         # dev+holdout, tekst+skan -> docs/
    python scripts/quality_report.py --source tekst          # bez skanów (szybko, bez OCR)
    python scripts/quality_report.py --out output/raport.md  # inny plik wynikowy

Liczy to samo co bramka (`eval.gate.run_gate`, F1 z `eval/score.py`), ale nie porównuje z baseline
i niczego nie zapisuje w `eval/` — tylko raport Markdown (+ surowe metryki obok, `.json`).
Czas to czas ścienny przebiegu potoku na tej maszynie podzielony przez liczbę dokumentów; skany
liczą się z OCR (zimny albo ciepły cache OCR — raport podaje, który). Holdout traktuj jako wynik
końcowy: nie stroimy pod niego reguł.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LOW_FIELD_F1 = 0.85  # próg z roadmapy (E7): pola poniżej wymagają opisu przyczyny
SPLITS = ("dev", "holdout")
SOURCES = ("tekst", "skan")


@dataclass
class Run:
    split: str
    source: str
    metrics: dict
    docs: int
    seconds: float
    exit_code: int
    score: dict = field(default_factory=dict)

    @property
    def per_doc(self) -> float | None:
        return self.seconds / self.docs if self.docs else None


def _docs(score: dict) -> int:
    return len(score.get("docs", [])) + (score.get("negatives", {}).get("total") or 0)


def run_section(split: str, source: str, gate_dir: Path) -> Run:
    from eval.gate import run_gate

    t0 = time.perf_counter()
    res = run_gate(split, source=source, gate_dir=gate_dir)
    seconds = time.perf_counter() - t0
    score = (res.details or {}).get("score", {}) if hasattr(res, "details") else {}
    return Run(split, source, res.metrics, _docs(score), seconds, res.exit_code, score)


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def _sec(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f} s"


def ocr_cache_state() -> str:
    from odw2json.config_loader import ROOT_DIR, load_app_config

    cache = (load_app_config().get("ingest") or {}).get("ocr", {}).get("cache_dir")
    if not cache:
        return "brak cache OCR"
    path = Path(cache) if Path(cache).is_absolute() else ROOT_DIR / cache
    n = sum(1 for p in path.rglob("*") if p.is_file()) if path.is_dir() else 0
    return f"ciepły ({n} plików w `{cache}`)" if n else f"zimny (pusty `{cache}`)"


def environment() -> dict[str, str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        commit = ""
    return {
        "data": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": commit or "?",
        "python": platform.python_version(),
        "system": f"{platform.system()} {platform.release()}",
        "procesor": platform.processor() or platform.machine(),
        "rdzenie": str(os.cpu_count() or "?"),
    }


def render(runs: list[Run], env: dict[str, str], cache: str) -> str:
    out = ["# Raport jakości jsonix", ""]
    out.append(
        "F1 liczone wg reguł UZP (`eval/score.py`: długie teksty z progiem podobieństwa 80%, reszta "
        "dokładnie, "
        "listy po treści) na danych treningowych z podziałem `data/splits.yaml`. Holdout nie był używany do "
        "strojenia reguł. Wygenerowano: `python scripts/quality_report.py`."
    )
    out += ["", "## Środowisko", ""]
    out += [f"- {k}: {v}" for k, v in env.items()]
    out += [f"- cache OCR na starcie: {cache}", ""]

    out += ["## Podsumowanie", ""]
    out.append(
        "| Zbiór | Źródło | F1 | Precyzja | Pełność | Dokumenty | Negatywy | Błędy klasyfikacji "
        "| Czas / dokument |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        m = r.metrics
        neg = f"{m.get('neg_correct', 0)}/{m.get('neg_total', 0)}"
        out.append(
            f"| {r.split} | {r.source} | **{_pct(m.get('f1'))}** | {_pct(m.get('precision'))} | "
            f"{_pct(m.get('recall'))} | {r.docs} | {neg} | {m.get('classification_errors', 0)} "
            f"| {_sec(r.per_doc)} |"
        )

    types = sorted({t for r in runs for t in (r.metrics.get("f1_by_type") or {})})
    if types:
        out += ["", "## F1 per typ dokumentu", ""]
        out.append("| Typ | " + " | ".join(f"{r.split} {r.source}" for r in runs) + " |")
        out.append("|---" * (len(runs) + 1) + "|")
        for t in types:
            cells = [_pct((r.metrics.get("f1_by_type") or {}).get(t)) for r in runs]
            out.append(f"| {t} | " + " | ".join(cells) + " |")

    fields = sorted({f for r in runs for f in (r.metrics.get("f1_by_field") or {})})
    if fields:
        out += ["", "## F1 per pole", ""]
        out.append(
            f"Pola z F1 < {LOW_FIELD_F1:.2f} w którymkolwiek zbiorze są pogrubione "
            "— wymagają opisu przyczyny."
        )
        out.append("")
        out.append("| Pole | " + " | ".join(f"{r.split} {r.source}" for r in runs) + " |")
        out.append("|---" * (len(runs) + 1) + "|")
        for f in fields:
            vals = [(r.metrics.get("f1_by_field") or {}).get(f) for r in runs]
            low = any(v is not None and v < LOW_FIELD_F1 for v in vals)
            name = f"**{f}**" if low else f
            out.append(f"| {name} | " + " | ".join(_pct(v) for v in vals) + " |")

    bad = [(r, e) for r in runs for e in (r.metrics.get("classification_error_files") or [])]
    if bad:
        out += ["", "## Błędy klasyfikacji", ""]
        out += [f"- {r.split} {r.source}: `{e}`" for r, e in bad]

    out += [
        "",
        "## Jak czytać czas",
        "",
        "Czas / dokument = czas ścienny przebiegu potoku (wczytanie, OCR, klasyfikacja, ekstrakcja, zapis) "
        "podzielony przez liczbę dokumentów w zbiorze, na maszynie z sekcji „Środowisko”. UZP ogranicza czas "
        "na rozwiązanie (kryteria, pkt 5a), więc najważniejszy jest czas skanów przy zimnym cache OCR.",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=[*SPLITS, "all"], default="all")
    ap.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    ap.add_argument("--out", default=str(REPO / "docs" / "raport-jakosci.md"))
    a = ap.parse_args(argv)
    os.environ.setdefault("LLM_MODE", "replay")
    splits = SPLITS if a.split == "all" else (a.split,)
    sources = SOURCES if a.source == "all" else (a.source,)
    cache = ocr_cache_state()
    runs = []
    with tempfile.TemporaryDirectory(prefix="jsonix-report-") as tmp:
        for split in splits:
            for source in sources:
                print(f"[raport] {split} / {source} ...", flush=True)
                runs.append(run_section(split, source, Path(tmp)))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(runs, environment(), cache), encoding="utf-8")
    raw = {
        f"{r.split}@{r.source}": {"metrics": r.metrics, "docs": r.docs, "seconds": r.seconds} for r in runs
    }
    out.with_suffix(".json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for r in runs:
        print(
            f"[raport] {r.split}/{r.source}: F1={_pct(r.metrics.get('f1'))}, "
            f"{r.docs} dok., {_sec(r.per_doc)}/dok."
        )
    print(f"[raport] zapisano {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
