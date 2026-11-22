"""Czyste normalizatory wartości pól (bez I/O, bez sieci).

Każdy normalizator ma sygnaturę ``fn(value: str) -> wynik | None``.
``None`` oznacza, że wartości nie da się znormalizować (pole zostanie puste).
Rejestr ``NORMALIZERS`` mapuje nazwy z konfiguracji YAML na funkcje.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from collections.abc import Callable
from typing import Any

# --- wspólne --------------------------------------------------------------

_BIALE_ZNAKI = re.compile(r"\s+")

# Miesiące w dopełniaczu (np. „11 września 2026”), bez polskich znaków.
_MIESIACE = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "wrzesnia": 9,
    "pazdziernika": 10,
    "listopada": 11,
    "grudnia": 12,
}


def _bez_znakow_diakrytycznych(tekst: str) -> str:
    rozlozony = unicodedata.normalize("NFKD", tekst)
    return "".join(c for c in rozlozony if not unicodedata.combining(c))


def _wyczysc_biale(tekst: str) -> str:
    """Zamienia wszystkie białe znaki (także twarde spacje) na zwykłe i zwija je."""
    return _BIALE_ZNAKI.sub(" ", tekst).strip()


def _tylko_cyfry(tekst: str) -> str:
    return "".join(c for c in tekst if c.isdigit())


# --- date -----------------------------------------------------------------

# DD.MM.RRRR, DD-MM-RRRR, DD/MM/RRRR; ten sam separator w obu miejscach (\2).
# separator spacja: OCR gubi kropki („20 04 2026”); ten sam separator w obu miejscach
_DATA_DMY = re.compile(r"^(\d{1,2})([./\- ])(\d{1,2})\2(\d{4})$")
_DATA_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DATA_SLOWNIE = re.compile(r"^(\d{1,2})\s+([^\W\d_]+)\s+(\d{4})$")
_SUFIKS_R = re.compile(r"\s*(r\.|r|roku)$", re.IGNORECASE)


def _zbuduj_date(rok: str, miesiac: int, dzien: int) -> str | None:
    try:
        return _dt.date(int(rok), miesiac, dzien).isoformat()
    except ValueError:
        return None


def date(value: str) -> str | None:
    """Data z dokumentu → ISO ``RRRR-MM-DD``; nieprawidłowa data → None."""
    tekst = _wyczysc_biale(value)
    tekst = _SUFIKS_R.sub("", tekst).strip()
    tekst = re.sub(r"^dnia\s+", "", tekst, flags=re.IGNORECASE)
    if not tekst:
        return None

    if m := _DATA_DMY.match(tekst):
        dzien, _sep, miesiac, rok = m.groups()
        return _zbuduj_date(rok, int(miesiac), int(dzien))

    if m := _DATA_ISO.match(tekst):
        rok, miesiac, dzien = m.groups()
        return _zbuduj_date(rok, int(miesiac), int(dzien))

    if m := _DATA_SLOWNIE.match(tekst):
        dzien, nazwa, rok = m.groups()
        numer = _MIESIACE.get(_bez_znakow_diakrytycznych(nazwa).lower())
        if numer is None:
            return None
        return _zbuduj_date(rok, numer, int(dzien))

    return None


# --- kwoty ----------------------------------------------------------------

_WALUTA = re.compile(r"^\s*(?:pln|zł|zl)\.?\s*|\s*(?:zł|zl|pln)\.?$", re.IGNORECASE)
_TYSIACE_KROPKA = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_KWOTA = re.compile(r"^-?\d+(\.\d+)?$")


def amount(value: str) -> float | None:
    """Kwota → float. Spacje (także twarde) to separatory tysięcy; przecinek to dziesiętny."""
    tekst = _WALUTA.sub("", value.strip()).strip()
    tekst = re.sub(r"\s", "", tekst)
    if "," in tekst:
        tekst = tekst.replace(".", "").replace(",", ".")
    elif _TYSIACE_KROPKA.match(tekst):  # 10.000 -> kropka jako separator tysięcy
        tekst = tekst.replace(".", "")
    if not _KWOTA.match(tekst):
        return None
    return float(tekst)


# --- IBAN -----------------------------------------------------------------

_SEPARATORY = re.compile(r"[\s\-]")


def iban(value: str) -> str | None:
    """Rachunek jak w dokumencie: „PL” + 26 cyfr (gdy prefiks jest) albo 26 cyfr; bez separatorów."""
    tekst = _SEPARATORY.sub("", value)
    prefiks = ""
    if tekst.startswith("PL"):
        prefiks, tekst = "PL", tekst[2:]
    if re.fullmatch(r"\d{26}", tekst):
        return prefiks + tekst
    return None


# --- numery identyfikacyjne -----------------------------------------------


def digits(value: str) -> str | None:
    """Same cyfry; brak cyfr → None."""
    wynik = _tylko_cyfry(value)
    return wynik or None


def _cyfry_o_dlugosci(value: str, dlugosci: tuple[int, ...]) -> str | None:
    wynik = _tylko_cyfry(value)
    if len(wynik) in dlugosci:
        return wynik
    return None


def nip(value: str) -> str | None:
    """NIP: dokładnie 10 cyfr (bez walidacji sumy kontrolnej)."""
    return _cyfry_o_dlugosci(value, (10,))


def krs(value: str) -> str | None:
    """KRS: 1–10 cyfr, uzupełniane zerami wiodącymi do 10."""
    wynik = _tylko_cyfry(value)
    if not 1 <= len(wynik) <= 10:
        return None
    return wynik.zfill(10)


def regon(value: str) -> str | None:
    """REGON: 9 albo 14 cyfr (bez walidacji sumy kontrolnej)."""
    return _cyfry_o_dlugosci(value, (9, 14))


def pesel(value: str) -> str | None:
    """PESEL: 11 cyfr jako string (zera wiodące zachowane; bez walidacji sumy kontrolnej)."""
    return _cyfry_o_dlugosci(value, (11,))


# --- BZP / TED ------------------------------------------------------------

_BZP = re.compile(
    r"^(\d{4})\s*/\s*BZP\s*(\d{8})(?:\s*/\s*(\d{2}))?$",
    re.IGNORECASE,
)


def bzp(value: str) -> str | None:
    """Numer BZP → ``RRRR/BZP########`` (opcjonalnie ``/NN``), bez spacji."""
    m = _BZP.match(value.strip())
    if m is None:
        return None
    rok, numer, czesc = m.groups()
    wynik = f"{rok}/BZP{numer}"
    if czesc is not None:
        wynik += f"/{czesc}"
    return wynik


_TED_NUMER_ROK = re.compile(r"^(\d{6})-(\d{4})$")
_TED_ROK_S = re.compile(r"^(\d{4})\s*/\s*S\s*\d{1,3}\s*-\s*(\d{6})$", re.IGNORECASE)
_TED_ROK_OJS = re.compile(r"^(\d{4})\s*-\s*OJS\s*\d{1,3}\s*-\s*(\d{6})$", re.IGNORECASE)


def ted(value: str) -> str | None:
    """Numer TED → ``NNNNNN-RRRR``. Obsługuje ``RRRR/S NNN-NNNNNN`` i ``RRRR-OJS NNN-NNNNNN``."""
    tekst = value.strip()
    if m := _TED_NUMER_ROK.match(tekst):
        numer, rok = m.groups()
        return f"{numer}-{rok}"
    if m := _TED_ROK_S.match(tekst):
        rok, numer = m.groups()
        return f"{numer}-{rok}"
    if m := _TED_ROK_OJS.match(tekst):
        rok, numer = m.groups()
        return f"{numer}-{rok}"
    return None


# --- e-mail / tekst -------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def email(value: str) -> str | None:
    """Wyłuskuje pierwszy adres e-mail i zapisuje go małymi literami."""
    m = _EMAIL.search(value)
    if m is None:
        return None
    return m.group(0).lower()


def ws(value: str) -> str | None:
    """Zwija białe znaki do pojedynczych spacji i przycina; pusty wynik → None."""
    wynik = _wyczysc_biale(value)
    return wynik or None


# --- formy prawne / OCR ---------------------------------------------------

# „Sp. z o.o.” z typowymi błędami OCR: 0 zamiast o, brak spacji, brak kropek.
_SP_Z_O_O = re.compile(
    r"\b([Ss])p\.\s*z\s*[oO0]\s*\.\s*[oO0]\s*\.?",
)
# „S.A” bez kropki na końcu (nie rusza już poprawnego „S.A.”).
_S_A = re.compile(r"(?<![A-Za-z])S\.\s?A(?![A-Za-z.])")


def ocr_fix(value: str) -> str | None:
    """Poprawia typowe błędy OCR w formach prawnych; inne zera pozostają bez zmian."""
    if not value.strip():
        return None
    wynik = _SP_Z_O_O.sub(lambda m: f"{m.group(1)}p. z o.o.", value)
    wynik = _S_A.sub("S.A.", wynik)
    return wynik


_PARY_CUDZYSLOWOW = (
    ('"', '"'),
    ("'", "'"),
    ("„", "”"),
    ("„", '"'),
    ("“", "”"),
    ("«", "»"),
)


def _usun_cudzyslowy(tekst: str) -> str:
    for otwierajacy, zamykajacy in _PARY_CUDZYSLOWOW:
        if len(tekst) >= 2 and tekst.startswith(otwierajacy) and tekst.endswith(zamykajacy):
            return tekst[len(otwierajacy) : -len(zamykajacy)].strip()
    return tekst


def company(value: str) -> str | None:
    """Nazwa firmy: białe znaki, OCR-fix form prawnych, bez otaczających cudzysłowów.

    Skróty nie są rozwijane.
    """
    wynik = ws(value)
    if wynik is None:
        return None
    wynik = ocr_fix(wynik) or wynik
    wynik = _usun_cudzyslowy(wynik)
    return wynik or None


NORMALIZERS: dict[str, Callable[[str], Any]] = {
    "date": date,
    "amount": amount,
    "iban": iban,
    "digits": digits,
    "nip": nip,
    "krs": krs,
    "regon": regon,
    "pesel": pesel,
    "bzp": bzp,
    "ted": ted,
    "email": email,
    "ws": ws,
    "ocr_fix": ocr_fix,
    "company": company,
}
