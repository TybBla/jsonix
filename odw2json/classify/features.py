"""Silnik cech klasyfikatora: punktacja jednego typu dokumentu wg ``ClassifyConfig`` (YAML).

Wszystkie dopasowania działają na tekście znormalizowanym (``textnorm.fold``: małe litery, bez polskich
znaków), dzięki czemu błędy OCR typu ł->l czy Ę->E nie mają znaczenia. Żadna cecha nie widzi nazwy pliku.

Dwa sposoby czytania nagłówka:
- ``header(n)`` - jeden ciąg (pierwsze ``n`` znaków, rozstrzelone litery zwinięte); używa go
  ``title_mode: anywhere``;
- ``header_lines(n)`` - znormalizowane linie tych znaków (bez interpunkcji przy brzegach); używają
  ``title_mode: line`` oraz kary za nagłówki dokumentów obcych (``foreign_titles``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from odw2json.config_loader import (
    REGEX_PREFIX,
    TITLE_TOKEN,
    ClassifyConfig,
    ClassifySettings,
    RequiredGroup,
)
from odw2json.textnorm import collapse_spaced_letters, fold

_EDGE_JUNK = re.compile(r"^[\W_]+|[\W_]+$")


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
        self._lines: dict[int, list[str]] = {}
        self._foreign: tuple[ClassifySettings, list[str]] | None = None

    def header(self, n: int) -> str:
        """Nagłówek: pierwsze ``n`` znaków, rozstrzelone litery zwinięte, następnie ``fold``."""
        if n not in self._headers:
            self._headers[n] = fold(collapse_spaced_letters(self.raw[:n]))
        return self._headers[n]

    def header_lines(self, n: int) -> list[str]:
        """Niepuste linie nagłówka (``fold``, bez interpunkcji i znaków specjalnych przy brzegach)."""
        if n not in self._lines:
            lines = (fold(line) for line in collapse_spaced_letters(self.raw[:n]).splitlines())
            stripped = (_EDGE_JUNK.sub("", line) for line in lines)
            self._lines[n] = [line for line in stripped if line]
        return self._lines[n]

    def foreign_hits(self, settings: ClassifySettings) -> list[str]:
        """Frazy ``foreign_titles`` trafione w nagłówku (liczone raz na dokument, filtrowane per typ)."""
        if self._foreign is None or self._foreign[0] is not settings:
            self._foreign = (settings, _foreign_hits(self, settings))
        return self._foreign[1]


def _flags() -> int:
    return re.IGNORECASE


def _word(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")


def _required_hit(item: str, text: str) -> bool:
    if item.startswith(REGEX_PREFIX):
        return re.search(item[len(REGEX_PREFIX) :], text, _flags()) is not None
    return fold(item) in text


def _title_hits(prepared: Prepared, cfg: ClassifyConfig) -> list[str]:
    """Frazy ``title`` trafione w nagłówku wg ``title_mode``."""
    if not cfg.title:
        return []
    if cfg.title_mode == "anywhere":
        header = prepared.header(cfg.header_chars)
        return [p for p in cfg.title if fold(p) in header]
    lines = [ln for ln in prepared.header_lines(cfg.header_chars) if len(ln) <= cfg.title_line_max_chars]
    return [
        p for p in cfg.title if any(_is_title_line(fold(p), ln, cfg.title_line_min_cover) for ln in lines)
    ]


def _is_title_line(phrase: str, line: str, min_cover: float) -> bool:
    """Linia jest tytulem, gdy zawiera fraze (granice slow) i fraza zajmuje >= ``min_cover`` linii.

    Fraza wielowyrazowa dopasowywana jest tez bez spacji (``potwierdzenieprzelewu``): OCR i rozstrzelony
    druk gubia odstepy miedzy wyrazami tytulu.
    """
    if _word(phrase).search(line):
        return len(phrase) / len(line) >= min_cover
    if " " in phrase:
        compact, compact_line = phrase.replace(" ", ""), line.replace(" ", "")
        return compact in compact_line and len(compact) / len(compact_line) >= min_cover
    return False


def _foreign_hits(prepared: Prepared, settings: ClassifySettings) -> list[str]:
    ft = settings.foreign_titles
    if not ft.phrases:
        return []
    lines = prepared.header_lines(ft.header_chars)
    hits = []
    for phrase in ft.phrases:
        pat = re.compile(rf"^{re.escape(fold(phrase))}(?!\w)")
        if any(pat.search(line) for line in lines):
            hits.append(phrase)
    return hits


def _exempt_from_foreign(phrase: str, cfg: ClassifyConfig) -> bool:
    """Typ nie jest karany za fraze obca z ``ignore_foreign`` ani pokrywajaca sie z wlasnym ``title``.

    Pokrycie = po normalizacji fraza obca zaczyna tytul albo tytul zaczyna fraze obca (np. typ z
    ``title: [wyrok]`` nie jest karany za naglowek ``wyrok``).
    """
    f = fold(phrase).strip()
    if any(fold(p).strip() == f for p in cfg.ignore_foreign):
        return True
    return any(t.startswith(f) or f.startswith(t) for t in (fold(p).strip() for p in cfg.title) if t)


def _required_ok(item: str | RequiredGroup, text: str, title_hit: bool) -> bool:
    entries = item.all_of if isinstance(item, RequiredGroup) else [item]
    return all(title_hit if e == TITLE_TOKEN else _required_hit(e, text) for e in entries)


def _describe(item: str | RequiredGroup) -> str:
    return "(" + " + ".join(item.all_of) + ")" if isinstance(item, RequiredGroup) else item


def evaluate(prepared: Prepared, cfg: ClassifyConfig, settings: ClassifySettings | None = None) -> TypeScore:
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

    title_hits = _title_hits(prepared, cfg)
    if title_hits:  # tytuł liczy się raz, niezależnie od liczby pasujących wariantów
        add(w.title, "title: " + ", ".join(repr(p) for p in title_hits))

    for pat in cfg.patterns:
        if re.search(pat.regex, text, _flags()):
            add(pat.weight, f"pattern: {pat.regex!r}")

    if settings is not None:
        foreign = [p for p in prepared.foreign_hits(settings) if not _exempt_from_foreign(p, cfg)]
        if foreign:  # kara raz na typ, niezależnie od liczby trafień
            add(settings.foreign_titles.weight, "foreign title: " + ", ".join(repr(p) for p in foreign))

    if cfg.required_any and not any(_required_ok(item, text, bool(title_hits)) for item in cfg.required_any):
        listed = ", ".join(_describe(i) for i in cfg.required_any)
        res.excluded = f"brak wymaganej cechy (required_any: {listed})"
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
