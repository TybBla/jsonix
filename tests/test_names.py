"""Testy normalizacji imion i nazwisk do mianownika (odw2json/extract/names.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from odw2json.extract.names import normalize_name, strip_titles

PAIRS = json.loads((Path(__file__).parent / "fixtures" / "names_pairs.json").read_text(encoding="utf-8"))


def _accuracy(split: str) -> tuple[float, list[tuple[str, str, str]]]:
    items = [p for p in PAIRS if p["split"] == split]
    errors = [(p["text"], normalize_name(p["text"]), p["gt"]) for p in items]
    errors = [e for e in errors if e[1] != e[2]]
    return 1 - len(errors) / len(items), errors


def test_fixture_nonempty_and_has_both_splits():
    assert {p["split"] for p in PAIRS} == {"dev", "holdout"}
    assert len(PAIRS) > 100


def test_train_pairs_dev_accuracy():
    acc, errors = _accuracy("dev")
    assert acc >= 0.95, errors


def test_train_pairs_holdout_accuracy():
    acc, errors = _accuracy("holdout")
    assert acc >= 0.90, errors


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Katarzynie Wiśniewskiej", "Katarzyna Wiśniewska"),
        ("Tomaszowi Zielińskiemu", "Tomasz Zieliński"),
        ("adw. Annę Nowak", "Anna Nowak"),
        ("r. pr. Jana Kowalskiego", "Jan Kowalski"),
        ("Piotrem Malinowskim", "Piotr Malinowski"),
    ],
)
def test_task_examples(text, expected):
    assert normalize_name(text) == expected


# Odmienione formy imion i nazwisk z danych treningowych (dane UZP mają je w tekście tylko
# w mianowniku) oraz typowe nazwiska polskie - formy pisane ręcznie, nie generowane regułami.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # dopełniacz / biernik (mężczyźni)
        ("Bartosza Szymańskiego", "Bartosz Szymański"),
        ("Cezarego Wierzbickiego", "Cezary Wierzbicki"),
        ("Ignacego Sadowskiego", "Ignacy Sadowski"),
        ("Norberta Szulca", "Norbert Szulc"),
        ("Ryszarda Lewandowskiego", "Ryszard Lewandowski"),
        ("Marka Rutkiewicza", "Marek Rutkiewicz"),
        ("Grzegorza Dudka", "Grzegorz Dudek"),
        ("Pawła Wieczorka", "Paweł Wieczorek"),
        ("Łukasza Sikory", "Łukasz Sikora"),
        ("Rafała Czajki", "Rafał Czajka"),
        ("Tadeusza Nowaka", "Tadeusz Nowak"),
        ("Kamila Bąka", "Kamil Bąk"),
        ("Michała Wilka", "Michał Wilk"),
        ("Jerzego Białego", "Jerzy Biały"),
        ("Antoniego Kowalczyka", "Antoni Kowalczyk"),
        # celownik
        ("Sławomirowi Jabłońskiemu", "Sławomir Jabłoński"),
        ("Zbigniewowi Dobrowolskiemu", "Zbigniew Dobrowolski"),
        ("Dariuszowi Pietrzakowi", "Dariusz Pietrzak"),
        ("Markowi Dudkowi", "Marek Dudek"),
        ("Łukaszowi Sikorze", "Łukasz Sikora"),
        ("Rafałowi Czajce", "Rafał Czajka"),
        ("Halinie Walczak", "Halina Walczak"),
        ("Aleksandrze Marciniak", "Aleksandra Marciniak"),
        ("Natalii Góreckiej", "Natalia Górecka"),
        ("Patrycji Furman", "Patrycja Furman"),
        ("Agnieszce Kurek", "Agnieszka Kurek"),
        ("Barbarze Piotrowskiej", "Barbara Piotrowska"),
        ("Elżbiecie Woźniak", "Elżbieta Woźniak"),
        ("Oldze Baran", "Olga Baran"),
        ("Ewie Lis", "Ewa Lis"),
        # dopełniacz (kobiety)
        ("Magdaleny Wróblewskiej", "Magdalena Wróblewska"),
        ("Joanny Stępień", "Joanna Stępień"),
        ("Iwony Kucharskiej", "Iwona Kucharska"),
        ("Klaudii Bartoszewicz", "Klaudia Bartoszewicz"),
        ("Agnieszki Sikory", "Agnieszka Sikora"),
        # narzędnik
        ("Krzysztofem Nowickim", "Krzysztof Nowicki"),
        ("Henrykiem Ostrowskim", "Henryk Ostrowski"),
        ("Robertem Kurkiem", "Robert Kurek"),
        ("Leszkiem Jabłońskim", "Leszek Jabłoński"),
        ("Andrzejem Wawrzyniakiem", "Andrzej Wawrzyniak"),
        ("Wojciechem Majewskim", "Wojciech Majewski"),
        ("Celiną Ostrowską", "Celina Ostrowska"),
        ("Teresą Sadowską", "Teresa Sadowska"),
        ("Martą Mazur", "Marta Mazur"),
        # biernik (kobiety)
        ("Weronikę Jabłońską", "Weronika Jabłońska"),
        ("Grażynę Zielińską", "Grażyna Zielińska"),
        ("Marię Sikorę", "Maria Sikora"),
        # niejednoznaczne imię: C. żeński albo Ms. męski - rozstrzyga nazwisko
        ("Mirosławie Rutkowskiej", "Mirosława Rutkowska"),
        ("Michałowi Wróblowi", "Michał Wróbel"),
    ],
)
def test_inflected_forms(text, expected):
    assert normalize_name(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("adw. Jan Kowalski", "Jan Kowalski"),
        ("r. pr. Anna Nowak", "Anna Nowak"),
        ("radcy prawnemu Tomaszowi Zielińskiemu", "Tomasz Zieliński"),
        ("radca prawny Piotr Zalewski", "Piotr Zalewski"),
        ("adwokatowi Janowi Nowakowi", "Jan Nowak"),
        ("mec. Natalia Górecka", "Natalia Górecka"),
        ("Pani Iwonie Zawadzkiej", "Iwona Zawadzka"),
        ("Panu Kamilowi Olszewskiemu", "Kamil Olszewski"),
        ("dr Igor Majewski", "Igor Majewski"),
        ("dr hab. Anną Nowak", "Anna Nowak"),
        ("  Jan   Kowalski ", "Jan Kowalski"),
    ],
)
def test_titles_removed(text, expected):
    assert normalize_name(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # nazwisko dwuczłonowe
        ("Annie Nowak-Jeziorańskiej", "Anna Nowak-Jeziorańska"),
        ("Anna Nowak-Jeziorańska", "Anna Nowak-Jeziorańska"),
        ("Janowi Kowalskiemu-Nowakowi", "Jan Kowalski-Nowak"),
        # nazwiska żeńskie zakończone spółgłoską - nieodmienne
        ("Katarzynie Kowalczyk", "Katarzyna Kowalczyk"),
        # mianownik bez zmian, także niezgodność rodzaju w danych UZP
        ("Klaudia Dobrowolski", "Klaudia Dobrowolski"),
        ("Jolanta Zajkowski", "Jolanta Zajkowski"),
        ("Cezary Kaczmark", "Cezary Kaczmark"),
        ("Bartosz Szymanski", "Bartosz Szymanski"),
        # imiona obcojęzyczne / nieznane - bez zmian
        ("John Smith", "John Smith"),
        ("Jean-Pierre Dupont", "Jean-Pierre Dupont"),
        # dwa imiona
        ("Annie Marii Kowalskiej", "Anna Maria Kowalska"),
        # Daniela/Józefa: mianownik żeński albo dopełniacz męski - rozstrzyga nazwisko
        ("Daniela Kowalska", "Daniela Kowalska"),
        ("Daniela Kowalskiego", "Daniel Kowalski"),
        ("Józefa Nowak", "Józefa Nowak"),
        # wielkie litery: GT UZP ma zawsze postac tytulowa („Jan Kowalski”), nigdy „JAN KOWALSKI”
        ("JANA KOWALSKIEGO", "Jan Kowalski"),
        # puste / pojedyncze słowo
        ("", ""),
        ("Kowalski", "Kowalski"),
    ],
)
def test_edge_cases(text, expected):
    assert normalize_name(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("JAN NOWAK", "Jan Nowak"),
        ("ANNA KOWALSKA", "Anna Kowalska"),
        ("ŁUKASZ ŻÓŁTOWSKI", "Łukasz Żółtowski"),
        ("ANNA NOWAK-JEZIORAŃSKA", "Anna Nowak-Jeziorańska"),
        ("JEAN-PIERRE DUPONT", "Jean-Pierre Dupont"),
        ("Jan NOWAK", "Jan Nowak"),
        ("Anna KOWALSKA", "Anna Kowalska"),
        ("JAN Nowak", "Jan Nowak"),
        ("ADW. JAN NOWAK", "Jan Nowak"),
        ("r. pr. ANNA NOWAK", "Anna Nowak"),
        ("KATARZYNIE WIŚNIEWSKIEJ", "Katarzyna Wiśniewska"),
        ("Tomaszowi ZIELIŃSKIEMU", "Tomasz Zieliński"),
        ("JOHN SMITH", "John Smith"),
        ("KOWALSKI", "Kowalski"),
        ("J. KOWALSKI", "J. Kowalski"),
        ("Jan McDonald", "Jan McDonald"),
    ],
)
def test_uppercase_names_become_title_case_before_inflection(text, expected):
    assert normalize_name(text) == expected


def test_strip_titles():
    assert strip_titles("r.pr. Jan Kowalski") == "Jan Kowalski"
    assert strip_titles("adw. dr Anna Nowak") == "Anna Nowak"
    assert strip_titles("Panią Anną Nowak") == "Anną Nowak"
