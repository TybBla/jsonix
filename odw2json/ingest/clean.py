"""Czyszczenie tekstu wyciagnietego z PDF: rejestr czystych funkcji ``str -> str``.

Kazdy krok jest idempotentny i nigdy nie zmienia cyfr ani polskich liter.
Kolejnosc uruchamiania ustala wywolujacy (konfiguracja); zalecana: ``DEFAULT_ORDER``.
Znak ``\\f`` jest twarda granica stron i nie jest usuwany przez zaden krok.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from collections.abc import Callable

# Spacje "specjalne": NBSP, figure space, thin space, narrow NBSP itd.
_SPECIAL_SPACES = dict.fromkeys(
    map(
        ord,
        "               　",
    ),
    " ",
)
_LIGATURES = {
    ord("ﬀ"): "ff",
    ord("ﬁ"): "fi",
    ord("ﬂ"): "fl",
    ord("ﬃ"): "ffi",
    ord("ﬄ"): "ffl",
    ord("ﬅ"): "st",
    ord("ﬆ"): "st",
}
_QUOTES = {
    **dict.fromkeys(map(ord, "„“”‟«»"), '"'),
    **dict.fromkeys(map(ord, "‚‘’‛"), "'"),
}
# Artefakty OCR: znaki, ktorych polszczyzna nie uzywa, a ktore silnik "multi" podstawia za polskie litery
# lub za litery lacinskie z bledna diakrytyka (obserwacje: docs/decyzje/E2b-ocr-wydajnosc.md).
# Celowo pominiete: ä/ë/ö/ü (czeste w nazwiskach obcych) i wszystko, co jest polska litera.
_OCR_ARTIFACTS = {
    **dict.fromkeys(map(ord, "ı"), "i"),
    **dict.fromkeys(map(ord, "ſ"), "s"),
    **dict.fromkeys(map(ord, "ñň"), "ń"),
    **dict.fromkeys(map(ord, "ÑŇ"), "Ń"),
    ord("ő"): "ó",
    ord("Ő"): "Ó",
    ord("š"): "ś",
    ord("Š"): "Ś",
    ord("č"): "ć",
    ord("Č"): "Ć",
    ord("ž"): "ż",
    ord("Ž"): "Ż",
    ord("ě"): "ę",
    ord("Ě"): "Ę",
    **dict.fromkeys(map(ord, "àáâãåāă"), "a"),
    **dict.fromkeys(map(ord, "ÀÁÂÃÅĀĂ"), "A"),
    **dict.fromkeys(map(ord, "ċç"), "c"),
    **dict.fromkeys(map(ord, "ĊÇ"), "C"),
    ord("ņ"): "n",
    ord("Ņ"): "N",
    ord("ș"): "s",
    ord("Ș"): "S",
    **dict.fromkeys(map(ord, "èêēĕė"), "e"),
    **dict.fromkeys(map(ord, "ÈÊĒĔĖ"), "E"),
    **dict.fromkeys(map(ord, "ìíîïī"), "i"),
    **dict.fromkeys(map(ord, "ÌÍÎÏĪ"), "I"),
    **dict.fromkeys(map(ord, "òôõō"), "o"),
    **dict.fromkeys(map(ord, "ÒÔÕŌ"), "O"),
    **dict.fromkeys(map(ord, "ùúûūůűų"), "u"),
    **dict.fromkeys(map(ord, "ÙÚÛŪŮŰŲ"), "U"),
    **dict.fromkeys(map(ord, "ýÿ"), "y"),
    **dict.fromkeys(map(ord, "ÝŸ"), "Y"),
}
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")

# litera, myslnik, koniec wiersza, mala litera (wielka po lewej/prawej = nie ruszamy)
_DEHYPHEN_RE = re.compile(r"(?<=[^\W\d_])-[ \t]*\n(?=[^\W\d_A-ZĄĆĘŁŃÓŚŹŻ])")
_PAGE_FOOTER_RE = re.compile(r"^[ \t]*Strona[ \t]+\d+[ \t]+z[ \t]+\d+[ \t]*(?:\n|$)", re.I | re.M)

_SENTENCE_END = (".", ":", ";", "!", "?")
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-•*▪●]|\(?[0-9a-zA-Z]{1,3}[.)])(?:\s|\.|$)")
_LOWER_LABEL_RE = re.compile(r"^[^\W\d_][^\W\d_ ]*(?: [^\W\d_][^\W\d_]*){0,3}:")
_LABEL_VALUE_END_RE = re.compile(r":[ \t]*[\d\s\-./]*\d[\d\s\-./]*$")
_MIN_WRAPPED_LEN = 40


def unicode_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def nbsp_to_space(text: str) -> str:
    return text.translate(_SPECIAL_SPACES)


def ligatures(text: str) -> str:
    return text.translate(_LIGATURES)


def ocr_artifacts(text: str) -> str:
    """Naprawia znaki, ktore OCR podstawia za polskie litery (np. ``Ñ`` za ``Ń``, ``á`` za ``a``)."""
    return text.translate(_OCR_ARTIFACTS)


def quotes(text: str) -> str:
    return text.translate(_QUOTES)


def dashes(text: str) -> str:
    return text.translate(_DASHES)


def _per_page(fn: Callable[[str], str]) -> Callable[[str], str]:
    """Krok liniowy stosowany osobno do kazdej strony: ``\\f`` jest twarda granica wiersza i strony."""

    @functools.wraps(fn)
    def wrapper(text: str) -> str:
        return "\f".join(fn(page) for page in text.split("\f"))

    return wrapper


def dehyphenate(text: str) -> str:
    """``wyra-\\nzu`` -> ``wyrazu``: litera, myslnik na koncu wiersza, mala litera."""
    return _DEHYPHEN_RE.sub("", text)


def _is_header(line: str) -> bool:
    s = line.strip()
    if s.endswith(":"):
        return True
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and len(s) <= 60 and all(c.isupper() for c in letters)


def _should_join(prev: str, nxt: str) -> bool:
    if not prev.strip() or not nxt.strip() or "\f" in prev or "\f" in nxt:
        return False
    p, n = prev.rstrip(), nxt.lstrip()
    if len(p) < _MIN_WRAPPED_LEN or p.endswith(_SENTENCE_END) or _is_header(p):
        return False
    if _LABEL_VALUE_END_RE.search(p):
        return False
    if not n[0].isalpha() or not n[0].islower():
        return False
    return not (_LIST_MARKER_RE.match(n) or _LOWER_LABEL_RE.match(n))


@_per_page
def join_wrapped_lines(text: str) -> str:
    """Skleja lamane wiersze akapitu; konserwatywnie (lepiej niedokleic).

    Decyzja zalezy tylko od (dotychczas sklejony wiersz, nastepny wiersz), wiec krok jest idempotentny.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if out and _should_join(out[-1], line):
            out[-1] = out[-1].rstrip() + " " + line.lstrip()
        else:
            out.append(line)
    return "\n".join(out)


@_per_page
def collapse_spaces(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" +$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text)


def _strip_repeated_footers(text: str) -> str:
    pages = text.split("\f")
    if len(pages) < 2:
        return text
    while True:
        split = [p.split("\n") for p in pages]
        last_idx: list[int | None] = []
        counts: dict[str, int] = {}
        for lines in split:
            idx = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
            last_idx.append(idx)
            if idx is not None and len(lines[idx].strip()) <= 80:
                key = lines[idx].strip()
                counts[key] = counts.get(key, 0) + 1
        repeated = {k for k, c in counts.items() if c >= 2}
        if not repeated:
            return "\f".join(pages)
        seen: set[str] = set()
        new_pages = []
        for lines, idx in zip(split, last_idx, strict=True):
            if idx is not None and lines[idx].strip() in repeated:
                key = lines[idx].strip()
                if key in seen:  # pierwsze wystapienie (strona 1) zostaje, powtorzenia znikaja
                    del lines[idx]
                seen.add(key)
            new_pages.append("\n".join(lines))
        pages = new_pages


def strip_page_artifacts(text: str) -> str:
    """Usuwa ``Strona X z Y`` oraz powtorzenia identycznej stopki (zostaje pierwsze; wymaga ``\\f``)."""
    text = "\f".join(_PAGE_FOOTER_RE.sub("", page) for page in text.split("\f"))
    if "\f" in text:
        text = _strip_repeated_footers(text)
    return text


CLEAN_STEPS: dict[str, Callable[[str], str]] = {
    "unicode_nfc": unicode_nfc,
    "nbsp_to_space": nbsp_to_space,
    "ligatures": ligatures,
    "ocr_artifacts": ocr_artifacts,
    "quotes": quotes,
    "dashes": dashes,
    "dehyphenate": dehyphenate,
    "join_wrapped_lines": join_wrapped_lines,
    "collapse_spaces": collapse_spaces,
    "strip_page_artifacts": strip_page_artifacts,
}

DEFAULT_ORDER: list[str] = [
    "unicode_nfc",
    "nbsp_to_space",
    "ligatures",
    "quotes",
    # "ocr_artifacts" pominiete: stosowany tylko do tekstu z OCR (config: ingest.ocr.postprocess).
    # "dashes" pominiete: UZP GT zachowuje "–" w tytulach; krok dostepny dla innych typow dokumentow.
    "strip_page_artifacts",
    "dehyphenate",
    "join_wrapped_lines",
    "collapse_spaces",
]


def clean_text(text: str, steps: list[str]) -> str:
    """Uruchamia kroki z rejestru w podanej kolejnosci; nieznany krok -> ``ValueError``."""
    unknown = [s for s in steps if s not in CLEAN_STEPS]
    if unknown:
        raise ValueError(f"Nieznane kroki czyszczenia: {unknown}. Dostepne: {sorted(CLEAN_STEPS)}")
    for name in steps:
        text = CLEAN_STEPS[name](text)
    return text
