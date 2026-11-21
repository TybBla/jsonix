import json
import re
from pathlib import Path

import pytest

from odw2json.ingest import load
from odw2json.ingest.clean import CLEAN_STEPS, DEFAULT_ORDER, clean_text

ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data" / "train"
PL = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
NIP = "123-456-78-90"
IBAN = "60 1010 1010 0008 1362 2310 0000"

EXPECTED = {
    "unicode_nfc",
    "nbsp_to_space",
    "ligatures",
    "ocr_artifacts",
    "quotes",
    "dashes",
    "dehyphenate",
    "join_wrapped_lines",
    "collapse_spaces",
    "strip_page_artifacts",
}


def _real(name: str) -> str:
    return load(TRAIN / name).text


@pytest.fixture(scope="module")
def samples() -> list[str]:
    real = [
        _real("przyklad_01/odwolanie.pdf"),
        _real("przyklad_01/pelnomocnictwo.pdf"),
        _real("przyklad_02/odwolanie.pdf"),
    ]
    synthetic = [
        f"Strona 1 z 2\n\nNIP: {NIP}\nIBAN {IBAN}\n{PL}\n\f\nStopka\n\f\nStopka\n",
        "wyra-\nzu i biało-\nczerwony oraz Sp-\nKrak\n\n\n\n„cytat” – test x  y ﬁn",
    ]
    return real + synthetic


def test_registry_names():
    assert set(CLEAN_STEPS) == EXPECTED
    # DEFAULT_ORDER bez "dashes" (decyzja orkiestratora, docs/decyzje/E2-backend-pdf.md)
    # ... i bez "ocr_artifacts" (tylko dla tekstu z OCR: ingest.ocr.postprocess)
    assert set(DEFAULT_ORDER) == EXPECTED - {"dashes", "ocr_artifacts"}
    assert len(DEFAULT_ORDER) == len(set(DEFAULT_ORDER))


def test_unknown_step():
    with pytest.raises(ValueError, match="dehyphenate"):
        clean_text("x", ["nie_ma_takiego"])


def test_unicode_nfc():
    assert CLEAN_STEPS["unicode_nfc"]("ą") == "ą"
    assert CLEAN_STEPS["unicode_nfc"]("ś") == "ś"


def test_nbsp_to_space():
    assert CLEAN_STEPS["nbsp_to_space"]("a b c d e") == "a b c d e"


def test_ligatures():
    assert CLEAN_STEPS["ligatures"]("ﬁx ﬂ ﬀ ﬃ ﬄ") == "fix fl ff ffi ffl"


def test_ocr_artifacts_typographic_and_lookalikes():
    f = CLEAN_STEPS["ocr_artifacts"]
    assert f("ıdentyfikator ſłowo") == "identyfikator słowo"
    assert f("GDAÑSK gdañsk ZAMÓWIEÑ NADWIŚLAÑSKI") == "GDAŃSK gdańsk ZAMÓWIEŃ NADWIŚLAŃSKI"
    assert f("ktőrym Ő") == "którym Ó"
    assert f("okolicznošci raċhunek ż ŠČŽ čas") == "okoliczności rachunek ż ŚĆŻ ćas"


def test_ocr_artifacts_stray_accents_on_latin_letters():
    f = CLEAN_STEPS["ocr_artifacts"]
    assert f("Zamáwiający wymaganià prowadzonègo Lublín wynikų") == (
        "Zamawiający wymagania prowadzonego Lublin wyniku"
    )
    assert f("ÀÁÍÔ") == "AAIO"


def test_ocr_artifacts_stray_marks_seen_in_scans():
    f = CLEAN_STEPS["ocr_artifacts"]
    assert f("rzetelņą wykoņawcy przyjęçia zașady") == "rzetelną wykonawcy przyjęcia zasady"


def test_ocr_artifacts_leaves_polish_and_foreign_names_untouched():
    f = CLEAN_STEPS["ocr_artifacts"]
    text = f"{PL} Müller Citroën René Schröder ·  – NIP {NIP}\n\f\n"
    assert f(text) == text


def test_ocr_artifacts_does_not_touch_text_layer_corpus(samples):
    for s in samples[:3]:
        assert CLEAN_STEPS["ocr_artifacts"](s) == s


def test_ocr_artifacts_not_in_default_order():
    assert "ocr_artifacts" not in DEFAULT_ORDER
    assert clean_text("José Škoda", DEFAULT_ORDER) == "José Škoda"


def test_quotes():
    assert CLEAN_STEPS["quotes"]("„abc” «x» ‚y’") == '"abc" "x" \'y\''


def test_dashes():
    assert CLEAN_STEPS["dashes"]("a – b — c ‒ d ‐ e") == "a - b - c - d - e"
    assert CLEAN_STEPS["dashes"](NIP) == NIP


def test_dehyphenate():
    f = CLEAN_STEPS["dehyphenate"]
    assert f("wyra-\nzu") == "wyrazu"
    assert f("zamó-\nwienia") == "zamówienia"
    assert f("biało-czerwony") == "biało-czerwony"
    assert f("12-\n34") == "12-\n34"
    assert f("NIP 123-\n456") == "NIP 123-\n456"
    assert f("kod 80-\nabc") == "kod 80-\nabc"
    assert f("abc-\n123") == "abc-\n123"
    assert f("a - \nb") == "a - \nb"
    assert f("Sp-\nKrak") == "Sp-\nKrak"


def test_join_wrapped_lines_basic():
    f = CLEAN_STEPS["join_wrapped_lines"]
    assert f("Spółka z ograniczoną odpowiedzialnością w\nwarszawie przy ul. X") == (
        "Spółka z ograniczoną odpowiedzialnością w warszawie przy ul. X"
    )


def test_join_wrapped_lines_conservative():
    f = CLEAN_STEPS["join_wrapped_lines"]
    long = "To jest dostatecznie długi wiersz tekstu"
    for text in [
        f"{long}.\nkolejne zdanie",  # koniec zdania
        f"{long}\n\nkolejny akapit",  # pusta linia
        f"{long}\nZamawiający",  # wielka litera
        "Zamawiający:\nbelmoria sp. z o.o. w trakcie",  # etykieta
        "ODWOŁANIE W SPRAWIE\nkolejne słowa",  # same wielkie
        f"{long}\na) pierwszy punkt",  # lista
        f"{long}\n- pierwszy punkt",
        f"{long}\n1. pierwszy",
        f"{long}\n• punkt",
        f"{long}\nadres do korespondencji: Gdańsk",  # etykieta w nastepnym
        "NIP: 1234567890 i jeszcze dluzsza reszta wiersza NIP: 1234567890\nkontakt@x.example",
        "krótki\nmały",  # za krótki
        f"{long}\f\nmały ciąg",  # twarda granica stron
        f"{long}\n\fmały ciąg",
    ]:
        assert f(text) == text, text


def test_collapse_spaces():
    f = CLEAN_STEPS["collapse_spaces"]
    assert f("a  \t b   \nc\n\n\n\nd") == "a b\nc\n\nd"
    assert f("a\n\f\nb") == "a\n\f\nb"
    assert f("a \n   \n \n\nb") == "a\n\nb"


def test_strip_page_artifacts_footer_numbers():
    f = CLEAN_STEPS["strip_page_artifacts"]
    assert f("tekst\nStrona 1 z 2\n\nnext") == "tekst\n\nnext"
    assert f("tekst\n  strona 12 Z 30  \nnext") == "tekst\nnext"
    assert f("Strona 2 z 2") == ""
    assert f("Zobacz Strona 1 z 2 w tekście") == "Zobacz Strona 1 z 2 w tekście"


def test_strip_page_artifacts_repeated_footer_keeps_first():
    f = CLEAN_STEPS["strip_page_artifacts"]
    text = "a1\nKancelaria X, tel. 000\n\f\na2\nKancelaria X, tel. 000\n\f\na3\nunikat"
    assert f(text) == "a1\nKancelaria X, tel. 000\n\f\na2\n\f\na3\nunikat"
    assert f(f(text)) == f(text)
    # stopka na 3 stronach: zostaje tylko pierwsze wystapienie
    three = "a\nFOOT\n\fb\nFOOT\n\fc\nFOOT"
    assert f(three) == "a\nFOOT\n\fb\n\fc"
    assert f(f(three)) == f(three)
    # bez \f nic sie nie usuwa
    plain = "a1\nKancelaria X\n\na2\nKancelaria X"
    assert f(plain) == plain
    # pojedyncza stopka nie jest powtorzona
    single = "a1\nKancelaria X\n\f\na2"
    assert f(single) == single


def test_page_boundaries_without_newlines_are_line_boundaries():
    # dokument sklejony samym "\f" (bez "\n" wokol): kroki liniowe widza granice strony
    assert CLEAN_STEPS["strip_page_artifacts"]("a\nStrona 1 z 2\fb") == "a\n\fb"
    assert CLEAN_STEPS["collapse_spaces"]("a  \fb") == "a\fb"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_steps_never_remove_page_breaks(name, samples):
    for s in samples:
        assert CLEAN_STEPS[name](s).count("\f") == s.count("\f")


def test_default_order_keeps_page_count_on_joined_pages():
    pages = ["a-\nb  x\nStopka", "c\nStopka", "d\nStopka", ""]
    out = clean_text("\f".join(pages), DEFAULT_ORDER)
    assert out.count("\f") == 3


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_idempotent(name, samples):
    f = CLEAN_STEPS[name]
    for s in samples:
        once = f(s)
        assert f(once) == once


def test_idempotent_default_order(samples):
    for s in samples:
        once = clean_text(s, DEFAULT_ORDER)
        assert clean_text(once, DEFAULT_ORDER) == once


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_numbers_and_polish_letters_untouched(name):
    f = CLEAN_STEPS[name]
    text = f"NIP: {NIP}\nIBAN: {IBAN}\nKRS 0000123456\n{PL}\nżółć gęślą jaźń"
    assert f(text) == text


def test_numbers_and_polish_letters_untouched_all_steps():
    text = f"NIP: {NIP}\nIBAN: {IBAN}\n{PL}"
    assert clean_text(text, DEFAULT_ORDER) == text


def _keep(t: str) -> str:
    return re.sub(rf"[^\d{PL}]", "", t)


def test_polish_letters_and_digits_preserved_on_real_text(samples):
    for s in samples[:3]:
        out = clean_text(s, DEFAULT_ORDER)
        # "Strona X z Y" jest usuwane, wiec porownujemy po jego odjeciu
        base = re.sub(r"Strona\s+\d+\s+z\s+\d+", "", s, flags=re.I)
        assert _keep(out) == _keep(base)


def test_gt_values_survive_cleaning():
    text = clean_text(_real("przyklad_01/odwolanie.pdf"), DEFAULT_ORDER)
    flat = re.sub(r"\s+", " ", text)
    gt = json.loads((TRAIN / "przyklad_01" / "odwolanie.json").read_text(encoding="utf-8"))
    values = []
    for p in gt["Odwolujacy"] + gt["Zamawiajacy"]:
        values += [p["krs"], p["nip"], p["regon"], p["nazwa"]]
    values.append(gt["Odwolujacy"][0]["pelnomocnik"]["imie_nazwisko"])
    values.append(gt["ZamowieniePubliczne"]["numer_postepowania"])
    values.append(gt["ZamowieniePubliczne"]["tytul"])
    missing = [v for v in values if v not in flat]
    assert not missing
