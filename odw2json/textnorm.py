"""Wspólne funkcje normalizacji tekstu."""

from __future__ import annotations

import re
import unicodedata

_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def fold(text: str) -> str:
    """Małe litery, bez polskich znaków i akcentów, zwinięte białe znaki (do dopasowań)."""
    t = unicodedata.normalize("NFKC", text).translate(_PL)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t).strip().lower()
