"""Testy normalizatorów wartości (odw2json/extract/normalize.py)."""

from __future__ import annotations

import pytest

from odw2json.extract.normalize import (
    NORMALIZERS,
    amount,
    bzp,
    company,
    date,
    digits,
    email,
    iban,
    krs,
    nip,
    ocr_fix,
    pesel,
    regon,
    ted,
    ws,
)

# --- date -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("11.09.2026", "2026-09-11"),
        ("11.09.2026 r.", "2026-09-11"),
        ("2026-09-11", "2026-09-11"),
        ("11 września 2026", "2026-09-11"),
        ("11 wrzesnia 2026 roku", "2026-09-11"),
        ("1 kwietnia 2026", "2026-04-01"),
        ("  1.4.2026  ", "2026-04-01"),
    ],
)
def test_date_formaty(raw: str, expected: str) -> None:
    assert date(raw) == expected


@pytest.mark.parametrize(
    ("miesiac", "numer"),
    [
        ("stycznia", 1),
        ("lutego", 2),
        ("marca", 3),
        ("kwietnia", 4),
        ("maja", 5),
        ("czerwca", 6),
        ("lipca", 7),
        ("sierpnia", 8),
        ("września", 9),
        ("października", 10),
        ("listopada", 11),
        ("grudnia", 12),
    ],
)
def test_date_dwanascie_miesiecy_z_polskimi_znakami(miesiac: str, numer: int) -> None:
    assert date(f"15 {miesiac} 2026") == f"2026-{numer:02d}-15"


@pytest.mark.parametrize(
    ("miesiac", "numer"),
    [
        ("stycznia", 1),
        ("lutego", 2),
        ("marca", 3),
        ("kwietnia", 4),
        ("maja", 5),
        ("czerwca", 6),
        ("lipca", 7),
        ("sierpnia", 8),
        ("wrzesnia", 9),
        ("pazdziernika", 10),
        ("listopada", 11),
        ("grudnia", 12),
    ],
)
def test_date_dwanascie_miesiecy_bez_polskich_znakow(miesiac: str, numer: int) -> None:
    assert date(f"3 {miesiac} 2026 r.") == f"2026-{numer:02d}-03"


@pytest.mark.parametrize(
    "raw",
    [
        "31.02.2026",
        "2026-02-30",
        "11.13.2026",
        "32 września 2026",
        "29 lutego 2026",
        "11 września",
        "tekst bez daty",
        "",
    ],
)
def test_date_nieprawidlowa_zwraca_none(raw: str) -> None:
    assert date(raw) is None


def test_date_przestepny_rok() -> None:
    assert date("29 lutego 2028") == "2028-02-29"


# --- amount -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10 000,00 zł", 10000.0),
        ("10000.00 PLN", 10000.0),
        ("34.00 PLN", 34.0),
        ("1 234,5", 1234.5),
        ("1 234,56 zł", 1234.56),
        ("1 234,56 zł", 1234.56),
        ("1.234,56 zł", 1234.56),
        ("200,00 zł", 200.0),
        ("0,00", 0.0),
    ],
)
def test_amount_formaty(raw: str, expected: float) -> None:
    assert amount(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "", "zł", "12,34,56"])
def test_amount_nieprawidlowa_zwraca_none(raw: str) -> None:
    assert amount(raw) is None


# --- iban -------------------------------------------------------------------

IBAN_CYFRY = "68438223049992295262834736"


@pytest.mark.parametrize(
    "raw",
    [
        "PL68 4382 2304 9992 2952 6283 4736",
        "68-4382-2304-9992-2952-6283-4736",
        "PL68438223049992295262834736",
        IBAN_CYFRY,
    ],
)
def test_iban_normalizuje_do_26_cyfr(raw: str) -> None:
    assert iban(raw) == IBAN_CYFRY


@pytest.mark.parametrize(
    "raw",
    [
        "6843822304999229526283473",  # 25 cyfr
        "684382230499922952628347360",  # 27 cyfr
        "PL6843822304999229526283473X",
        "",
    ],
)
def test_iban_zla_dlugosc_zwraca_none(raw: str) -> None:
    assert iban(raw) is None


# --- digits / nip / krs / regon / pesel -------------------------------------


def test_digits_zostawia_same_cyfry() -> None:
    assert digits("123-456-78-90") == "1234567890"
    assert digits("PL 123") == "123"


@pytest.mark.parametrize("raw", ["abc", "", "--"])
def test_digits_brak_cyfr_zwraca_none(raw: str) -> None:
    assert digits(raw) is None


def test_nip_dziesiec_cyfr() -> None:
    assert nip("123-456-78-90") == "1234567890"
    assert nip("PL 9999284065") == "9999284065"


@pytest.mark.parametrize("raw", ["123456789", "12345678901", ""])
def test_nip_zla_dlugosc_zwraca_none(raw: str) -> None:
    assert nip(raw) is None


def test_krs_bez_zmian_gdy_dziesiec_cyfr() -> None:
    assert krs("9999405188") == "9999405188"


def test_krs_uzupelnia_zerami_wiodacymi() -> None:
    assert krs("123456") == "0000123456"
    assert krs("1") == "0000000001"


@pytest.mark.parametrize("raw", ["12345678901", "abc", ""])
def test_krs_zla_dlugosc_zwraca_none(raw: str) -> None:
    assert krs(raw) is None


def test_regon_dziewiec_i_czternascie_cyfr() -> None:
    assert regon("999642785") == "999642785"
    assert regon("12345678901234") == "12345678901234"


@pytest.mark.parametrize("raw", ["12345678", "1234567890", "12345678901234567", ""])
def test_regon_zla_dlugosc_zwraca_none(raw: str) -> None:
    assert regon(raw) is None


def test_pesel_jako_string() -> None:
    wynik = pesel("85071204278")
    assert wynik == "85071204278"
    assert isinstance(wynik, str)


def test_pesel_ze_spacjami() -> None:
    assert pesel("850 712 04278") == "85071204278"


def test_pesel_zachowuje_zera_wiodace() -> None:
    assert pesel("01234567890") == "01234567890"


@pytest.mark.parametrize("raw", ["8507120427", "850712042780", ""])
def test_pesel_zla_dlugosc_zwraca_none(raw: str) -> None:
    assert pesel(raw) is None


# --- bzp --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026/BZP 00551100", "2026/BZP00551100"),
        ("2026/BZP00551100", "2026/BZP00551100"),
        ("2026/BZP 00143067/01", "2026/BZP00143067/01"),
        ("2026/BZP00143067/01", "2026/BZP00143067/01"),
        ("2026/BZP00143067/03", "2026/BZP00143067/03"),
        ("2026/BZP 00143067 / 01", "2026/BZP00143067/01"),
    ],
)
def test_bzp_formaty(raw: str, expected: str) -> None:
    assert bzp(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "BZP 00551100",
        "2026/BZP0055110",  # 7 cyfr
        "2026-BZP00551100",
        "2026/BZP00551100/1",
        "",
    ],
)
def test_bzp_inny_format_zwraca_none(raw: str) -> None:
    assert bzp(raw) is None


# --- ted --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("383751-2025", "383751-2025"),
        ("2025/S 112-383751", "383751-2025"),
        ("2025/S112-383751", "383751-2025"),
        ("2025-OJS112-383751", "383751-2025"),
        ("2025-OJS 112-383751", "383751-2025"),
    ],
)
def test_ted_formaty(raw: str, expected: str) -> None:
    assert ted(raw) == expected


@pytest.mark.parametrize("raw", ["38375-2025", "abc", ""])
def test_ted_nierozpoznawalne_zwraca_none(raw: str) -> None:
    assert ted(raw) is None


# --- email ------------------------------------------------------------------


def test_email_wyluskuje_i_zmienia_na_male() -> None:
    assert email("Adres: Biuro@Poczta.Example, tel 123") == "biuro@poczta.example"


def test_email_z_bialymi_znakami() -> None:
    assert email("  kontakt@wozniakkancelaria.example  ") == "kontakt@wozniakkancelaria.example"


@pytest.mark.parametrize("raw", ["brak adresu", "", "a@b"])
def test_email_brak_adresu_zwraca_none(raw: str) -> None:
    assert email(raw) is None


# --- ws ---------------------------------------------------------------------


def test_ws_zwija_biale_znaki() -> None:
    assert ws("  Jan   Kowalski \n Nowak ") == "Jan Kowalski Nowak"


def test_ws_twarda_spacja() -> None:
    assert ws("a  b") == "a b"


def test_ws_bez_zmian() -> None:
    assert ws("bez zmian") == "bez zmian"


def test_ws_same_biale_znaki_zwraca_none() -> None:
    assert ws("   ") is None


# --- ocr_fix ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Belmoria Sp. z 0.0.", "Belmoria Sp. z o.o."),
        ("Belmoria sp. z o. o.", "Belmoria sp. z o.o."),
        ("Belmoria Sp.z o.o.", "Belmoria Sp. z o.o."),
        ("Belmoria sp.z 0.0", "Belmoria sp. z o.o."),
        ("Firma S.A", "Firma S.A."),
        ("Firma S.A.", "Firma S.A."),
    ],
)
def test_ocr_fix_formy_prawne(raw: str, expected: str) -> None:
    assert ocr_fix(raw) == expected


@pytest.mark.parametrize("raw", ["Kwota 10.00 zł", "Nr 10.00.5", "Kod 00100"])
def test_ocr_fix_nie_rusza_innych_zer(raw: str) -> None:
    assert ocr_fix(raw) == raw


def test_ocr_fix_pusty_zwraca_none() -> None:
    assert ocr_fix("") is None


# --- company ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"Kancelaria Sp. z 0.0."', "Kancelaria Sp. z o.o."),
        ("„Belmoria Rozwiązania S.A.”", "Belmoria Rozwiązania S.A."),
        ("  Aurelink   Automatyka S.A  ", "Aurelink Automatyka S.A."),
        (
            "Kancelaria Adwokacka Spółka z ograniczoną odpowiedzialnością",
            "Kancelaria Adwokacka Spółka z ograniczoną odpowiedzialnością",
        ),
        ("Firma 'ABC'", "Firma 'ABC'"),
        ("«Firma»", "Firma"),
    ],
)
def test_company(raw: str, expected: str) -> None:
    assert company(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", '""'])
def test_company_pusty_zwraca_none(raw: str) -> None:
    assert company(raw) is None


# --- rejestr ----------------------------------------------------------------


def test_rejestr_zawiera_wszystkie_normalizatory() -> None:
    assert set(NORMALIZERS) == {
        "date",
        "amount",
        "iban",
        "digits",
        "nip",
        "krs",
        "regon",
        "pesel",
        "bzp",
        "ted",
        "email",
        "ws",
        "ocr_fix",
        "company",
    }


@pytest.mark.parametrize("nazwa", sorted(NORMALIZERS))
def test_rejestr_pusty_wejscie_zwraca_none(nazwa: str) -> None:
    assert NORMALIZERS[nazwa]("") is None
