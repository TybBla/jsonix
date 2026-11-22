"""Normalizacja polskich imion i nazwisk do mianownika (kryteria UZP §5).

`normalize_name("r. pr. Jana Kowalskiego") -> "Jan Kowalski"`.

Algorytm:
1. Usuń tytuły z początku (adw., r. pr., radca prawny, mec., Pan/Pani, dr, ...).
1a. Człon zapisany w całości WIELKIMI literami (JAN NOWAK, NOWAK-JEZIORAŃSKI, „Anna KOWALSKA”) -> postać
   tytułowa („Jan Nowak”) PRZED odmianą; dane UZP mają imiona zawsze w postaci tytułowej. Pojedyncze
   inicjały („J.”) zostają bez zmian.
2. Kolejne słowa rozpoznane w słowniku imion (`config/lookups/imiona.yaml`, formy przypadków
   generowane regułami) wyznaczają rodzaj i przypadek. Imię nieznane -> wejście bez zmian.
3. Imię w mianowniku -> całość bez zmian (także gdy rodzaj nazwiska nie zgadza się z imieniem,
   jak w danych UZP: „Klaudia Dobrowolski”).
4. Nazwisko (każdy człon osobno, także po myślniku) odmieniane wstecz regułami końcówek
   zgodnymi z przypadkiem imienia; brak pasującej reguły -> człon bez zmian
   (np. nazwiska żeńskie zakończone spółgłoską: „Annie Nowak” -> „Anna Nowak”).
"""

from __future__ import annotations

import re
from functools import cache

from odw2json.config_loader import load_lookup

NOM, GEN, DAT, ACC, INS, LOC = "nom", "gen", "dat", "acc", "ins", "loc"
VOWELS = set("aąeęioóuy")

_TITLE = (
    r"adw\.|adwokat(?:a|owi|em|ka|ki|ce|kę|ką)?\b"
    r"|apl\.\s*(?:adw|radc|r\.\s*pr)\.?"
    r"|aplikant(?:a|owi|em|ka|ki|ce|kę|ką)?\s+(?:adwokack|radcowsk)\w*"
    r"|r\.\s*pr\.?|radc(?:a|y|ę|zie|ą)\s+prawn\w*|radczyni\b(?:\s+prawn\w*)?"
    r"|mec\.|mecenas(?:a|owi|em|ie)?\b"
    r"|pan(?:a|u|em|ie|i|ią)?\b"
    r"|dr\b\.?(?:\s*hab\.)?|hab\.|prof\.|mgr\b\.?|inż\.|lic\."
)
_TITLE_RX = re.compile(rf"^\s*(?:{_TITLE})[\s,]*", re.IGNORECASE)

# Celownik/miejscownik rzeczowników na -a: końcówka -> końcówka mianownika (najdłuższe najpierw).
_DAT_A = [
    ("ście", "sta"),
    ("dzie", "da"),
    ("rze", "ra"),
    ("dze", "ga"),
    ("cie", "ta"),
    ("sze", "cha"),
    ("nie", "na"),
    ("mie", "ma"),
    ("sie", "sa"),
    ("zie", "za"),
    ("wie", "wa"),
    ("bie", "ba"),
    ("pie", "pa"),
    ("fie", "fa"),
    ("ce", "ka"),
    ("le", "ła"),
]
_DAT_A_FWD = [(nom[:-1], obl) for obl, nom in _DAT_A]  # rdzeń -> końcówka C./Ms.
_LOC_M = {"r": "rze", "t": "cie", "d": "dzie", "ł": "le", "n": "nie", "m": "mie", "s": "sie"}
_LOC_M |= {"z": "zie", "w": "wie", "b": "bie", "p": "pie", "f": "fie"}
# Nazwisko jednoznacznie w D./B. męskim - rozstrzyga „Daniela/Kamila/Józefa ...”.
_MALE_GEN_SURNAME = re.compile(r"(?:ego|(?:[aąeiouy]k|[iy]cz)a)$")
_OBLIQUE_STEM = {"aleksander": "aleksandr", "kacper": "kacpr"}


# ---------------------------------------------------------------- słownik imion
def _male_forms(n: str) -> dict[str, set[str]]:
    forms: dict[str, set[str]] = {}

    def add(form: str, *cases: str) -> None:
        forms.setdefault(form, set()).update(cases)

    add(n, NOM)
    if n[-1] in "iy":  # Antoni, Jerzy, Ignacy, Cezary
        stem = n if n[-1] == "i" else n[:-1]
        add(stem + "ego", GEN, ACC)
        add(stem + "emu", DAT)
        add(n + "m", INS, LOC)
        return forms
    stem = _OBLIQUE_STEM.get(n)
    if stem is None:
        if n.endswith("ek") and len(n) > 3:
            stem = n[:-2] + "k"  # Marek -> Mark-
        elif n.endswith("eł"):
            stem = n[:-2] + "ł"  # Paweł -> Pawł-
        else:
            stem = n
    add(stem + "a", GEN, ACC)
    add(stem + "owi", DAT)
    add(stem + ("iem" if stem[-1] in "kg" else "em"), INS)
    if stem[-1] in "kg" or stem.endswith(("ch", "sz", "cz", "rz", "ż", "c", "j", "l")):
        add(stem + "u", LOC)
    elif stem.endswith("st"):
        add(stem[:-2] + "ście", LOC)
    elif stem[-1] in _LOC_M:
        add(stem[:-1] + _LOC_M[stem[-1]], LOC)
    return forms


def _female_forms(n: str) -> dict[str, set[str]]:
    forms: dict[str, set[str]] = {n: {NOM}}
    if not n.endswith("a"):
        return forms
    stem = n[:-1]

    def add(form: str, *cases: str) -> None:
        forms.setdefault(form, set()).update(cases)

    if stem.endswith("i"):  # Maria, Julia, Natalia
        add(stem + "i", GEN, DAT, LOC)
    elif stem.endswith("j"):  # Patrycja, Maja
        add((stem[:-1] if stem[-2] in VOWELS else stem) + "i", GEN, DAT, LOC)
    else:
        add(stem + ("i" if stem[-1] in "kgl" else "y"), GEN)
        dat = next((stem[: -len(s)] + o for s, o in _DAT_A_FWD if s and stem.endswith(s)), None)
        if stem[-1] == "l":
            dat = stem + "i"  # Urszula, Izabela
        add(dat or stem + "y", DAT, LOC)
    add(stem + "ę", ACC)
    add(stem + "ą", INS)
    return forms


@cache
def _name_index() -> dict[str, list[tuple[str, str, frozenset[str]]]]:
    """forma (małe litery) -> [(mianownik, rodzaj 'm'/'f', przypadki)]."""
    cfg = load_lookup("imiona")
    index: dict[str, list[tuple[str, str, frozenset[str]]]] = {}
    for gender, key, gen_fn in (("m", "meskie", _male_forms), ("f", "zenskie", _female_forms)):
        for name in cfg.get(key) or []:
            for form, cases in gen_fn(name.lower()).items():
                index.setdefault(form, []).append((name, gender, frozenset(cases)))
    for form, nom in (cfg.get("wyjatki") or {}).items():
        gender = "f" if nom.lower().endswith("a") else "m"
        index[form.lower()] = [(nom, gender, frozenset({GEN, DAT, ACC, INS, LOC}))]
    return index


# ---------------------------------------------------------------- nazwiska
def _fix_stem(stem: str) -> str | None:
    """Rdzeń po odcięciu końcówki -> mianownik (ruchome e)."""
    if len(stem) < 2:
        return None
    if stem[-1] == "k" and stem[-2] not in VOWELS and stem[-2] not in "slń":
        return stem[:-1] + "ek"  # Dudk- -> Dudek, Wieczork- -> Wieczorek
    if stem.endswith(("bl", "pl")):
        return stem[:-1] + "el"  # Wróbl- -> Wróbel
    if stem.endswith("ni") and len(stem) > 2 and stem[-3] not in VOWELS:
        return stem[:-2] + "ień"  # Stępni- -> Stępień
    if stem[-1] in VOWELS:
        return None
    return stem


def _a_noun_oblique(w: str, cases: frozenset[str]) -> str | None:
    """Nazwiska rzeczownikowe na -a (Sikora, Czajka): przypadki zależne -> mianownik."""
    if ACC in cases and w.endswith("ę"):
        return w[:-1] + "a"
    if cases & {ACC, INS} and w.endswith("ą"):
        return w[:-1] + "a"
    if GEN in cases:
        if w.endswith("y") and len(w) > 2 and w[-2] not in VOWELS:
            return w[:-1] + "a"
        if w.endswith(("ki", "gi")) and not w.endswith(("ski", "cki", "dzki")):
            return w[:-1] + "a"
    if cases & {DAT, LOC}:
        for obl, nom in _DAT_A:
            if w.endswith(obl) and len(w) > len(obl) + 1:
                return w[: -len(obl)] + nom
    return None


def _surname_part(w: str, gender: str, cases: frozenset[str]) -> str:
    """Jeden człon nazwiska (małe litery) -> mianownik; brak reguły -> bez zmian."""
    if len(w) < 3:
        return w
    # przymiotnikowe męskie (-ski, -cki, -ny, -ały): rodzaj wynika z końcówki
    if cases & {GEN, ACC} and w.endswith("ego") and len(w) > 4:
        return w[:-4] + "i" if w.endswith("iego") else w[:-3] + "y"
    if DAT in cases and w.endswith("emu") and len(w) > 4:
        return w[:-4] + "i" if w.endswith("iemu") else w[:-3] + "y"
    if cases & {INS, LOC} and w.endswith(("im", "ym")) and len(w) > 4:
        return w[:-1]
    # przymiotnikowe żeńskie (-ska, -cka, -na)
    if cases & {GEN, DAT, LOC} and w.endswith("ej") and len(w) > 4:
        return w[:-3] + "a" if w.endswith("iej") else w[:-2] + "a"
    if gender == "f":
        return _a_noun_oblique(w, cases) or w  # spółgłoskowe żeńskie: nieodmienne
    # męskie rzeczownikowe (Nowak, Szulc, Dudek) i na -a (Sikora)
    res = None
    if DAT in cases and w.endswith(("owi", "ewi")):
        res = _fix_stem(w[:-3])
    elif INS in cases and w.endswith(("kiem", "giem")):
        res = _fix_stem(w[:-3])
    elif INS in cases and w.endswith("em"):
        res = _fix_stem(w[:-2])
    elif LOC in cases and w.endswith("u"):
        res = _fix_stem(w[:-1])
    elif cases & {GEN, ACC} and w.endswith("a"):
        res = _fix_stem(w[:-1])
    return res or _a_noun_oblique(w, cases) or w


# ---------------------------------------------------------------- API
def strip_titles(text: str) -> str:
    """Usuwa tytuły/zwroty grzecznościowe z początku i zwija białe znaki."""
    s = re.sub(r"\s+", " ", text or "").strip()
    while True:
        new = _TITLE_RX.sub("", s, count=1)
        if new == s:
            return s.strip(" ,;:")
        s = new


def _recase(orig: str, low: str) -> str:
    """Przenosi wielkość liter z formy w tekście na wynik (WIELKIE / Pierwsza wielka)."""
    out = []
    for o, r in zip(orig.split("-"), low.split("-"), strict=False):
        if len(o) > 1 and o.isupper():
            out.append(r.upper())
        elif o[:1].isupper():
            out.append(r[:1].upper() + r[1:])
        else:
            out.append(r)
    return "-".join(out)


_LETTER_RUN = re.compile(r"[^\W\d_]+")


def _title_case_if_upper(token: str) -> str:
    """Człon w całości wielkimi literami (>= 2 litery) -> „Jan”, „Nowak-Jeziorański”; reszta bez zmian."""
    letters = _LETTER_RUN.findall(token)
    if sum(len(x) for x in letters) < 2 or not token.isupper():
        return token
    return _LETTER_RUN.sub(lambda m: m[0][:1] + m[0][1:].lower(), token)


def normalize_name(text: str) -> str:
    """Imię i nazwisko w dowolnym przypadku (z tytułami) -> mianownik."""
    s = strip_titles(text)
    s = " ".join(_title_case_if_upper(t) for t in s.split(" ")) if s else s
    tokens = s.split(" ") if s else []
    index = _name_index()
    firsts: list[list[tuple[str, str, frozenset[str]]]] = []
    while len(firsts) < len(tokens) - 1 and tokens[len(firsts)].lower() in index:
        firsts.append(index[tokens[len(firsts)].lower()])
    if not firsts:
        return s
    surnames = tokens[len(firsts) :]
    last = surnames[-1].lower()

    # wspólna interpretacja (rodzaj, przypadki) wszystkich imion
    readings: dict[str, frozenset[str]] = {}
    for gender in ("m", "f"):
        cases: frozenset[str] | None = None
        for cands in firsts:
            c = frozenset().union(*(cs for _, g, cs in cands if g == gender))
            cases = c if cases is None else cases & c
        if cases:
            readings[gender] = cases
    if not readings:
        return s
    if any(NOM in c for c in readings.values()):
        male_gen = GEN in readings.get("m", frozenset())
        if not (male_gen and _MALE_GEN_SURNAME.search(last)):
            return s  # mianownik (albo niejednoznaczne, np. „Daniela Sikora”) - bez zmian
        readings = {"m": readings["m"] - {NOM}}
    if len(readings) > 1:
        # np. „Aleksandrze” = C. żeński albo Ms. męski: męski tylko, gdy nazwisko się odmienia
        female_marked = last.endswith(("ej", "ą", "ę"))
        male = not female_marked and any(_surname_part(p, "m", readings["m"]) != p for p in last.split("-"))
        readings = {g: c for g, c in readings.items() if g == ("m" if male else "f")}
    gender, cases = next(iter(readings.items()))

    out = []
    for tok, cands in zip(tokens, firsts, strict=False):
        nom = next(n for n, g, cs in cands if g == gender and cs & cases)
        out.append(_recase(tok, nom.lower()))
    for tok in surnames:
        parts = [_surname_part(p, gender, cases) for p in tok.lower().split("-")]
        out.append(_recase(tok, "-".join(parts)))
    return " ".join(out)
