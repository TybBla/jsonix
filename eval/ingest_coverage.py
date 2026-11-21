"""Miara pokrycia tekstu: czy wartosci z GT wystepuja w tekscie wyciagnietym z PDF.

Mierzy jakosc ingestu (backend PDF + czyszczenie) niezaleznie od reszty pipeline'u.
Pola "doslowne" sprawdzane sa po normalizacji porownawczej (NFKC, casefold, ujednolicone
cudzyslowy i myslniki, zwiniete biale znaki), pola cyfrowe (NIP, KRS, IBAN...) po samych cyfrach
z opcjonalnym separatorem miedzy cyframi. Imiona i nazwiska maja dodatkowo trafienie rozmyte
(pierwsze 4 litery kazdego slowa jako poczatek tokenu), bo w tekscie bywaja w innym przypadku.

Uzycie: python -m eval.ingest_coverage [--backend NAME] [--split dev|holdout|all]
        [--show-missing 20] [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.score import SOURCE_SCAN, SOURCE_TEXT, gt_path_for_pdf, has_text_layer, infer_doc_type
from odw2json.config_loader import ROOT_DIR, load_registry
from odw2json.splits import load_splits

LITERAL_KEYS = frozenset(
    {"nazwa", "tytul", "imie_nazwisko", "mail", "numer_postepowania", "numer_transakcji", "miejscowosc"}
)
DIGIT_KEYS = frozenset({"krs", "nip", "regon", "pesel", "na_rachunek", "z_rachunku"})
FUZZY_KEYS = frozenset({"imie_nazwisko"})

TRAIN_DIR = ROOT_DIR / "data" / "train"

_QUOTES = str.maketrans({c: '"' for c in "„”«»‚’‘“'\""})
_DASHES = str.maketrans({c: "-" for c in "–—‒‐‑−"})
_SEP = r"[\s\-./]?"


def normalize(s: str) -> str:
    """NFKC, casefold, ujednolicone cudzyslowy/myslniki, biale znaki zwiniete do pojedynczej spacji."""
    s = unicodedata.normalize("NFKC", s).casefold().translate(_QUOTES).translate(_DASHES)
    return " ".join(s.split())


@dataclass
class Coverage:
    found: int = 0
    found_fuzzy: int = 0
    total: int = 0
    missing: list[tuple[str, str]] = field(default_factory=list)
    by_field: dict[str, Coverage] = field(default_factory=dict, compare=False, repr=False)

    def __add__(self, o: Coverage) -> Coverage:
        r = Coverage(
            self.found + o.found,
            self.found_fuzzy + o.found_fuzzy,
            self.total + o.total,
            self.missing + o.missing,
        )
        for src in (self.by_field, o.by_field):
            for k, v in src.items():
                r.by_field[k] = r.by_field.get(k, Coverage()) + _plain(v)
        return r

    @property
    def rate(self) -> float:
        """Odsetek trafien dokladnych."""
        return self.found / self.total if self.total else 0.0

    @property
    def rate_with_fuzzy(self) -> float:
        return (self.found + self.found_fuzzy) / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "found_fuzzy": self.found_fuzzy,
            "total": self.total,
            "rate": self.rate,
            "rate_with_fuzzy": self.rate_with_fuzzy,
        }


def _plain(c: Coverage) -> Coverage:
    return Coverage(c.found, c.found_fuzzy, c.total, list(c.missing))


def _leaves(v: Any, path: str = "") -> list[tuple[str, Any]]:
    """Liscie GT; sciezki jak w eval.score (listy jako `[]`)."""
    if isinstance(v, dict):
        out: list[tuple[str, Any]] = []
        for k, x in v.items():
            out += _leaves(x, f"{path}.{k}" if path else k)
        return out
    if isinstance(v, list):
        out = []
        for x in v:
            out += _leaves(x, path + "[]")
        return out
    return [(path, v)]


def _key_of(path: str) -> str:
    return path.rsplit(".", 1)[-1].replace("[]", "")


def _digits_pattern(digits: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\d)" + _SEP.join(digits) + r"(?!\d)")


def _literal_found(norm_text: str, norm_value: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(norm_value) + r"(?!\w)", norm_text) is not None


def _fuzzy_name_found(tokens: set[str], norm_value: str) -> bool:
    words = re.findall(r"\w+", norm_value)
    if not words:
        return False
    for w in words:
        if len(w) >= 4:
            if not any(t.startswith(w[:4]) for t in tokens):
                return False
        elif w not in tokens:
            return False
    return True


def coverage_for_doc(text: str, gt: dict, doc_type: str) -> Coverage:
    """Pokrycie wartosci GT (pola doslowne i cyfrowe) w tekscie dokumentu.

    `doc_type` (stem GT: odwolanie, pelnomocnictwo, przelew) jest zachowany w sygnaturze dla
    spojnosci z raportem; zbior pol zalezy tylko od nazwy pola.
    """
    nfkc = unicodedata.normalize("NFKC", text)
    norm_text = normalize(text)
    tokens = set(re.findall(r"\w+", norm_text))
    cov = Coverage()
    for path, raw in _leaves(gt):
        key = _key_of(path)
        if raw is None or isinstance(raw, bool) or key not in LITERAL_KEYS | DIGIT_KEYS:
            continue
        value = str(raw)
        if key in DIGIT_KEYS:
            digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", value))
            if not digits:
                continue
            hit = _digits_pattern(digits).search(nfkc) is not None
            fuzzy = False
        else:
            nv = normalize(value)
            if not nv:
                continue
            hit = _literal_found(norm_text, nv)
            fuzzy = not hit and key in FUZZY_KEYS and _fuzzy_name_found(tokens, nv)
        f = cov.by_field.setdefault(path, Coverage())
        cov.total += 1
        f.total += 1
        if hit:
            cov.found += 1
            f.found += 1
        elif fuzzy:
            cov.found_fuzzy += 1
            f.found_fuzzy += 1
        else:
            cov.missing.append((path, value))
            f.missing.append((path, value))
    return cov


# --------------------------------------------------------------------- zbior


@dataclass
class Report:
    total: Coverage = field(default_factory=Coverage)
    by_type: dict[str, Coverage] = field(default_factory=dict)
    by_source: dict[str, Coverage] = field(default_factory=dict)  # 'tekst' / 'skan'
    by_type_source: dict[str, Coverage] = field(default_factory=dict)  # 'typ/zrodlo'
    docs_by_source: dict[str, int] = field(default_factory=dict)
    docs: int = 0
    load_errors: list[tuple[str, str]] = field(default_factory=list)
    foreign_backend: list[tuple[str, str]] = field(default_factory=list)  # (doc, backend inny niz zadany)

    @property
    def by_field(self) -> dict[str, Coverage]:
        return self.total.by_field

    def to_dict(self) -> dict:
        return {
            "global": self.total.to_dict(),
            "by_type": {k: v.to_dict() for k, v in sorted(self.by_type.items())},
            "by_source": {k: v.to_dict() for k, v in sorted(self.by_source.items())},
            "by_type_source": {k: v.to_dict() for k, v in sorted(self.by_type_source.items())},
            "docs_by_source": dict(sorted(self.docs_by_source.items())),
            "by_field": {k: v.to_dict() for k, v in sorted(self.by_field.items())},
            "missing": [{"field": p, "value": v} for p, v in self.total.missing],
            "docs": self.docs,
            "load_errors": [{"doc": d, "error": e} for d, e in self.load_errors],
            "foreign_backend": [{"doc": d, "backend": b} for d, b in self.foreign_backend],
        }


def _make_loader(backend: str | None):
    """Loader; przy jawnym backendzie bez fallbackow, zeby pokrycie liczylo sie tylko jemu."""
    from odw2json.config_loader import load_app_config
    from odw2json.ingest import load

    if backend is None:
        return load
    cfg = {**(load_app_config().get("ingest", {}) or {}), "fallback_backends": []}

    def _load(path: Path):
        return load(path, backend=backend, cfg=cfg)

    return _load


def _cases(split: str) -> list[str]:
    splits = load_splits()
    if split == "all":
        return sorted(splits["dev"] + splits["holdout"])
    return sorted(splits[split])


def run_coverage(
    split: str = "all",
    backend: str | None = None,
    train_dir: Path = TRAIN_DIR,
    cases: list[str] | None = None,
) -> Report:
    """Pokrycie wartosci GT w tekscie z ingestu.

    GT dla `X.pdf`: `X.json` obok niego, inaczej `GT_NAME_FOR_PDF`; typ dokumentu z kluczy GT (fallback:
    nazwa pliku GT). Zrodlo: 'skan', gdy `doc.ocr_used`, albo gdy PDF nie ma warstwy tekstowej
    (< 30 znakow w surowej ekstrakcji; dotyczy tez bledu wczytania i nieudanego OCR); inaczej 'tekst'.
    `cases` nadpisuje liste spraw splitu (testy).
    """
    loader = _make_loader(backend)
    registry = load_registry()
    rep = Report()
    for case in cases if cases is not None else _cases(split):
        for pdf in sorted((train_dir / case).glob("*.pdf")):
            gt_path = gt_path_for_pdf(pdf)
            if gt_path is None:
                continue
            gt = json.loads(gt_path.read_text(encoding="utf-8-sig"))
            gt_type = infer_doc_type(gt, registry) or gt_path.stem
            rel = f"{case}/{pdf.name}"
            ocr_used = False
            try:
                doc = loader(pdf)
                text = doc.text
                ocr_used = bool(doc.ocr_used)
                if backend is not None and doc.backend != backend:
                    rep.foreign_backend.append((rel, doc.backend))
            except Exception as e:  # noqa: BLE001 - narzedzie pomiarowe, jedziemy dalej
                rep.load_errors.append((rel, f"{type(e).__name__}: {e}"))
                text = ""
            source = SOURCE_SCAN if ocr_used or not has_text_layer(pdf) else SOURCE_TEXT
            rep.docs += 1
            cov = coverage_for_doc(text, gt, gt_type)
            cov.missing = [(f"{rel}: {p}", v) for p, v in cov.missing]
            rep.total = rep.total + cov
            rep.by_type[gt_type] = rep.by_type.get(gt_type, Coverage()) + cov
            rep.by_source[source] = rep.by_source.get(source, Coverage()) + cov
            key = f"{gt_type}/{source}"
            rep.by_type_source[key] = rep.by_type_source.get(key, Coverage()) + cov
            rep.docs_by_source[source] = rep.docs_by_source.get(source, 0) + 1
    return rep


# --------------------------------------------------------------------- CLI


def _row(name: str, c: Coverage, w: int) -> str:
    return f"{name:<{w}} {c.found:>6} {c.found_fuzzy:>6} {c.total:>6}  {c.rate:7.1%} {c.rate_with_fuzzy:7.1%}"


def _hdr(w: int) -> str:
    return f"{'':<{w}} {'exact':>6} {'fuzzy':>6} {'total':>6}  {'rate':>7} {'+fuzzy':>7}"


def format_report(rep: Report, show_missing: int = 20) -> str:
    out = [f"== GLOBALNIE ({rep.docs} dokumentow) ==", _hdr(12), _row("razem", rep.total, 12), ""]
    out += ["== WG TYPU DOKUMENTU ==", _hdr(16)]
    for k in sorted(rep.by_type):
        out.append(_row(k, rep.by_type[k], 16))
    out += ["", "== WG ZRODLA (tekst / skan) ==", _hdr(24)]
    for k in sorted(rep.by_source):
        out.append(_row(f"{k} ({rep.docs_by_source.get(k, 0)} dok.)", rep.by_source[k], 24))
    for k in sorted(rep.by_type_source):
        out.append(_row(k, rep.by_type_source[k], 24))
    out += ["", "== POLA (od najgorszego) =="]
    fields = sorted(
        rep.by_field.items(),
        key=lambda kv: (kv[1].rate_with_fuzzy, kv[1].rate, -kv[1].total, kv[0]),
    )
    w = min(50, max([len(k) for k, _ in fields] + [5]))
    out.append(_hdr(w))
    for k, c in fields:
        out.append(_row(k[:w], c, w))
    miss = rep.total.missing
    out += ["", f"== BRAKI ({min(show_missing, len(miss))} z {len(miss)}) =="]
    for p, v in miss[:show_missing]:
        out.append(f"{p} = {v!r}")
    if rep.load_errors:
        out += ["", f"== BLEDY WCZYTANIA ({len(rep.load_errors)}) =="]
        out += [f"{d}: {e}" for d, e in rep.load_errors]
    return "\n".join(out)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pokrycie wartosci GT w tekscie z ingestu")
    ap.add_argument("--backend", default=None, help="nazwa backendu PDF (domyslnie: konfiguracja)")
    ap.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    ap.add_argument("--show-missing", type=int, default=20)
    ap.add_argument("--json", type=Path, default=None, help="zapisz pelny raport JSON")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    rep = run_coverage(a.split, a.backend)
    print(format_report(rep, a.show_missing))
    if a.json:
        a.json.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
