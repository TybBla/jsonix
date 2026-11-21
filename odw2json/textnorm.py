"""Wspólne funkcje normalizacji tekstu."""

from __future__ import annotations

import re
import unicodedata

_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


_LETTER = r"[^\W\d_]"
# ciag >= 5 pojedynczych liter rozdzielonych pojedynczymi spacjami, ograniczony nie-znakami slowa
_SPACED_RUN = re.compile(rf"(?<!\w)(?:{_LETTER} ){{4,}}{_LETTER}(?!\w)")


def collapse_spaced_letters(text: str) -> str:
    """Zwija rozstrzelone litery: ``P E Ł N O M O C N I C T W O`` -> ``PEŁNOMOCNICTWO``.

    Zwijane są wyłącznie ciągi co najmniej 5 pojedynczych liter oddzielonych pojedynczymi spacjami,
    więc krótkie ciągi typu ``a i w z`` oraz cyfry (``1 2 3 4 5 6``) zostają bez zmian.
    """
    return _SPACED_RUN.sub(lambda m: m.group().replace(" ", ""), text)


def fold(text: str) -> str:
    """Małe litery, bez polskich znaków i akcentów, zwinięte białe znaki (do dopasowań)."""
    t = unicodedata.normalize("NFKC", text).translate(_PL)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().lower()
