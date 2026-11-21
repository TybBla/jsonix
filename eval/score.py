"""Narzedzie do liczenia F1 wg zasad organizatora (TP/TN/FP/FN na poziomie pol).

Uzycie: python -m eval.score --pred output --gt data/train
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

# pdf stem -> GT stem (domyslnie identycznosc); uzywane tylko, gdy obok X.pdf nie ma X.json
GT_NAME_FOR_PDF: dict = {"potwierdzenie_przelewu": "przelew"}

SOURCE_TEXT = "tekst"
SOURCE_SCAN = "skan"
MIN_TEXT_LAYER_CHARS = 30  # PDF z mniejsza liczba znakow w surowej ekstrakcji uznajemy za skan


@dataclass
class ScoreConfig:
    # Pola "dlugi string" (prog podobienstwa) wg UZP, Discord 2026-11-21 13:26.
    fuzzy_paths: frozenset = frozenset(
        {
            "Odwolujacy[].nazwa",
            "Zamawiajacy[].nazwa",
            "Odwolujacy[].pelnomocnik.nazwa",
            "ZamowieniePubliczne.tytul",
            "przelew_bankowy.tytul",
        }
    )
    # Klucze traktowane rozmyto tylko przy PAROWANIU elementow list (nie przy ocenie).
    fuzzy_keys: frozenset = frozenset({"nazwa", "tytul", "imie_nazwisko"})
    threshold: float = 0.8
    lenient_types: bool = False  # "123" == 123
    casefold_exact: bool = False  # pola dokladne: ignoruj wielkosc liter
    min_match_sim: float = 0.0  # min. podobienstwo elementow listy do sparowania
    gt_name_for_pdf: dict = field(default_factory=lambda: dict(GT_NAME_FOR_PDF))


@dataclass
class Counts:
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    fields: dict = field(default_factory=dict, compare=False, repr=False)

    def __add__(self, o: Counts) -> Counts:
        r = Counts(self.tp + o.tp, self.tn + o.tn, self.fp + o.fp, self.fn + o.fn)
        for src in (self.fields, o.fields):
            for k, v in src.items():
                cur = r.fields.get(k, Counts())
                r.fields[k] = Counts(cur.tp + v.tp, cur.tn + v.tn, cur.fp + v.fp, cur.fn + v.fn)
        return r

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        d = 2 * self.tp + self.fp + self.fn
        return 2 * self.tp / d if d else 0.0

    @property
    def accuracy(self) -> float:
        n = self.tp + self.tn + self.fp + self.fn
        return (self.tp + self.tn) / n if n else 0.0

    def to_dict(self) -> dict:
        return {
            "tp": self.tp,
            "tn": self.tn,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "accuracy": self.accuracy,
        }


def _norm(v: Any) -> Any:
    """Normalizuje wartosc liscia; None oznacza 'brak'."""
    if isinstance(v, str):
        v = " ".join(v.split())
        return v if v else None
    return v


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _lenient_str(v: Any) -> Any:
    if _is_num(v):
        return str(int(v)) if float(v).is_integer() else str(v)
    return v


def _values_equal(p: Any, g: Any, fuzzy: bool, cfg: ScoreConfig) -> bool:
    """p, g: znormalizowane, niepuste."""
    if cfg.lenient_types and (_is_num(p) != _is_num(g)):
        p, g = _lenient_str(p), _lenient_str(g)
    if _is_num(p) and _is_num(g):
        return math.isclose(float(p), float(g), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(p, bool) or isinstance(g, bool):
        return type(p) is type(g) and p == g
    if isinstance(p, str) and isinstance(g, str):
        if fuzzy:
            return fuzz.ratio(p.casefold(), g.casefold()) / 100.0 >= cfg.threshold
        return p.casefold() == g.casefold() if cfg.casefold_exact else p == g
    return p == g


def _leaf_counts(p: Any, g: Any, path: str, cfg: ScoreConfig) -> Counts:
    p, g = _norm(p), _norm(g)
    if p is None and g is None:
        return Counts(tn=1)
    if g is None:
        return Counts(fp=1)
    if p is None:
        return Counts(fn=1)
    return Counts(tp=1) if _values_equal(p, g, path in cfg.fuzzy_paths, cfg) else Counts(fp=1)


def _add(acc: Counts, path: str, c: Counts) -> None:
    acc.tp += c.tp
    acc.tn += c.tn
    acc.fp += c.fp
    acc.fn += c.fn
    f = acc.fields.setdefault(path, Counts())
    f.tp += c.tp
    f.tn += c.tn
    f.fp += c.fp
    f.fn += c.fn


def _empty_like(v: Any) -> Any:
    if isinstance(v, dict):
        return {}
    if isinstance(v, list):
        return []
    return None


def _flat(v: Any) -> Any:
    """Struktura w miejscu skalara (niezgodnosc ksztaltu) -> tekst do porownania."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return v


def _compare(p: Any, g: Any, path: str, cfg: ScoreConfig, acc: Counts) -> None:
    p_struct = isinstance(p, (dict, list))
    g_struct = isinstance(g, (dict, list))
    if isinstance(p, dict) or isinstance(g, dict):
        if (
            (p_struct and not isinstance(p, dict))
            or (g_struct and not isinstance(g, dict))
            or (p is not None and not p_struct)
            or (g is not None and not g_struct)
        ):
            _add(acc, path, _leaf_counts(_flat(p), _flat(g), path, cfg))
            return
        pd = p or {}
        gd = g or {}
        for k in list(gd) + [k for k in pd if k not in gd]:
            _compare(pd.get(k), gd.get(k), f"{path}.{k}" if path else k, cfg, acc)
        return
    if isinstance(p, list) or isinstance(g, list):
        if (p is not None and not isinstance(p, list)) or (g is not None and not isinstance(g, list)):
            _add(acc, path, _leaf_counts(_flat(p), _flat(g), path, cfg))
            return
        _compare_lists(p or [], g or [], path + "[]", cfg, acc)
        return
    if path == "" and p is None and g is None:
        return  # dwa brakujace dokumenty - nic do policzenia
    _add(acc, path, _leaf_counts(p, g, path, cfg))


def _leaves(v: Any, path: str = "") -> dict:
    out: dict = {}
    if isinstance(v, dict):
        for k, x in v.items():
            out.update(_leaves(x, f"{path}.{k}" if path else k))
    elif isinstance(v, list):
        for i, x in enumerate(v):
            out.update(_leaves(x, f"{path}[{i}]"))
    else:
        out[path] = v
    return out


def _elem_sim(a: Any, b: Any, cfg: ScoreConfig) -> float:
    """Srednie podobienstwo lisci (po polach niepustych w ktorymkolwiek elemencie)."""
    la = {k: _norm(v) for k, v in _leaves(a).items()}
    lb = {k: _norm(v) for k, v in _leaves(b).items()}
    keys = [k for k in dict.fromkeys(list(la) + list(lb)) if la.get(k) is not None or lb.get(k) is not None]
    if not keys:
        return 1.0
    total = 0.0
    for k in keys:
        x, y = la.get(k), lb.get(k)
        if x is None or y is None:
            continue
        key = k.rsplit(".", 1)[-1].split("[")[0]
        if key in cfg.fuzzy_keys and isinstance(x, str) and isinstance(y, str):
            total += fuzz.ratio(x.casefold(), y.casefold()) / 100.0
        elif _values_equal(x, y, False, cfg):
            total += 1.0
    return total / len(keys)


def _compare_lists(pl: list, gl: list, path: str, cfg: ScoreConfig, acc: Counts) -> None:
    pairs = sorted(
        ((_elem_sim(a, b, cfg), i, j) for i, a in enumerate(pl) for j, b in enumerate(gl)),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    used_p: set = set()
    used_g: set = set()
    matched = []
    for s, i, j in pairs:
        if s < cfg.min_match_sim or i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        matched.append((i, j))
    for i, j in matched:
        _compare(pl[i], gl[j], path, cfg, acc)
    for i, x in enumerate(pl):
        if i not in used_p:
            _compare(x, _empty_like(x), path, cfg, acc)  # nadmiarowy -> FP
    for j, y in enumerate(gl):
        if j not in used_g:
            _compare(_empty_like(y), y, path, cfg, acc)  # brakujacy -> FN/TN


_DEFAULT_CFG = ScoreConfig()


def score_pair(pred: dict | None, gt: dict | None, cfg: ScoreConfig = _DEFAULT_CFG) -> Counts:
    """Porownuje jeden dokument. None = brak pliku. Zwraca Counts z .fields (per pole)."""
    acc = Counts()
    p = pred if pred is not None else _empty_like(gt)
    g = gt if gt is not None else _empty_like(pred)
    _compare(p, g, "", cfg, acc)
    return acc


# ------------------------------------------- GT, typ dokumentu i zrodlo (E2b)


def gt_path_for_pdf(pdf: Path, cfg: ScoreConfig | None = None) -> Path | None:
    """Istniejacy plik GT dla `X.pdf`: `X.json` obok PDF-a, w przeciwnym razie `GT_NAME_FOR_PDF[X].json`.

    None = brak GT (dokument negatywny).
    """
    names = (cfg or _DEFAULT_CFG).gt_name_for_pdf
    pdf = Path(pdf)
    for stem in (pdf.stem, names.get(pdf.stem, pdf.stem)):
        cand = pdf.with_name(f"{stem}.json")
        if cand.is_file():
            return cand
    return None


def infer_doc_type(gt: Any, registry: dict) -> str | None:
    """Typ dokumentu, ktorego szablon ma najwiecej kluczy wspolnych z kluczami najwyzszego poziomu GT.

    None, gdy GT nie jest obiektem, nie ma wspolnych kluczy z zadnym szablonem albo wynik jest remisowy.
    """
    if not isinstance(gt, dict) or not gt:
        return None
    keys = set(gt)
    scores = {name: len(keys & set(cfg.template())) for name, cfg in registry.items()}
    best = max(scores.values(), default=0)
    winners = [name for name, n in scores.items() if n == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def has_text_layer(pdf: Path, min_chars: int = MIN_TEXT_LAYER_CHARS) -> bool:
    """Czy PDF ma warstwe tekstowa (surowa ekstrakcja, bez OCR): >= `min_chars` znakow na calosc.

    Nieczytelny plik uznajemy za tekstowy (nie jest skanem, tylko bledem do zglaszania gdzie indziej).
    """
    from odw2json.ingest import backends

    try:
        pages = backends.BACKENDS["pypdfium2"](Path(pdf))
    except Exception:  # noqa: BLE001 - heurystyka pomiarowa
        return True
    return sum(len(p.strip()) for p in pages) >= min_chars


def doc_source(pred_root: Path, rel_pdf: str) -> str:
    """'skan', gdy trace `<pred_root>/.trace/<rel>.trace.json` ma `ocr_used` = true; inaczej 'tekst'.

    Brak lub uszkodzony trace daje 'tekst'.
    """
    trace = Path(pred_root) / ".trace" / Path(rel_pdf).with_suffix(".json").with_suffix(".trace.json")
    try:
        data = json.loads(trace.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return SOURCE_TEXT
    return SOURCE_SCAN if isinstance(data, dict) and data.get("ocr_used") is True else SOURCE_TEXT


# ---------------------------------------------------------------- katalogi


@dataclass
class DocResult:
    rel: str
    doc_type: str
    counts: Counts
    pred_missing: bool
    negative: bool
    neg_correct: bool = False
    source: str = SOURCE_TEXT

    def to_dict(self) -> dict:
        return {
            "doc": self.rel,
            "type": self.doc_type,
            "source": self.source,
            "pred_missing": self.pred_missing,
            **self.counts.to_dict(),
        }


@dataclass
class Report:
    docs: list = field(default_factory=list)
    total: Counts = field(default_factory=Counts)
    by_type: dict = field(default_factory=dict)
    by_source: dict = field(default_factory=dict)  # zrodlo -> Counts (z negatywami, sumuje sie do total)
    by_type_source: dict = field(default_factory=dict)  # "typ/zrodlo" -> Counts (bez negatywow)
    docs_by_source: dict = field(default_factory=dict)
    neg_total: int = 0
    neg_correct: int = 0

    @property
    def fields(self) -> dict:
        return self.total.fields

    def to_dict(self) -> dict:
        return {
            "total": self.total.to_dict(),
            "by_type": {k: v.to_dict() for k, v in self.by_type.items()},
            "by_source": {k: v.to_dict() for k, v in sorted(self.by_source.items())},
            "by_type_source": {k: v.to_dict() for k, v in sorted(self.by_type_source.items())},
            "docs_by_source": dict(sorted(self.docs_by_source.items())),
            "fields": {k: v.to_dict() for k, v in sorted(self.fields.items())},
            "negatives": {
                "total": self.neg_total,
                "correct": self.neg_correct,
                "rate": self.neg_correct / self.neg_total if self.neg_total else None,
            },
            "docs": [d.to_dict() for d in self.docs],
        }


def load_json(p: Path) -> Any:
    """Dane albo None gdy plik nie istnieje / jest pusty / niepoprawny."""
    try:
        txt = p.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    if not txt.strip():
        return None
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return None


def score_dirs(
    pred_root: Path,
    gt_root: Path,
    cfg: ScoreConfig = _DEFAULT_CFG,
    registry: dict | None = None,
    sources: dict | None = None,
) -> Report:
    """Ocenia wszystkie `*.pdf` z `gt_root` (takze w podkatalogach, np. `skany/odwolania/0001/`).

    GT dla `X.pdf` to `X.json` obok niego, a gdy go brak - `cfg.gt_name_for_pdf`. Typ dokumentu to typ
    z `registry` (domyslnie `load_registry()`), ktorego szablon pasuje do kluczy GT; gdy zaden nie pasuje,
    nazwa pliku GT. `sources`: rel (posix) -> 'tekst'|'skan' nadpisuje odczyt z trace.
    """
    pred_root, gt_root = Path(pred_root), Path(gt_root)
    if registry is None:
        from odw2json.config_loader import load_registry

        registry = load_registry()
    rep = Report()
    for pdf in sorted(gt_root.rglob("*.pdf")):
        rel_dir = pdf.parent.relative_to(gt_root)
        rel = (rel_dir / pdf.name).as_posix()
        gt_path = gt_path_for_pdf(pdf, cfg)
        gt = load_json(gt_path) if gt_path else None
        pred = load_json(pred_root / rel_dir / f"{pdf.stem}.json")
        negative = gt is None
        counts = score_pair(pred, gt, cfg)
        source = (sources or {}).get(rel) or doc_source(pred_root, rel)
        dtype = "negative" if negative else (infer_doc_type(gt, registry) or gt_path.stem)
        res = DocResult(rel, dtype, counts, pred is None, negative, source=source)
        if negative:
            rep.neg_total += 1
            # poprawne odrzucenie = brak pliku, pusty plik albo {} (nie: szablon z nullami)
            res.neg_correct = pred is None or pred == {}
            rep.neg_correct += int(res.neg_correct)
        rep.docs.append(res)
        rep.total = rep.total + counts
        rep.by_type[dtype] = rep.by_type.get(dtype, Counts()) + counts
        rep.by_source[source] = rep.by_source.get(source, Counts()) + counts
        rep.docs_by_source[source] = rep.docs_by_source.get(source, 0) + 1
        if not negative:
            key = f"{dtype}/{source}"
            rep.by_type_source[key] = rep.by_type_source.get(key, Counts()) + counts
    return rep


# --------------------------------------------------------------------- CLI


def _row(name: str, c: Counts, w: int) -> str:
    return (
        f"{name:<{w}} {c.tp:>5} {c.tn:>5} {c.fp:>5} {c.fn:>5}  {c.precision:6.3f} {c.recall:6.3f} {c.f1:6.3f}"
    )


def _hdr(w: int) -> str:
    return f"{'':<{w}} {'TP':>5} {'TN':>5} {'FP':>5} {'FN':>5}  {'P':>6} {'R':>6} {'F1':>6}"


def format_report(rep: Report, worst: int = 10) -> str:
    L = []
    t = rep.total
    L += ["== GLOBALNIE ==", _hdr(12), _row("razem", t, 12), f"accuracy (z TN): {t.accuracy:.3f}", ""]
    L += ["== WG TYPU DOKUMENTU ==", _hdr(16)]
    for k in sorted(rep.by_type):
        L.append(_row(k, rep.by_type[k], 16))
    if len(rep.by_source) > 1 or SOURCE_SCAN in rep.by_source:
        L += ["", "== WG ZRODLA (tekst / skan) ==", _hdr(16)]
        for k in sorted(rep.by_source):
            L.append(_row(f"{k} ({rep.docs_by_source.get(k, 0)} dok.)", rep.by_source[k], 16))
    if rep.neg_total:
        L.append(
            f"negatywy: poprawnie odrzucone {rep.neg_correct}/{rep.neg_total} "
            f"({rep.neg_correct / rep.neg_total:.1%})"
        )
    L += ["", "== POLA (od najgorszego F1) =="]
    fl = sorted(rep.fields.items(), key=lambda kv: (kv[1].f1, -(kv[1].fp + kv[1].fn), kv[0]))
    w = min(50, max([len(k) for k, _ in fl] + [5]))
    L.append(_hdr(w))
    for k, c in fl:
        L.append(_row(k[:w], c, w))
    L += ["", f"== {worst} NAJGORSZYCH DOKUMENTOW =="]
    bad = sorted(
        (d for d in rep.docs if d.counts.fp + d.counts.fn > 0),
        key=lambda d: (d.counts.f1, -(d.counts.fp + d.counts.fn)),
    )[:worst]
    for d in bad:
        c = d.counts
        L.append(
            f"{d.rel:<60} {d.doc_type:<14} F1={c.f1:.3f} FP={c.fp} FN={c.fn}"
            + ("  [brak pliku pred]" if d.pred_missing else "")
        )
    return "\n".join(L)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ocena F1 wyniku wzgledem GT")
    ap.add_argument("--pred", required=True, type=Path)
    ap.add_argument("--gt", required=True, type=Path)
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--json", type=Path, default=None, help="zapisz raport JSON")
    ap.add_argument("--worst", type=int, default=10)
    ap.add_argument("--lenient-types", action="store_true")
    ap.add_argument("--casefold-exact", action="store_true")
    a = ap.parse_args(argv)
    cfg = ScoreConfig(threshold=a.threshold, lenient_types=a.lenient_types, casefold_exact=a.casefold_exact)
    rep = score_dirs(a.pred, a.gt, cfg)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(format_report(rep, a.worst))
    if a.json:
        a.json.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
