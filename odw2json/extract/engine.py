"""Silnik ekstrakcji sterowany konfiguracją YAML (sekcje ``fields`` i ``lists`` typu dokumentu).

Kod nie zna nazw pól UZP: każde pole opisuje ścieżka w szablonie wyniku + lista ekstraktorów,
normalizatory i walidatory. Wszystko rozszerzalne przez rejestry ``EXTRACTORS``, ``NORMALIZERS``,
``VALIDATORS`` (dekoratory ``register_*``), więc nowe typy/pola dodaje się konfiguracją.

Przebieg dla pola: zakres (``scope``) -> ekstraktory po kolei; każdy zwraca kandydatów (``Hit``),
kandydat przechodzi ``normalize`` (łańcuch, ``None`` = odrzut) i ``validate``; pierwszy poprawny
wygrywa. Brak poprawnego kandydata = ``null`` (fałszywa wartość kosztuje tyle co brak).

Dopasowanie etykiet/fraz/zakresów odbywa się na tekście „złożonym” (``fold``: małe litery, bez
polskich znaków, ta sama długość co oryginał), a wartości wycinane są z oryginału po offsetach.
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
import unicodedata
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from odw2json.config_loader import load_lookup
from odw2json.contracts import Document, ExtractionResult, FieldResult

if TYPE_CHECKING:
    from odw2json.config_loader import DocTypeConfig, FieldSpec

REGEX_PREFIX = "re:"
LIST_MARK = "[]"
SNIPPET_MAX = 300

# ============================================================== tekst złożony


_FOLD_EXTRA = {"ł": "l", "Ł": "l", "ø": "o", "đ": "d", "ß": "s"}


@lru_cache(maxsize=4096)
def _fold_char(ch: str) -> str:
    if ch in _FOLD_EXTRA:
        return _FOLD_EXTRA[ch]
    low = ch.lower()
    if len(low) != 1:
        low = ch
    base = unicodedata.normalize("NFKD", low)
    c = base[0] if base else low
    return c if c.isascii() or not base else low


def fold(text: str) -> str:
    """Małe litery bez diakrytyków; **ta sama długość** co wejście (offsety zachowane)."""
    return "".join(_fold_char(c) for c in text)


@lru_cache(maxsize=2048)
def phrase_pattern(spec: str, line_start: bool = False) -> re.Pattern:
    """``re:<regex>`` (na tekście złożonym) albo fraza: granice słów, dowolne białe znaki."""
    if spec.startswith(REGEX_PREFIX):
        return re.compile(spec[len(REGEX_PREFIX) :], re.IGNORECASE | re.MULTILINE)
    words = fold(spec).split()
    body = r"\s+".join(re.escape(w) for w in words)
    pre = r"^[ \t]*" if line_start else r"(?<![a-z0-9])"
    return re.compile(pre + body + r"(?![a-z0-9])", re.MULTILINE)


@lru_cache(maxsize=1024)
def value_pattern(pattern: str, case: bool = False) -> re.Pattern:
    flags = re.MULTILINE | (0 if case else re.IGNORECASE)
    return re.compile(pattern, flags)


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


# ============================================================== kontekst i kandydaci


@dataclass
class Hit:
    """Kandydat na wartość: tekst + pozycja w ``doc.text`` (``anchor`` = początek etykiety)."""

    value: Any
    start: int = -1
    end: int = -1
    anchor: int | None = None


@dataclass
class Ctx:
    """Kontekst ekstraktora: dokument, tekst złożony i bieżący zakres ``[start, end)``."""

    doc: Document
    text: str
    folded: str
    start: int
    end: int
    field_type: str = "str"
    config_dir: Any = None  # katalog config/ typu (lookupy ekstraktorów, np. phrase_lookup)

    def search(self, pattern: str, case: bool = False) -> re.Match | None:
        return value_pattern(pattern, case).search(self.text, self.start, self.end)

    def line_bounds(self, pos: int) -> tuple[int, int]:
        ls = self.text.rfind("\n", 0, pos) + 1
        le = self.text.find("\n", pos)
        return ls, (len(self.text) if le < 0 else le)

    def type_pattern(self, opts: dict) -> tuple[str | None, bool]:
        if opts.get("value"):
            return opts["value"], bool(opts.get("case"))
        t = TYPES.get(self.field_type)
        return (t.pattern if t else None), False


# ============================================================== rejestry


@dataclass(frozen=True)
class ExtractorDef:
    fn: Callable[[Ctx, dict], Iterator[Hit]]
    primary: str
    options: frozenset[str]


EXTRACTORS: dict[str, ExtractorDef] = {}
NORMALIZERS: dict[str, Callable[[Any], Any]] = {}
VALIDATORS: dict[str, Callable[[Any, Any], bool]] = {}


def register_extractor(name: str, primary: str, options: tuple[str, ...] = ()):
    """Rejestruje ekstraktor ``fn(ctx, opts) -> Iterator[Hit]``.

    ``primary`` - opcja przyjmowana z zapisu skróconego (``- label: [..]``); ``options`` - pozostałe
    dozwolone opcje (zapis pełny ``- label: {labels: [..], max_chars: 80}``).
    """

    def deco(fn):
        EXTRACTORS[name] = ExtractorDef(fn, primary, frozenset(options) | {primary})
        return fn

    return deco


def register_normalizer(name: str):
    """Rejestruje normalizator ``fn(value: str) -> Any | None`` (``None`` = odrzuć kandydata)."""

    def deco(fn):
        NORMALIZERS[name] = fn
        return fn

    return deco


def register_validator(name: str):
    """Rejestruje walidator ``fn(value, arg) -> bool`` (klucz w ``validate: {name: arg}``)."""

    def deco(fn):
        VALIDATORS[name] = fn
        return fn

    return deco


def parse_extractor_entry(entry: Any) -> tuple[str, dict]:
    """``{label: [...]}`` / ``{label: {...}}`` / ``{label: [...], max_chars: 80}`` -> (nazwa, opcje).

    Rzuca ``ValueError`` z czytelnym komunikatem przy błędzie (używane też przy ładowaniu konfiguracji).
    """
    if not isinstance(entry, dict):
        raise ValueError(f"wpis ekstraktora musi być mapą, jest {entry!r}")
    names = [k for k in entry if k in EXTRACTORS]
    if len(names) != 1:
        unknown = [k for k in entry if k not in EXTRACTORS]
        if not names:
            raise ValueError(f"nieznany ekstraktor {unknown} (dostępne: {', '.join(sorted(EXTRACTORS))})")
        raise ValueError(f"wpis ekstraktora musi mieć dokładnie jeden ekstraktor, jest {names}")
    name = names[0]
    d = EXTRACTORS[name]
    raw = entry[name]
    opts = dict(raw) if isinstance(raw, dict) else {d.primary: raw}
    opts.update({k: v for k, v in entry.items() if k != name})
    bad = sorted(set(opts) - d.options - {WITHIN})
    if bad:
        raise ValueError(
            f"ekstraktor {name!r}: nieznane opcje {bad} (dozwolone: {', '.join(sorted(d.options))}, {WITHIN})"
        )
    for key in ("pattern", "value"):
        if isinstance(opts.get(key), str):
            try:
                re.compile(opts[key])
            except re.error as e:
                raise ValueError(f"ekstraktor {name!r}: niepoprawny regex {opts[key]!r}: {e}") from e
    for key in ("labels", "phrases", "header", "stop"):
        for p in _as_list(opts.get(key)):
            check_phrase(p)
    for i, w in enumerate(_as_list(opts.get(WITHIN))):
        if not isinstance(w, dict) or not w or set(w) - _WITHIN_KEYS:
            raise ValueError(
                f"ekstraktor {name!r}: {WITHIN}[{i}] musi być mapą z kluczami "
                f"{sorted(_WITHIN_KEYS)}, jest {w!r}"
            )
        for key in ("after", "before"):
            for p in _as_list(w.get(key)):
                check_phrase(p)
    return name, opts


# Opcja wspólna wszystkich ekstraktorów: okno (albo lista okien zawężanych po kolei) w zakresie pola.
WITHIN = "within"
_WITHIN_KEYS = frozenset({"after", "before", "max_chars"})


def check_phrase(p: Any) -> None:
    if not isinstance(p, str):
        raise ValueError(f"fraza musi być tekstem, jest {p!r}")
    if p.startswith(REGEX_PREFIX):
        try:
            re.compile(p[len(REGEX_PREFIX) :])
        except re.error as e:
            raise ValueError(f"niepoprawny regex {p!r}: {e}") from e


# ============================================================== typy pól


@dataclass(frozen=True)
class TypeDef:
    pattern: str | None  # wzorzec wartości (label/near szukają go w oknie po etykiecie)
    normalize: tuple[str, ...]  # domyślny łańcuch, gdy pole nie podaje ``normalize``


_MONTHS = r"(?:stycz|lut|mar|kwie|maj|maja|czerw|lip|sierp|wrze|pa[zź]dzier|listopad|grud)[a-ząćęłńóśźż]*"
DATE_PATTERN = (
    r"(?<!\d)(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}|\d{1,2}\s+"
    + _MONTHS
    + r"\s+\d{4})(?!\d)"
)
AMOUNT_PATTERN = r"(?<![\d,.])(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)[,.]\d{2}(?!\d|[.,]\d)"
IBAN_PATTERN = r"(?<![\dA-Za-z])(?:PL\s?)?\d{2}(?:\s?\d{4}){6}(?!\d)"
EMAIL_PATTERN = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"

TYPES: dict[str, TypeDef] = {
    "str": TypeDef(None, ("ws",)),
    "int": TypeDef(r"(?<!\d)\d+(?!\d)", ("int",)),
    "amount": TypeDef(AMOUNT_PATTERN, ("amount",)),
    "date": TypeDef(DATE_PATTERN, ("date",)),
    "iban": TypeDef(IBAN_PATTERN, ("iban",)),
    "digits": TypeDef(r"\d(?:[\d \-]*\d)?", ("digits",)),
    "email": TypeDef(EMAIL_PATTERN, ("email",)),
    "name": TypeDef(None, ("ws", "name")),
    "company": TypeDef(None, ("ws", "company")),
    "enum": TypeDef(None, ("ws",)),
    "lookup": TypeDef(None, ("ws",)),
}


# ============================================================== ekstraktory


_LEADER = " \t:.…·-–—_"


def _line_value(ctx: Ctx, pos: int, opts: dict) -> Hit | None:
    """Wartość w trybie liniowym: reszta linii po etykiecie albo następna niepusta linia (+ ciąg dalszy)."""
    text, end = ctx.text, ctx.end
    while pos < end and text[pos] in _LEADER:
        pos += 1
    if pos >= end:
        return None
    if text[pos] in "\r\n":  # wartość w następnej niepustej linii
        while pos < end and text[pos] in " \t\r\n":
            pos += 1
        if pos >= end:
            return None
    _, le = ctx.line_bounds(pos)
    le = min(le, end)
    first, vend = pos, le
    parts = [text[pos:le]]
    if opts.get("multiline"):
        stops = [phrase_pattern(s, True) for s in _as_list(opts.get("stop"))]
        max_lines = int(opts.get("max_lines", 8))
        while len(parts) < max_lines and vend + 1 < end:
            ns = vend + 1
            ne = text.find("\n", ns)
            ne = min(end, len(text) if ne < 0 else ne)
            line = text[ns:ne]
            if not line.strip() or any(p.match(ctx.folded, ns, ne) for p in stops):
                break
            parts.append(line)
            vend = ne
    value = "\n".join(parts).strip()
    return Hit(value, first, vend) if value else None


def _pattern_after(ctx: Ctx, pos: int, opts: dict, pattern: str, case: bool) -> Hit | None:
    lim = min(ctx.end, pos + int(opts.get("max_chars", 120)))
    m = value_pattern(pattern, case).search(ctx.text, pos, lim)
    if not m:
        return None
    g = "v" if "v" in m.re.groupindex else 0
    return Hit(m.group(g), m.start(g), m.end(g))


@register_extractor(
    "label",
    primary="labels",
    options=("max_chars", "value", "case", "multiline", "stop", "max_lines", "line_start"),
)
def ex_label(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Wartość po etykiecie (kolejność etykiet = priorytet). ``:``/kropki prowadzące pomijane.

    Gdy pole ma typ ze wzorcem (amount/date/iban/...) albo podano ``value``, szukany jest wzorzec
    w oknie ``max_chars`` po etykiecie (także w następnych liniach). Inaczej: reszta linii albo
    następna niepusta linia; ``multiline`` dokleja kolejne linie do pustej linii lub linii
    zaczynającej się od frazy z ``stop`` (max ``max_lines``).
    """
    pattern, case = ctx.type_pattern(opts)
    line_start = bool(opts.get("line_start"))
    for lab in _as_list(opts.get("labels")):
        for m in phrase_pattern(lab, line_start).finditer(ctx.folded, ctx.start, ctx.end):
            hit = (
                _pattern_after(ctx, m.end(), opts, pattern, case)
                if pattern
                else _line_value(ctx, m.end(), opts)
            )
            if hit:
                hit.anchor = m.start()
                yield hit


@register_extractor("regex", primary="pattern", options=("nth", "case", "fold"))
def ex_regex(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Regex na tekście (grupa nazwana ``v`` = wartość); ``nth`` (od 1) - tylko n-te trafienie;
    ``case: true`` - wielkość liter ma znaczenie; ``fold: true`` - szukaj w tekście złożonym."""
    if opts.get("fold"):
        rx = re.compile(opts["pattern"], re.MULTILINE)
        hay = ctx.folded
    else:
        rx = value_pattern(opts["pattern"], bool(opts.get("case")))
        hay = ctx.text
    nth = opts.get("nth")
    for i, m in enumerate(rx.finditer(hay, ctx.start, ctx.end), start=1):
        if nth is not None and i != int(nth):
            continue
        g = "v" if "v" in rx.groupindex else 0
        if m.group(g) is not None:
            yield Hit(ctx.text[m.start(g) : m.end(g)], m.start(g), m.end(g), anchor=m.start())
        if nth is not None:
            return


@register_extractor("section_line", primary="header", options=("n", "line_start"))
def ex_section_line(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """``n``-ta niepusta linia po linii nagłówka (``n: 0`` = sama linia nagłówka; domyślnie 1)."""
    n = int(opts.get("n", 1))
    for h in _as_list(opts.get("header")):
        for m in phrase_pattern(h, bool(opts.get("line_start"))).finditer(ctx.folded, ctx.start, ctx.end):
            ls, le = ctx.line_bounds(m.start())
            ls, le = max(ls, ctx.start), min(le, ctx.end)
            k = 0
            while k < n and le < ctx.end:
                ls = le + 1
                le = min(ctx.line_bounds(ls)[1], ctx.end)
                if ctx.text[ls:le].strip():
                    k += 1
            line = ctx.text[ls:le] if k == n else ""
            if line.strip():
                off = ls + (len(line) - len(line.lstrip()))
                yield Hit(line.strip(), off, off + len(line.strip()), anchor=m.start())


@register_extractor("near", primary="phrases", options=("max_chars", "direction", "value", "case"))
def ex_near(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Wartość typu pola (albo ``value``) najbliżej frazy, w oknie ``max_chars`` (domyślnie 200);
    ``direction``: ``after`` | ``before`` | ``both`` (domyślnie)."""
    pattern, case = ctx.type_pattern(opts)
    if not pattern:
        return
    rx = value_pattern(pattern, case)
    win = int(opts.get("max_chars", 200))
    direction = opts.get("direction", "both")
    for ph in _as_list(opts.get("phrases")):
        for m in phrase_pattern(ph).finditer(ctx.folded, ctx.start, ctx.end):
            cands: list[tuple[int, re.Match]] = []
            if direction in ("after", "both"):
                for v in rx.finditer(ctx.text, m.end(), min(ctx.end, m.end() + win)):
                    cands.append((v.start() - m.end(), v))
            if direction in ("before", "both"):
                for v in rx.finditer(ctx.text, max(ctx.start, m.start() - win), m.start()):
                    cands.append((m.start() - v.end(), v))
            for _, v in sorted(cands, key=lambda c: c[0]):
                g = "v" if "v" in rx.groupindex else 0
                yield Hit(v.group(g), v.start(g), v.end(g), anchor=min(m.start(), v.start()))


@register_extractor("const", primary="value")
def ex_const(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Stała wartość (bez pozycji w tekście)."""
    yield Hit(opts.get("value"))


@register_extractor("if_match", primary="phrases", options=("then",))
def ex_if_match(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Stała ``then``, gdy w zakresie występuje któraś z fraz (``re:`` = regex na tekście złożonym);
    pozycja trafienia trafia do trace.

    Np. typ osoby: ``{if_match: {phrases: [ceidg], then: osoba_fizyczna}}``.
    """
    for ph in _as_list(opts.get("phrases")):
        m = phrase_pattern(ph).search(ctx.folded, ctx.start, ctx.end)
        if m:
            yield Hit(opts.get("then"), m.start(), m.end())
            return


@register_extractor("flag", primary="phrases", options=("value",))
def ex_flag(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Wartość ``value`` (domyślnie 1), gdy w zakresie występuje któraś z fraz (np. „reprezentowany przez”).

    Typowo z ``- const: 0`` jako drugim wpisem (brak frazy = 0)."""
    value = opts.get("value", 1)
    for ph in _as_list(opts.get("phrases")):
        m = phrase_pattern(ph).search(ctx.folded, ctx.start, ctx.end)
        if m:
            yield Hit(value, m.start(), m.end())
            return


def _window(ctx: Ctx, opts: dict) -> tuple[int, int] | None:
    """Okno w zakresie ``ctx``: od końca najwcześniejszej frazy ``after`` do ``before`` / ``max_chars``.

    Brak frazy ``after`` = brak okna (``None``); brak ``before`` = do końca zakresu.
    """
    start, end = ctx.start, ctx.end
    if opts.get("after"):
        ms = [m for p in _as_list(opts["after"]) if (m := phrase_pattern(p).search(ctx.folded, start, end))]
        if not ms:
            return None
        start = min(ms, key=lambda m: m.start()).end()
    if opts.get("before"):
        ms = [m for p in _as_list(opts["before"]) if (m := phrase_pattern(p).search(ctx.folded, start, end))]
        if ms:
            end = min(m.start() for m in ms)
    if opts.get("max_chars"):
        end = min(end, start + int(opts["max_chars"]))
    return (start, end) if start < end else None


def _within(ctx: Ctx, spec: Any) -> Ctx | None:
    """Opcja ``within`` ekstraktora: okno (mapa) albo lista okien zawężanych kolejno; ``None`` = brak okna."""
    cur = ctx
    for w in _as_list(spec):
        win = _window(cur, w)
        if win is None:
            return None
        cur = Ctx(ctx.doc, ctx.text, ctx.folded, win[0], win[1], ctx.field_type, ctx.config_dir)
    return cur


@register_extractor("phrase_lookup", primary="lookup")
def ex_phrase_lookup(ctx: Ctx, opts: dict) -> Iterator[Hit]:
    """Klasyfikacja fragmentu słownikiem fraz z ``config/lookups/<lookup>.yaml``.

    Słownik to lista ``{id: <wartość>, phrases: [...]}``; **kolejność wpisów = priorytet** (pierwszy
    wpis, którego fraza występuje w zakresie, wygrywa - niezależnie od pozycji frazy). Zakres zawęża się
    wspólną opcją ``within`` (kilka wpisów może szukać w różnych miejscach, np. zdanie o czynności,
    a potem pierwszy zarzut).
    """
    for entry in _phrase_table(opts["lookup"], ctx.config_dir):
        for p in entry[1]:
            m = p.search(ctx.folded, ctx.start, ctx.end)
            if m:
                yield Hit(entry[0], m.start(), m.end())
                return


_PHRASE_TABLES: dict[tuple[str, str], list[tuple[Any, list[re.Pattern]]]] = {}


def _phrase_table(name: str, config_dir: Any) -> list[tuple[Any, list[re.Pattern]]]:
    key = (name, str(config_dir))
    if key not in _PHRASE_TABLES:
        raw = load_lookup(name, config_dir) if config_dir is not None else load_lookup(name)
        if not isinstance(raw, list):
            raise ValueError(f"lookup {name!r}: phrase_lookup wymaga listy wpisów {{id, phrases}}")
        table = []
        for i, e in enumerate(raw):
            if not isinstance(e, dict) or "id" not in e or not e.get("phrases"):
                raise ValueError(f"lookup {name!r}[{i}]: wpis musi mieć 'id' i niepuste 'phrases'")
            for p in _as_list(e["phrases"]):
                check_phrase(p)
            table.append((e["id"], [phrase_pattern(p) for p in _as_list(e["phrases"])]))
        _PHRASE_TABLES[key] = table
    return _PHRASE_TABLES[key]


# ============================================================== normalizatory lokalne
# Minimalne wersje za interfejsem ``fn(value: str) -> Any | None``; jeśli istnieje moduł
# ``odw2json.extract.normalize`` (T2) / ``odw2json.extract.names`` (T3), ich funkcje je nadpisują.


_WS = re.compile(r"\s+")
_MONTH_NUM = {
    "stycz": 1,
    "lut": 2,
    "mar": 3,
    "kwie": 4,
    "maj": 5,
    "czerw": 6,
    "lip": 7,
    "sierp": 8,
    "wrze": 9,
    "pazdz": 10,
    "listop": 11,
    "grud": 12,
}


@register_normalizer("ws")
def n_ws(value: str) -> str | None:
    out = _WS.sub(" ", str(value)).strip()
    return out or None


@register_normalizer("date")
def n_date(value: str) -> str | None:
    s = fold(_WS.sub(" ", str(value)).strip())
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            y, mo, d = map(int, m.groups())
        elif m := re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", s):
            d, mo, y = map(int, m.groups())
        elif m := re.fullmatch(r"(\d{1,2}) ([a-z]+) (\d{4})(?: ?r\.?)?", s):
            word = m.group(2)
            mo = next((v for k, v in _MONTH_NUM.items() if word.startswith(k)), 0)
            d, y = int(m.group(1)), int(m.group(3))
        else:
            return None
        return _dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


@register_normalizer("amount")
def n_amount(value: str) -> float | None:
    s = re.sub(r"(?i)\s*(pln|zł|zl)\.?", "", str(value))
    s = re.sub(r"\s", "", s)  # \s obejmuje też twardą spację
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return round(float(s), 2) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


@register_normalizer("iban")
def n_iban(value: str) -> str | None:
    s = re.sub(r"[\s\-]", "", str(value))
    if s[:2].upper() == "PL":
        s = s[2:]
    return s if re.fullmatch(r"\d{26}", s) else None


@register_normalizer("digits")
def n_digits(value: str) -> str | None:
    return re.sub(r"\D", "", str(value)) or None


@register_normalizer("int")
def n_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    s = re.sub(r"\D", "", str(value))
    return int(s) if s else None


@register_normalizer("email")
def n_email(value: str) -> str | None:
    m = re.search(EMAIL_PATTERN, str(value))
    return m.group(0).lower() if m else None


@register_normalizer("company")
def n_company(value: str) -> str | None:
    return n_ws(value)


@register_normalizer("name")
def n_name(value: str) -> str | None:
    return n_ws(value)


@register_normalizer("trim_quotes")
def n_trim_quotes(value: str) -> str | None:
    """Zdejmuje otaczające cudzysłowy i końcową kropkę/przecinek (np. ``"tytuł".`` -> ``tytuł``)."""
    s = str(value).strip().rstrip(".,;").strip()
    pairs = [('"', '"'), ("„", "”"), ("„", '"'), ("“", "”"), ("'", "'"), ("«", "»")]
    for a, b in pairs:
        if len(s) >= 2 and s.startswith(a) and s.endswith(b):
            s = s[len(a) : -len(b)].strip()
            break
    return s or None


@register_normalizer("upper")
def n_upper(value: str) -> str | None:
    return str(value).upper() or None


@register_normalizer("lower")
def n_lower(value: str) -> str | None:
    return str(value).lower() or None


_OCR_DIGIT_TOKEN = re.compile(r"(?<![A-Za-z])[0-9oO]*[0-9][0-9oO]*(?![A-Za-z])|(?<![A-Za-z])[oO]+(?=[0-9])")


@register_normalizer("ocr_digits")
def n_ocr_digits(value: str) -> str | None:
    """OCR: litera ``o``/``O`` w ciągu cyfr -> ``0`` (``2026/BZP o0692455`` -> ``2026/BZP 00692455``)."""
    s = str(value)
    return _OCR_DIGIT_TOKEN.sub(lambda m: m.group(0).replace("o", "0").replace("O", "0"), s) or None


def _load_external_normalizers() -> None:
    """Funkcje z ``normalize.py`` (T2) i ``names.py`` (T3) nadpisują lokalne o tej samej nazwie."""
    try:
        from odw2json.extract import normalize as ext  # type: ignore[attr-defined]
    except ImportError:
        ext = None
    if ext is not None:
        table = getattr(ext, "NORMALIZERS", None)
        if isinstance(table, dict):
            NORMALIZERS.update({k: v for k, v in table.items() if callable(v)})
        for name in ("date", "amount", "iban", "digits", "bzp", "ted", "email", "ws", "ocr_fix", "company"):
            fn = getattr(ext, name, None)
            if callable(fn):
                NORMALIZERS[name] = fn
    try:
        from odw2json.extract.names import normalize_name  # type: ignore[import-not-found]
    except ImportError:
        return
    NORMALIZERS["name"] = NORMALIZERS["name_nominative"] = lambda v: normalize_name(n_ws(v) or "") or None


_load_external_normalizers()


# ============================================================== walidatory


@register_validator("regex")
def v_regex(value: Any, arg: str) -> bool:
    return re.search(arg, str(value)) is not None


@register_validator("min_len")
def v_min_len(value: Any, arg: int) -> bool:
    return len(str(value)) >= int(arg)


@register_validator("max_len")
def v_max_len(value: Any, arg: int) -> bool:
    return len(str(value)) <= int(arg)


@register_validator("min")
def v_min(value: Any, arg: float) -> bool:
    return isinstance(value, (int, float)) and value >= arg


@register_validator("max")
def v_max(value: Any, arg: float) -> bool:
    return isinstance(value, (int, float)) and value <= arg


@register_validator("one_of")
def v_one_of(value: Any, arg: list) -> bool:
    return value in arg


# ============================================================== ścieżki w danych


def get_path(data: Any, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def set_path(data: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value


def template_has_path(template: Any, path: str) -> bool:
    """Czy ścieżka DSL (``a.b``, ``L[].x``) istnieje w szablonie (listy: pierwszy element)."""
    cur = template
    for part in path.split("."):
        is_list = part.endswith(LIST_MARK)
        key = part[: -len(LIST_MARK)] if is_list else part
        if not isinstance(cur, dict) or key not in cur:
            return False
        cur = cur[key]
        if is_list:
            if not isinstance(cur, list) or not cur:
                return False
            cur = cur[0]
    return True


# ============================================================== silnik


def _scope(ctx: Ctx, scope: Any) -> tuple[int, int] | None:
    if scope is None:
        return ctx.start, ctx.end
    start, end = ctx.start, ctx.end
    if scope.after:
        ms = [m for p in _as_list(scope.after) if (m := phrase_pattern(p).search(ctx.folded, start, end))]
        if not ms:
            return None
        start = min(ms, key=lambda m: m.start()).end()
    if scope.before:
        ms = [m for p in _as_list(scope.before) if (m := phrase_pattern(p).search(ctx.folded, start, end))]
        if ms:
            end = min(m.start() for m in ms)
    if scope.max_chars:
        end = min(end, start + scope.max_chars)
    return (start, end) if start < end else None


def _snippet(ctx: Ctx, hit: Hit) -> str | None:
    if hit.start < 0:
        return None
    a = hit.start if hit.anchor is None else min(hit.anchor, hit.start)
    ls = ctx.text.rfind("\n", 0, a) + 1
    le = ctx.text.find("\n", max(hit.end, a))
    le = len(ctx.text) if le < 0 else le
    s = ctx.text[ls:le].strip()
    return s[:SNIPPET_MAX] if s else None


def _normalize(value: Any, chain: list[str]) -> Any:
    for name in chain:
        if value is None:
            return None
        if not isinstance(value, str) and name != "int":
            continue  # stałe nie-tekstowe (const) przechodzą bez normalizacji tekstu
        value = NORMALIZERS[name](value)
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _valid(value: Any, rules: dict) -> bool:
    return all(VALIDATORS[k](value, arg) for k, arg in rules.items())


def extract_field(ctx: Ctx, path: str, spec: FieldSpec) -> FieldResult | None:
    """Pierwszy kandydat, który przeszedł normalize + validate; inaczej ``None``."""
    region = _scope(ctx, spec.scope)
    if region is None:
        return None
    sub = Ctx(ctx.doc, ctx.text, ctx.folded, region[0], region[1], spec.type, ctx.config_dir)
    chain = spec.normalize if spec.normalize is not None else list(TYPES[spec.type].normalize)
    for entry in spec.extract:
        name, opts = parse_extractor_entry(entry)
        local = _within(sub, opts[WITHIN]) if WITHIN in opts else sub
        if local is None:
            continue
        for hit in EXTRACTORS[name].fn(local, opts):
            value = _normalize(hit.value, chain)
            if value is None or not _valid(value, spec.validate_):
                continue
            page = ctx.doc.page_of(hit.start) if hit.start >= 0 else None
            return FieldResult(
                path=path, value=value, method=name, source_snippet=_snippet(ctx, hit), page=page
            )
    return None


def _split_region(ctx: Ctx, region: tuple[int, int], sp: Any) -> list[tuple[int, int]]:
    """Blok ``start``..``end`` w ``region`` podzielony na elementy (``item_sep`` / ``item_regex``)."""
    s, e = region
    if sp.start:
        m = phrase_pattern(sp.start).search(ctx.folded, s, e)
        if not m:
            return []
        s = m.start()
        search_from = m.end()
    else:
        search_from = s
    if sp.end:
        m = phrase_pattern(sp.end).search(ctx.folded, search_from, e)
        if m:
            e = m.start()
    if sp.item_sep:
        starts = [m.start() for m in phrase_pattern(sp.item_sep).finditer(ctx.folded, s, e)]
    elif getattr(sp, "item_regex", None):
        starts = [m.start() for m in value_pattern(sp.item_regex, True).finditer(ctx.text, s, e)]
    else:
        return [(s, e)]
    return [(a, b) for a, b in zip(starts, starts[1:] + [e], strict=True)] if starts else [(s, e)]


def _split_items(ctx: Ctx, region: tuple[int, int], spec: Any) -> list[tuple[int, int]]:
    items = [region] if spec is None or spec.split is None else _split_region(ctx, region, spec.split)
    if spec is not None and spec.max_items:
        items = items[: spec.max_items]
    return items


def _group_region(ctx: Ctx, spec: Any, index: int | None) -> tuple[int, int] | None:
    """``groups``: ``index``-ty blok całego dokumentu (``None`` = brak bloków, zostaje fragment rodzica)."""
    if spec is None or getattr(spec, "groups", None) is None or index is None:
        return None
    groups = _split_region(ctx, (0, len(ctx.text)), spec.groups)
    return groups[index] if index < len(groups) else None


def _is_empty(v: Any) -> bool:
    if isinstance(v, dict):
        return all(_is_empty(x) for x in v.values())
    if isinstance(v, list):
        return all(_is_empty(x) for x in v)
    return v is None


def _fill(
    obj: dict,
    prefix: str,
    concrete: str,
    region: tuple[int, int],
    ctx: Ctx,
    cfg: DocTypeConfig,
    trace: list,
    index: int | None = None,
) -> None:
    """Wypełnia ``obj`` polami o prefiksie ``prefix`` (DSL) w zakresie ``region``; listy rekurencyjnie.

    ``concrete`` - ten sam prefiks z konkretnymi indeksami (``Odwolujacy[0].``) do trace;
    ``index`` - indeks ``obj`` w liście nadrzędnej (dla ``groups``).
    """
    local = Ctx(ctx.doc, ctx.text, ctx.folded, region[0], region[1], config_dir=ctx.config_dir)
    lists: list[str] = []
    derived: list[tuple[str, Any]] = []
    for path, spec in cfg.fields.items():
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix) :]
        if LIST_MARK in rest:
            name = rest.split(LIST_MARK, 1)[0]
            if name not in lists:
                lists.append(name)
            continue
        if spec.derived is not None:
            derived.append((rest, spec))
            continue
        fr = extract_field(local, concrete + rest, spec)
        if fr is not None:
            set_path(obj, rest, fr.value)
            trace.append(fr)
    for name in lists:
        proto_list = get_path(obj, name)
        proto = proto_list[0] if isinstance(proto_list, list) and proto_list else {}
        lspec = cfg.lists.get(prefix + name)
        lregion = _group_region(ctx, lspec, index) or region
        unique = bool(lspec is not None and lspec.unique)
        items: list = []
        for r in _split_items(local, lregion, lspec):
            i = len(items)
            item = copy.deepcopy(proto)
            item_trace: list = []
            _fill(item, f"{prefix}{name}{LIST_MARK}.", f"{concrete}{name}[{i}].", r, ctx, cfg, item_trace, i)
            if unique and (_is_empty(item) or item in items):
                continue
            items.append(item)
            trace.extend(item_trace)
        set_path(obj, name, items or [copy.deepcopy(proto)])
    for rest, spec in derived:
        trace.append(_apply_derived_one(obj, rest, concrete + rest, spec, cfg, prefix, trace))


def _apply_derived_one(
    obj: dict, rest: str, tpath: str, spec: FieldSpec, cfg: DocTypeConfig, prefix: str, trace: list
) -> FieldResult:
    d = spec.derived
    src = d.from_[len(prefix) :] if prefix and d.from_.startswith(prefix) else d.from_
    key = get_path(obj, src)
    if d.lookup:
        value = load_lookup(d.lookup, cfg.config_dir).get(key) if key is not None else None
    else:
        value = key
    set_path(obj, rest, value)
    origin = next((t for t in reversed(trace) if t.path.endswith(src)), None)
    return FieldResult(
        path=tpath,
        value=value,
        method="derived",
        source_snippet=origin.source_snippet if origin and value is not None else None,
        page=origin.page if origin and value is not None else None,
    )


def apply_derived(data: dict, cfg: DocTypeConfig) -> list[FieldResult]:
    """Tylko pola ``derived`` najwyższego poziomu (np. ``czynnosc_opis`` = lookup[``czynnosc_powod_id``])."""
    trace: list[FieldResult] = []
    for path, spec in cfg.fields.items():
        if spec.derived is not None and LIST_MARK not in path:
            trace.append(_apply_derived_one(data, path, path, spec, cfg, "", trace))
    return trace


def extract(doc: Document, cfg: DocTypeConfig) -> ExtractionResult:
    """Wynik DOKŁADNIE w kształcie szablonu ``cfg.template()``; pola bez wyniku = ``null``."""
    data = cfg.template()
    text = doc.text or ""
    ctx = Ctx(doc, text, fold(text), 0, len(text), config_dir=cfg.config_dir)
    trace: list[FieldResult] = []
    _fill(data, "", "", (0, len(text)), ctx, cfg, trace)
    return ExtractionResult(doc_type=cfg.id, data=data, trace=trace)
