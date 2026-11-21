"""Silnik cech klasyfikatora: punktacja jednego typu dokumentu wg ``ClassifyConfig`` (YAML).

Wszystkie dopasowania działają na tekście znormalizowanym (``textnorm.fold``: małe litery, bez polskich
znaków), dzięki czemu błędy OCR typu ł->l czy Ę->E nie mają znaczenia. Żadna cecha nie widzi nazwy pliku.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from odw2json.config_loader import REGEX_PREFIX, ClassifyConfig
from odw2json.textnorm import collapse_spaced_letters, fold


@dataclass
class TypeScore:
    """Wynik jednego typu: suma punktów, trafione cechy i ewentualny powód wykluczenia."""

    score: float = 0.0
    evidence: list[str] = field(default_factory=list)
    excluded: str | None = None  # powód odpadnięcia (np. brak trafienia w required_any)


class Prepared:
    """Tekst dokumentu przygotowany raz do punktacji wszystkich typów (pełny i nagłówki)."""

    def __init__(self, text: str):
        self.raw = text
        self.full = fold(text)
        self._headers: dict[int, str] = {}

    def header(self, n: int) -> str:
        """Nagłówek: pierwsze ``n`` znaków, rozstrzelone litery zwinięte, następnie ``fold``."""
        if n not in self._headers:
            self._headers[n] = fold(collapse_spaced_letters(self.raw[:n]))
        return self._headers[n]


def _flags() -> int:
    return re.IGNORECASE


def _required_hit(item: str, text: str) -> bool:
    if item.startswith(REGEX_PREFIX):
        return re.search(item[len(REGEX_PREFIX) :], text, _flags()) is not None
    return fold(item) in text


def evaluate(prepared: Prepared, cfg: ClassifyConfig) -> TypeScore:
    """Punktuje dokument względem jednego typu; zwraca wynik, dowody i ewentualne wykluczenie."""
    w = cfg.weights
    text = prepared.full
    res = TypeScore()

    def add(points: float, label: str) -> None:
        res.score += points
        res.evidence.append(f"{label} ({points:+g})")

    for kind, phrases, weight in (
        ("strong", cfg.strong, w.strong),
        ("weak", cfg.weak, w.weak),
        ("negative", cfg.negative, w.negative),
    ):
        for phrase in phrases:
            if fold(phrase) in text:
                add(weight, f"{kind}: {phrase!r}")

    if cfg.title:
        header = prepared.header(cfg.header_chars)
        hits = [p for p in cfg.title if fold(p) in header]
        if hits:  # tytuł liczy się raz, niezależnie od liczby pasujących wariantów
            add(w.title, "title: " + ", ".join(repr(p) for p in hits))

    for pat in cfg.patterns:
        if re.search(pat.regex, text, _flags()):
            add(pat.weight, f"pattern: {pat.regex!r}")

    if cfg.required_any and not any(_required_hit(item, text) for item in cfg.required_any):
        res.excluded = "brak wymaganej cechy (required_any: " + ", ".join(cfg.required_any) + ")"
    return res


def confidence(best: float, second: float, min_score: float) -> float:
    """Pewność w [0, 1] = ``margines * nasycenie``.

    - ``margines = (best - max(second, 0)) / best`` - jak wyraźnie zwycięzca wyprzedza drugi typ
      (0 przy remisie, 1 gdy drugi typ nie zdobył punktów);
    - ``nasycenie = min(1, best / (2 * min_score))`` - jak daleko wynik jest powyżej progu
      (0,5 dokładnie na progu, 1 od dwukrotności progu).
    """
    if best <= 0:
        return 0.0
    margin = min(1.0, max(0.0, (best - max(second, 0.0)) / best))
    saturation = min(1.0, best / (2 * max(min_score, 1e-9)))
    return round(margin * saturation, 4)
