"""Sonda odporności ekstrakcji: warianty prawdziwych tekstów (w pamięci) i F1 wg reguł UZP.

Idea (recenzja odporności z E4): reguły ekstrakcji łatwo „dopasować” do dosłownych etykiet i układu
linii z danych treningowych. Ukryty zbiór UZP może mieć inne synonimy etykiet, formaty kwot/dat/numerów,
zawinięcia linii, wersaliki albo brak niektórych pól. Skrypt bierze teksty PDF-ów (tylko warstwa tekstu,
**bez OCR**), przerabia je wariantami (a razem z nimi — jeśli trzeba — wartość oczekiwaną GT), uruchamia
ekstrakcję i porównuje z GT tą samą metryką, co bramka (`eval.score`). Wypisuje F1 bazowe, F1 per wariant
i listę „pęknięć” (pól, w których wariant pogorszył wynik względem tekstu oryginalnego).

To narzędzie diagnostyczne, nie bramka: zawsze kończy się kodem 0 (poza błędem użycia).

Użycie (z katalogu repo):
    python scripts/robustness_probe.py --split dev
    python scripts/robustness_probe.py --split all --variant c4 --examples 2
    python scripts/robustness_probe.py --split dev --out output/odpornosc-dev.txt

Opcje:
    --split dev|holdout|all   które sprawy z data/splits.yaml (strojenie wyłącznie na dev!)
    --variant PREFIKS         tylko warianty, których nazwa zaczyna się od prefiksu (np. `b4`, `c`)
    --out PLIK                zapis raportu także do pliku (UTF-8)
    --examples N              dla każdego pęknięcia pokaż do N przykładów PRED vs GT (domyślnie 0)
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import re
import sys
import textwrap
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from eval.score import (  # noqa: E402
    Counts,
    gt_path_for_pdf,
    has_text_layer,
    infer_doc_type,
    load_json,
    score_pair,
)
from odw2json import ingest  # noqa: E402
from odw2json.config_loader import ROOT_DIR, load_app_config, load_registry  # noqa: E402
from odw2json.contracts import Document  # noqa: E402
from odw2json.extract import extract  # noqa: E402
from odw2json.ingest.clean import clean_text  # noqa: E402
from odw2json.splits import load_splits  # noqa: E402

TRAIN_DIR = ROOT_DIR / "data" / "train"
NO_OCR = {"ocr": {"enabled": False}}
SPLIT_CHOICES = ("dev", "holdout", "all")
BREAK_EPS = 0.005  # pole „pęka”, gdy F1 typu spada o więcej niż to
MAX_CASES_SHOWN = 3

MONTHS = [
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
]
MONTH_RX = "|".join(MONTHS)
PL = "A-ZĄĆĘŁŃÓŚŹŻ"
pl = "a-ząćęłńóśźż"


# ------------------------------------------------------------------ korpus


@dataclass
class Sample:
    """Jeden dokument korpusu: tekst warstwy tekstowej, GT i typ (wg kluczy GT, jak w eval)."""

    case: str
    type: str
    text: str
    gt: dict


def build_corpus(split: str, registry: dict | None = None) -> list[Sample]:
    """Dokumenty z `data/train` dla splitu (dev/holdout/all): tylko warstwa tekstu, bez skanów i OCR."""
    if split not in SPLIT_CHOICES:
        raise ValueError(f"nieznany split {split!r} (dozwolone: {', '.join(SPLIT_CHOICES)})")
    registry = registry or load_registry()
    splits = load_splits()
    cases = splits["dev"] + splits["holdout"] if split == "all" else splits[split]
    out: list[Sample] = []
    for case in cases:
        if case.replace("\\", "/").startswith("skany/"):
            continue
        for pdf in sorted((TRAIN_DIR / case).glob("*.pdf")):
            gt_file = gt_path_for_pdf(pdf)
            if gt_file is None or not has_text_layer(pdf):
                continue
            gt = load_json(gt_file)
            typ = infer_doc_type(gt, registry)
            text = ingest.load(pdf, cfg=NO_OCR).text
            if typ is None or not text.strip():
                continue
            out.append(Sample(case, typ, text, gt))
    return out


# ----------------------------------------------------------------- warianty
# Wariant: (tekst, gt, typ) -> (nowy tekst, nowe gt). Jeśli wariant nie ma zastosowania, zwraca wejście bez
# zmian (wtedy dokument jest pomijany). GT zmieniamy tylko tam, gdzie wartość oczekiwana zmienia się razem
# z tekstem (np. usunięty numer TED -> `null`); w pozostałych wariantach GT zostaje z danych.

Variant = Callable[[str, dict, str], tuple[str, dict]]


def sub(pattern: str, repl: str, flags: int = 0) -> Variant:
    def f(t: str, gt: dict, typ: str) -> tuple[str, dict]:
        return re.sub(pattern, repl, t, flags=flags), gt

    return f


def only(doc_type: str, fn: Variant) -> Variant:
    """Wariant stosowany tylko do dokumentów jednego typu (etykiety przelewu nie mają sensu w odwołaniu)."""

    def f(t: str, gt: dict, typ: str) -> tuple[str, dict]:
        return fn(t, gt, typ) if typ == doc_type else (t, gt)

    return f


syn_kwota = only(
    "przelew", sub(r"(?im)^(\s*)(Kwota (?:przelewu|operacji|transakcji)|Warto[śs][ćc])\b", r"\1Kwota")
)
syn_tytul = only(
    "przelew",
    sub(r"(?im)^(\s*)(Tytu[łl]em|Tytu[łl] przelewu|Tytu[łl]|Opis(?: operacji)?)\b:?", r"\1Tytuł płatności:"),
)
syn_odw = sub(r"(?m)^(\s*)Odwołujący:", r"\1Wykonawca wnoszący odwołanie:")
syn_zam = sub(r"(?m)^(\s*)Zamawiający:", r"\1Instytucja zamawiająca:")
syn_nip = sub(r"\bNIP:", "NIP")
syn_krs = sub(r"\bKRS:?\s", "nr KRS ")
syn_pel = sub(r"(?i)udzielam(y)? pełnomocnictwa", "umocowuję")
syn_benef = sub(r"(?im)^(\s*)(Adresat przelewu|Beneficjent|Odbiorca|Dane odbiorcy)\b", r"\1Kontrahent")


def iso2num(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return re.sub(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", lambda m: f"{m[3]}.{m[2]}.{m[1]}", t), gt


def num2word(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    t = re.sub(
        r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)",
        lambda m: f"{int(m[3])} {MONTHS[int(m[2]) - 1]} {m[1]} r.",
        t,
    )
    t = re.sub(
        r"(?<![\d.])(\d{1,2})\.(\d{2})\.(\d{4})(?!\d)",
        lambda m: f"{int(m[1])} {MONTHS[int(m[2]) - 1]} {m[3]} r.",
        t,
    )
    return t, gt


def word2num(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return (
        re.sub(
            rf"(?<!\d)(\d{{1,2}}) ({MONTH_RX}) (\d{{4}})(?: (?:r\.|roku))?",
            lambda m: f"{int(m[1]):02d}.{MONTHS.index(m[2]) + 1:02d}.{m[3]}",
            t,
        ),
        gt,
    )


def amount_fmt(fmt: Callable[[float], str], newval: float | None = None) -> Variant:
    """Zmienia zapis kwoty przelewu (i ewentualnie jej wartość, wtedy także GT)."""

    def f(t: str, gt: dict, typ: str) -> tuple[str, dict]:
        if typ != "przelew":
            return t, gt
        k = gt["przelew_bankowy"]["kwota"]
        if k is None:
            return t, gt
        v = newval if newval is not None else k
        pat = re.escape(f"{k:.2f}").replace(r"\.", "[.,]")
        t2 = re.sub(rf"(?<![\d.,]){pat}(?:\s*(?:PLN|zł))?", lambda _m: fmt(v), t)
        gt = copy.deepcopy(gt)
        gt["przelew_bankowy"]["kwota"] = float(v)
        return t2, gt

    return f


def pl_thousands(v: float) -> str:
    i, d = f"{v:.2f}".split(".")
    return f"{int(i):,}".replace(",", ".") + f",{d} zł"


def _iban_gt(gt: dict, prefix: str) -> dict:
    """GT z numerami rachunków zapisanymi „jak w dokumencie” (ustalenie UZP): z prefiksem `PL` albo bez."""
    gt = copy.deepcopy(gt)
    for key in ("na_rachunek", "z_rachunku"):
        v = (gt.get("przelew_bankowy") or {}).get(key)
        if v:
            gt["przelew_bankowy"][key] = prefix + re.sub(r"\D", "", v)[-26:]
    return gt


def iban_spaced(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """IBAN zapisany „PL12 3456 …” (z prefiksem i spacjami); w GT numer z `PL`, bez spacji."""

    def r(m: re.Match) -> str:
        d = m.group(2)
        return "PL" + d[:2] + " " + " ".join(d[i : i + 4] for i in range(2, 26, 4))

    t2 = re.sub(r"(?<![\dA-Za-z])(PL)?(\d{26})(?!\d)", r, t)
    return (t2, _iban_gt(gt, "PL")) if t2 != t and typ == "przelew" else (t, gt)


def iban_compact_nopl(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """IBAN ciągiem cyfr, bez „PL” i bez spacji; w GT numer bez prefiksu."""
    t2 = re.sub(
        r"(?<![\dA-Za-z])(?:PL\s?)?(\d{2}(?:\s?\d{4}){6})(?!\d)", lambda m: re.sub(r"\s", "", m[1]), t
    )
    return (t2, _iban_gt(gt, "")) if t2 != t and typ == "przelew" else (t, gt)


def nip_dash(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return re.sub(r"(NIP\W{0,3})(\d{3})(\d{3})(\d{2})(\d{2})(?!\d)", r"\1\2-\3-\4-\5", t), gt


def bzp_space(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return re.sub(r"(\d{4}/BZP)(\d{8})", r"\1 \2", t), gt


def bzp_slash(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Numer BZP z przyrostkiem „/01”; numer wpisujemy „jak w dokumencie”, więc w GT też z przyrostkiem."""
    t2 = re.sub(r"(\d{4}) ?/ ?BZP\s?(\d{8})(?!/)", r"\1/BZP \2/01", t)
    bzp = (gt.get("ZamowieniePubliczne") or {}).get("numer_bzp") if typ == "odwolanie" else None
    m = re.fullmatch(r"(\d{4})/BZP(\d{8})", bzp or "")
    if m is None or not re.search(rf"{m[1]} ?/ ?BZP\s?{m[2]}(?!/)", t):
        return t2, gt  # numer z nagłówka nie zmienił się (inny zapis albo już z przyrostkiem)
    gt = copy.deepcopy(gt)
    gt["ZamowieniePubliczne"]["numer_bzp"] = bzp + "/01"
    return t2, gt


def swap_parties(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Zamienia miejscami bloki „Odwołujący” i „Zamawiający” (do tytułu/`dotyczy`)."""
    if typ != "odwolanie":
        return t, gt
    lines = t.split("\n")

    def find(prefix: str) -> int | None:
        rx = re.compile(rf"\s*{prefix}[{pl}]*\s*(:|\()")
        return next((i for i, ln in enumerate(lines) if rx.match(ln)), None)

    o, z = find("Odwołując"), find("Zamawiając")
    if o is None or z is None:
        return t, gt
    endrx = re.compile(r"\s*(ODWOŁANIE|dotyczy|Dotyczy|Wykonawca wybrany|Przystępując|Uczestnik)")
    a, b = sorted([o, z])
    e = next((i for i in range(b + 1, len(lines)) if endrx.match(lines[i])), None)
    if e is None:
        return t, gt
    return "\n".join(lines[:a] + lines[b:e] + lines[a:b] + lines[e:]), gt


def blank_lines(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return t.replace("\n", "\n\n"), gt


def label_inline(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """„Etykieta⏎wartość” -> „Etykieta: wartość” (tylko przelew)."""
    if typ != "przelew":
        return t, gt
    labels = (
        r"Opis|Tytu[łl]\w*(?: przelewu)?|Warto[śs][ćc]|Kwota(?: operacji| przelewu)?|Data \w+|Numer \w+|"
        r"Nr ref\.|P[łl]atnik|Nadawca|Zleceniodawca|Odbiorca|Beneficjent|Adresat przelewu|Rachunek \w+|"
        r"Dane \w+|Status|Kana[łl]"
    )
    return re.sub(rf"(?m)^({labels})\n(?=\S)", r"\1: ", t), gt


def rewrap(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    out: list[str] = []
    for para in t.split("\n"):
        out.extend(textwrap.wrap(para, 55, break_long_words=False, break_on_hyphens=False) or [""])
    return "\n".join(out), gt


def unwrap(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return re.sub(rf"(?<=[{pl},])\n(?=[{pl}])", " ", t), gt


def upper_labels(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    labels = (
        "Odwołujący|Zamawiający|Kwota operacji|Kwota|Tytułem|Tytuł przelewu|Data operacji|"
        "Data transakcji|Rachunek odbiorcy|Mocodawca|Pełnomocnik"
    )
    return re.sub(rf"(?m)^(\s*)({labels})\b", lambda m: m[1] + m[2].upper(), t), gt


def drop_ted(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    if typ != "odwolanie" or not gt["ZamowieniePubliczne"].get("numer_ted"):
        return t, gt
    t2 = re.sub(
        r",?\s*(?:numer )?(?:ogłoszenia )?(?:w )?"
        r"(?:TED|Dzienniku Urzędowym Unii Europejskiej|Dz\. ?Urz\. ?UE)[^\n,]*?\d{6}-\d{4}",
        "",
        t,
    )
    t2 = re.sub(r"\b\d{6}-20\d{2}\b|\d{4}/S\s?\d{1,3}-\d{6}", "", t2)
    gt = copy.deepcopy(gt)
    gt["ZamowieniePubliczne"]["numer_ted"] = None
    return t2, gt


def drop_mail(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    if typ != "odwolanie" or not gt.get("Odwolujacy"):
        return t, gt
    m = gt["Odwolujacy"][0]["pelnomocnik"].get("mail")
    if not m:
        return t, gt
    gt = copy.deepcopy(gt)
    gt["Odwolujacy"][0]["pelnomocnik"]["mail"] = None
    return re.sub(re.escape(m), "", t, flags=re.IGNORECASE), gt


def drop_dateline(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Usuwa linię „Miejscowość, (dnia) DATA” (po miejscowości z GT); w GT `data` i `miejscowosc` = null."""
    place = gt["OdwolanieKIO"].get("miejscowosc") if typ == "odwolanie" else None
    if not place or not gt["OdwolanieKIO"].get("data"):
        return t, gt
    lines = t.split("\n")
    rx = re.compile(rf"^\s*{re.escape(place)},?\s*(?:dnia\s+)?\d")
    idx = next((i for i, ln in enumerate(lines[:40]) if rx.match(ln)), None)
    if idx is None:
        return t, gt
    del lines[idx]
    gt = copy.deepcopy(gt)
    gt["OdwolanieKIO"]["data"] = None
    gt["OdwolanieKIO"]["miejscowosc"] = None
    return "\n".join(lines), gt


def drop_ref(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    if typ != "przelew":
        return t, gt
    n = gt["przelew_bankowy"]["numer_transakcji"]
    if not n:
        return t, gt
    t2 = re.sub(
        r"(?im)^[ \t]*(nr ref\.?|numer referencyjny|numer transakcji[^\n]*?|identyfikator operacji"
        r"|id transakcji)[ \t]*:?[ \t]*\n?[ \t]*" + re.escape(n) + r"\.?[ \t]*$",
        "",
        t,
    )
    if t2 == t:
        return t, gt
    gt = copy.deepcopy(gt)
    gt["przelew_bankowy"]["numer_transakcji"] = None
    return t2, gt


def drop_krs_pel(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    if typ != "pelnomocnictwo":
        return t, gt
    gt = copy.deepcopy(gt)
    for m in gt["mocodawca"]:
        k = m["data"].get("krs")
        if k:
            t2 = re.sub(r"(?i),?\s*(?:nr\s+)?KRS:?\s*(?:pod numerem\s*)?" + k, "", t)
            if t2 != t:
                t = t2
                m["data"]["krs"] = None
    return t, gt


def names_upper(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    if typ != "pelnomocnictwo":
        return t, gt
    for p in gt.get("pelnomocnicy") or []:
        n = p.get("imie_nazwisko")
        if n:
            t = t.replace(n, n.upper())
    return t, gt


def nbsp_spaces(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Twarde spacje (U+00A0) zamiast zwykłych między cyframi i przed „zł/PLN” (typowy artefakt PDF)."""
    t = re.sub(r"(?<=\d) (?=\d)", " ", t)
    return re.sub(r" (?=(?:zł|PLN)\b)", " ", t), gt


def relabel(doc_type: str, labels: str, new: str) -> Variant:
    """Etykieta na początku linii (jedna z `labels`, regex) -> `new`; reszta linii bez zmian."""
    return only(doc_type, sub(rf"(?im)^([ \t]*)(?:{labels})(?=[ \t:]|$)", r"\g<1>" + new))


def date_fmt(fmt: str) -> Variant:
    """Daty ISO (`RRRR-MM-DD`) w dokumencie przelewu -> inny zapis (`DD-MM-RRRR`, `DD/MM/RRRR`)."""

    def f(t: str, gt: dict, typ: str) -> tuple[str, dict]:
        if typ != "przelew":
            return t, gt
        return re.sub(
            r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", lambda m: fmt.format(y=m[1], m=m[2], d=m[3]), t
        ), gt

    return f


def time_suffix(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Do dat w dokumencie przelewu dopisuje godzinę (`2026-03-21 14:32:07`), jak w wydrukach bankowych."""
    if typ != "przelew":
        return t, gt
    return re.sub(r"(?<![\d-])(\d{4}-\d{2}-\d{2})(?![\d-])", r"\1 14:32:07", t), gt


def amount_words(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Za kwotą przelewu dopisuje „(słownie: … 00/100)”."""
    if typ != "przelew" or gt["przelew_bankowy"].get("kwota") is None:
        return t, gt
    k = f"{gt['przelew_bankowy']['kwota']:.2f}".replace(".", "[.,]")
    return re.sub(rf"(?<![\d.,])({k}\s*(?:PLN|zł))", r"\1 (słownie: kwota 00/100)", t, count=1), gt


def nip_pl_prefix(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """NIP z unijnym prefiksem kraju (`NIP PL9999284065`); wartość oczekiwana bez prefiksu."""
    return re.sub(r"(NIP\W{0,3})(\d{10})(?!\d)", r"\1PL\2", t), gt


def keys_reorder(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Linia „KRS: x, NIP: y, REGON: z” -> inna kolejność identyfikatorów (NIP, REGON, KRS)."""
    return re.sub(
        r"(?m)^(\s*)KRS: (\d{10}), NIP: (\d{10}), REGON: (\d{9,14})\s*$",
        r"\1NIP: \3, REGON: \4, KRS: \2",
        t,
    ), gt


def contact_swap(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """„tel. 000 000 000, adres@poczta” -> „e-mail: adres@poczta, tel. 000 000 000” (odwołanie)."""
    if typ != "odwolanie":
        return t, gt
    return re.sub(r"(?m)^(\s*)tel\. ([\d ]+), (\S+@\S+)\s*$", r"\1e-mail: \3, tel. \2", t), gt


def party_inline(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """„Odwołujący:⏎Nazwa” -> „Odwołujący: Nazwa” (układ skanów w warstwie tekstu)."""
    if typ != "odwolanie":
        return t, gt
    return re.sub(r"(?m)^(Odwołujący|Zamawiający):[ \t]*\n(?=\S)", r"\1: ", t), gt


def action_inverted(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """„Zamawiający w dniu D …” -> „W dniu D Zamawiający …” (inny szyk zdania o zaskarżonej czynności)."""
    if typ != "odwolanie":
        return t, gt
    rx = r"(?m)^Zamawiający w dniu (\d{1,2} [a-ząćęłńóśźż]+ \d{4}(?: roku| r\.)?) "
    return re.sub(rx, r"W dniu \1 Zamawiający ", t), gt


def colon_labels(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    """Etykiety stojące w osobnej linii dostają dwukropek („Płatnik” -> „Płatnik:”) — typ przelew."""
    if typ != "przelew":
        return t, gt
    rx = (
        r"(?m)^(Płatnik|Nadawca|Zleceniodawca|Beneficjent|Odbiorca|Adresat przelewu|Kwota operacji|Kwota|"
        r"Opis|Data operacji|Data transakcji|Rachunek obciążany|Rachunek odbiorcy|Nr ref\.|Dane nadawcy|"
        r"Dane odbiorcy|Tytułem|Tytuł|Wartość|Numer transakcji)[ \t]*$"
    )
    return re.sub(rx, r"\1:", t), gt


def as_ingested(fn: Variant) -> Variant:
    """Artefakt białych znaków, który w prawdziwym potoku usuwa ingest (backend + `ingest.clean` z app.yaml).

    Wariant przechodzi przez to samo czyszczenie, więc jest istotny tylko tam, gdzie czyszczenie zawodzi
    (np. po zmianie listy kroków w konfiguracji). Gdy czyszczenie przywraca tekst, dokument jest pomijany.
    """

    def f(t: str, gt: dict, typ: str) -> tuple[str, dict]:
        t2, gt2 = fn(t, gt, typ)
        t2 = t2.replace("\r\n", "\n").replace("\r", "\n")
        steps = (load_app_config().get("ingest") or {}).get("clean") or []
        return clean_text(t2, list(steps)), gt2

    return f


def double_spaces(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return t.replace(" ", "  "), gt


def trailing_spaces(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return re.sub(r"(?m)$", "  ", t), gt


def crlf(t: str, gt: dict, typ: str) -> tuple[str, dict]:
    return t.replace("\n", "\r\n"), gt


VARIANTS: dict[str, Variant] = {
    "a1 Kwota operacji/Wartość->Kwota": syn_kwota,
    "a2 Tytułem/Opis->Tytuł płatności:": syn_tytul,
    "a3 Odbiorca/Beneficjent->Kontrahent": syn_benef,
    "a4 Odwołujący:->Wykonawca wnoszący odwołanie:": syn_odw,
    "a5 Zamawiający:->Instytucja zamawiająca:": syn_zam,
    "a6 NIP: -> NIP": syn_nip,
    "a7 KRS: -> nr KRS": syn_krs,
    "a8 udzielam pełn.->umocowuję": syn_pel,
    "b1 ISO->DD.MM.RRRR": iso2num,
    "b2 daty->słownie": num2word,
    "b3 słownie->DD.MM.RRRR": word2num,
    "b4 kwota 10.000,00 zł": amount_fmt(pl_thousands, 10000.0),
    "b5 kwota 10 000 PLN": amount_fmt(lambda v: "10 000 PLN", 10000.0),
    "b6 kwota 17 zł (bez groszy)": amount_fmt(lambda v: f"{int(v)} zł"),
    "b7 kwota PLN 17,00": amount_fmt(lambda v: "PLN " + f"{v:.2f}".replace(".", ",")),
    "b8 IBAN PL+spacje": iban_spaced,
    "b9 IBAN ciągiem bez PL": iban_compact_nopl,
    "b10 NIP z myślnikami": nip_dash,
    "b11 BZP ze spacją": bzp_space,
    "b12 BZP 'RRRR/BZP N/01'": bzp_slash,
    "b13 twarde spacje (NBSP)": as_ingested(nbsp_spaces),
    "c1 Zamawiający<->Odwołujący": swap_parties,
    "c2 puste linie": blank_lines,
    "c3 'Etykieta: wartość' w 1 linii": label_inline,
    "c4 zawinięcie 55 zn.": rewrap,
    "c5 odwinięcie linii": unwrap,
    "c6 etykiety WIELKIMI": upper_labels,
    "c7 nazwiska pełn. WIELKIMI": names_upper,
    "d1 brak TED": drop_ted,
    "d2 brak e-maila": drop_mail,
    "d3 brak linii 'Miejsc., data'": drop_dateline,
    "d4 brak nr ref. przelewu": drop_ref,
    "d5 brak KRS mocodawcy": drop_krs_pel,
    # --- rozszerzenie (E7-13): kolejne synonimy etykiet, formaty i układy spotykane w wydrukach/pismach
    "a9 data operacji->Data przelewu": relabel(
        "przelew", "Data operacji|Data transakcji|Data realizacji|Data wykonania", "Data przelewu"
    ),
    "a10 data operacji->Data zlecenia": relabel(
        "przelew", "Data operacji|Data transakcji|Data realizacji|Data wykonania", "Data zlecenia"
    ),
    "a11 numer transakcji->Nr transakcji": relabel(
        "przelew",
        "Numer transakcji(?: operacji)?|Numer referencyjny(?: operacji)?|Nr ref\\.?|Identyfikator operacji",
        "Nr transakcji",
    ),
    "a12 numer transakcji->Identyfikator płatności": relabel(
        "przelew",
        "Numer transakcji(?: operacji)?|Numer referencyjny(?: operacji)?|Nr ref\\.?|Identyfikator operacji",
        "Identyfikator płatności",
    ),
    "a13 rachunek nadawcy->Rachunek źródłowy": relabel(
        "przelew",
        "Rachunek zleceniodawcy|Rachunek obciążany|Rachunek nadawcy|Z rachunku",
        "Rachunek źródłowy",
    ),
    "a14 rachunek odbiorcy->Rachunek docelowy": relabel(
        "przelew",
        "Rachunek odbiorcy|Rachunek beneficjenta|Rachunek uznawany|Na rachunek",
        "Rachunek docelowy",
    ),
    "a15 tytuł->Opis płatności": relabel(
        "przelew", "Tytu[łl] przelewu|Tytułem|Tytu[łl]|Opis", "Opis płatności"
    ),
    "a16 tytuł->Treść przelewu": relabel(
        "przelew", "Tytu[łl] przelewu|Tytułem|Tytu[łl]|Opis", "Treść przelewu"
    ),
    "a17 kwota->Kwota płatności": relabel(
        "przelew", "Kwota operacji|Kwota przelewu|Kwota transakcji|Kwota|Wartość", "Kwota płatności"
    ),
    "a18 PESEL->nr PESEL": only("pelnomocnictwo", sub(r"\bPESEL:?\s", "nr PESEL ")),
    "a19 NIP -> NIP:": sub(r"\bNIP (?=\d)", "NIP: "),
    "a20 reprezentowany przez->reprezentowany przez pełnomocnika": only(
        "odwolanie", sub(r"(?m)^reprezentowan(\w) przez:", r"reprezentowan\1 przez pełnomocnika:")
    ),
    "a21 adres do korespondencji->adres do doręczeń": only(
        "odwolanie", sub(r"(?m)^adres do korespondencji:", "adres do doręczeń:")
    ),
    "a22 nr referencyjny sprawy->znak sprawy": only(
        "odwolanie", sub(r"nr referencyjny sprawy:", "znak sprawy:")
    ),
    "a23 nr referencyjny sprawy->numer postępowania": only(
        "odwolanie", sub(r"nr referencyjny sprawy:", "numer postępowania:")
    ),
    "a24 numer ogłoszenia TED->ogłoszenie TED nr": only(
        "odwolanie", sub(r"numer ogłoszenia TED:", "ogłoszenie TED nr")
    ),
    "a25 ogłoszenie o zamówieniu nr->numer ogłoszenia BZP:": only(
        "odwolanie", sub(r"ogłoszenie o zamówieniu nr\s+(?=\d{4}\s*/\s*BZP)", "numer ogłoszenia BZP: ")
    ),
    "a26 Zarzut nr N->Zarzut N": only("odwolanie", sub(r"(?m)^Zarzut nr (\d)", r"Zarzut \1")),
    "a27 Zarzut nr N->ZARZUT NR N": only("odwolanie", sub(r"(?m)^Zarzut nr (\d)", r"ZARZUT NR \1")),
    "a28 w dniu->dnia (czynność)": only("odwolanie", sub(r"(?m)^Zamawiający w dniu ", "Zamawiający dnia ")),
    "b14 data DD-MM-RRRR": date_fmt("{d}-{m}-{y}"),
    "b15 data DD/MM/RRRR": date_fmt("{d}/{m}/{y}"),
    "b16 data z godziną": time_suffix,
    "b17 kwota z dopiskiem 'słownie'": amount_words,
    "b18 NIP z prefiksem PL": nip_pl_prefix,
    "b19 KRS/NIP/REGON w innej kolejności": keys_reorder,
    "c8 etykiety z dwukropkiem": colon_labels,
    "c9 podwójne spacje": as_ingested(double_spaces),
    "c10 spacje na końcu linii": as_ingested(trailing_spaces),
    "c11 CRLF": as_ingested(crlf),
    "c12 'Odwołujący: Nazwa' w 1 linii": party_inline,
    "c13 'W dniu D Zamawiający ...'": action_inverted,
    "c14 e-mail przed telefonem": contact_swap,
}


# ------------------------------------------------------------------ pomiar


def run_extract(text: str, typ: str, registry: dict) -> dict:
    """Ekstrakcja z tekstu w pamięci (bez pliku, bez klasyfikacji — typ znany z GT)."""
    doc = Document(path=Path("x.pdf"), text=text, pages=[text], page_offsets=[0])
    return extract(doc, registry[typ]).data


@dataclass
class VariantRow:
    variant: str
    type: str
    n: int
    base_f1: float
    var_f1: float

    @property
    def broke(self) -> bool:
        return self.var_f1 < self.base_f1 - BREAK_EPS


@dataclass
class Break:
    variant: str
    type: str
    path: str
    cases: list[str] = field(default_factory=list)


@dataclass
class Report:
    split: str
    base: dict[str, Counts]  # F1 bazowe per typ
    base_docs: dict[str, int]
    rows: list[VariantRow]
    breaks: list[Break]
    examples: dict[tuple[str, str, str], list[tuple[str, dict, dict]]]


def _f1(c: Counts) -> float:
    d = 2 * c.tp + c.fp + c.fn
    return 2 * c.tp / d if d else 1.0


def evaluate(
    samples: Iterable[Sample],
    registry: dict,
    variants: dict[str, Variant] | None = None,
    only: str | None = None,
    split: str = "",
    max_examples: int = 0,
) -> Report:
    """Liczy F1 bazowe i per wariant (per typ dokumentu) oraz pęknięcia (pola, które pogorszyły się)."""
    samples = list(samples)
    variants = VARIANTS if variants is None else variants
    types = sorted({s.type for s in samples})
    base: dict[str, Counts] = {t: Counts() for t in types}
    base_docs: dict[str, int] = dict.fromkeys(types, 0)
    base_each: list[Counts] = []
    for s in samples:
        c = score_pair(run_extract(s.text, s.type, registry), s.gt)
        base_each.append(c)
        base[s.type] = base[s.type] + c
        base_docs[s.type] += 1

    rows: list[VariantRow] = []
    breaks: dict[tuple[str, str, str], Break] = {}
    examples: dict[tuple[str, str, str], list[tuple[str, dict, dict]]] = collections.defaultdict(list)
    for vname, fn in variants.items():
        if only and not vname.startswith(only):
            continue
        for typ in types:
            cb, cv, n = Counts(), Counts(), 0
            for s, b in zip(samples, base_each, strict=True):
                if s.type != typ:
                    continue
                t2, gt2 = fn(s.text, s.gt, typ)
                if t2 == s.text and gt2 == s.gt:
                    continue
                n += 1
                pred = run_extract(t2, typ, registry)
                sc = score_pair(pred, gt2)
                cb, cv = cb + b, cv + sc
                for key, c in sc.fields.items():
                    b0 = b.fields.get(key, Counts())
                    if (c.fp + c.fn) > (b0.fp + b0.fn):
                        k = (vname, typ, key)
                        breaks.setdefault(k, Break(vname, typ, key)).cases.append(s.case)
                        if len(examples[k]) < max_examples:
                            examples[k].append((s.case, pred, gt2))
            if n:
                rows.append(VariantRow(vname, typ, n, _f1(cb), _f1(cv)))
    return Report(split, base, base_docs, rows, sorted(breaks.values(), key=_break_key), dict(examples))


def _break_key(b: Break) -> tuple:
    return (b.variant, b.type, b.path)


# ------------------------------------------------------------------ raport


def _values(obj: object, path: str) -> list:
    """Wartości z `obj` pod ścieżką z raportu (`a.b`, `lista[].pole`); listy są spłaszczane."""
    cur: list = [obj]
    for part in path.split("."):
        key = part.removesuffix("[]")
        nxt: list = []
        for o in cur:
            v = o.get(key) if isinstance(o, dict) else None
            nxt.extend(v if part.endswith("[]") and isinstance(v, list) else [v])
        cur = nxt
    return cur


def _shorten(obj: object, limit: int = 300) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= limit else s[:limit] + "…"


def format_report(rep: Report) -> str:
    """Czytelny raport tekstowy: F1 bazowe, tabela wariantów, lista pęknięć (+ przykłady)."""
    out = [f"split={rep.split}", "", "F1 bazowe (teksty oryginalne):"]
    for typ, c in rep.base.items():
        out.append(f"  {typ:15s} n={rep.base_docs[typ]:3d} F1={_f1(c):.3f}")
    out += ["", "F1 per wariant (tylko dokumenty zmienione przez wariant; <<< = spadek o > 0,005):"]
    for r in rep.rows:
        flag = "  <<<" if r.broke else ""
        out.append(f"{r.variant:46s} {r.type:15s} n={r.n:3d} base={r.base_f1:.3f} var={r.var_f1:.3f}{flag}")
    out += ["", "--- pękające pola (wariant, typ, pole, liczba dokumentów, przykładowe sprawy)"]
    if not rep.breaks:
        out.append("(brak)")
    for b in rep.breaks:
        shown = ", ".join(b.cases[:MAX_CASES_SHOWN])
        out.append(f"({b.variant!r}, {b.type!r}, {b.path!r}) {len(b.cases)} [{shown}]")
    if rep.examples:
        out += ["", "--- przykłady (PRED vs GT po wariancie)"]
        for (vname, typ, key), items in sorted(rep.examples.items()):
            for case, pred, gt in items:
                out += [
                    f"#### {vname} | {typ} | {key} | {case}",
                    f"PRED {_shorten(_values(pred, key))}",
                    f"GT   {_shorten(_values(gt, key))}",
                ]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--split", choices=SPLIT_CHOICES, default="dev")
    ap.add_argument("--variant", default=None, help="prefiks nazwy wariantu (np. b4, c)")
    ap.add_argument("--out", type=Path, default=None, help="zapisz raport także do pliku")
    ap.add_argument("--examples", type=int, default=0, help="liczba przykładów PRED/GT na pęknięcie")
    args = ap.parse_args(argv)

    registry = load_registry()
    samples = build_corpus(args.split, registry)
    rep = evaluate(samples, registry, only=args.variant, split=args.split, max_examples=max(0, args.examples))
    text = format_report(rep)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
