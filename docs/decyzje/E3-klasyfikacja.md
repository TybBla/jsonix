# E3 — Klasyfikacja typu dokumentu: podejście, pomiary, ograniczenia

Status: raport T2 (odporność). Dotyczy klasyfikatora z T1 (`odw2json/classify/`). Typ rozpoznawany wyłącznie
z treści; nazwa pliku i katalog nie są używane.

## Podejście
Dla każdego typu z `config/doctypes/*.yaml` liczony jest wynik z cech zapisanych w sekcji `classify:`
(silnik: `odw2json/classify/features.py`, bez zmian kodu przy nowym typie):

- `strong` / `weak` / `negative` — obecność frazy (wagi domyślne +2 / +1 / −3), na tekście znormalizowanym
  (małe litery, bez polskich znaków — błędy OCR ł→l, Ę→E są neutralne);
- `title` — fraza w nagłówku (pierwsze `header_chars` znaków, rozstrzelone litery zwinięte), +4 raz;
- `patterns` — regex z wagą (np. numer rachunku 26 cyfr w pobliżu kwoty: +4; `zarzut nr \d+`: +3);
- `required_any` — bez trafienia typ odpada (przelew wymaga IBAN-u);
- `min_score`, `min_margin` — poniżej typ nieznany (`None`).
Wygrywa typ o najwyższym wyniku; `confidence = margines * nasycenie` (szczegóły w docstringu `classify/__init__.py`).

### Progi (z YAML) i uzasadnienie
| Typ | min_score | min_margin | header_chars | Uzasadnienie |
|---|---|---|---|---|
| odwolanie | 8.0 | 2.0 | 1500 | pojedyncze słowa domenowe (np. w wyroku KIO) nie wystarczają; tytuł stoi po blokach adresowych, stąd dłuższy nagłówek |
| pelnomocnictwo | 5.0 | 1.0 | 600 | krótki dokument, tytuł na początku |
| przelew | 6.0 | 2.0 | 600 | ogólne słowa (rachunek, kwota) tylko +1, bo występują w ogłoszeniach/broszurach; wymagany IBAN |

## Macierz pomyłek (klasyfikacja tekstowa, bez OCR; `python -m eval.gate --split all --source tekst`, exit 0, `classification_errors=0` dev i holdout)
Wiersz = oczekiwany, kolumna = wynik.

| dev | odwolanie | pelnomocnictwo | przelew | None |
|---|---|---|---|---|
| odwolanie | 46 | 0 | 0 | 0 |
| pelnomocnictwo | 0 | 46 | 0 | 0 |
| przelew | 0 | 0 | 46 | 0 |
| negatyw | 0 | 0 | 0 | 3 |

| holdout | odwolanie | pelnomocnictwo | przelew | None |
|---|---|---|---|---|
| odwolanie | 14 | 0 | 0 | 0 |
| pelnomocnictwo | 0 | 14 | 0 | 0 |
| przelew | 0 | 0 | 14 | 0 |
| negatyw | 0 | 0 | 0 | 1 |

Pula negatywów (`data/train/negatywne`, 12 plików): 12/12 → `None`.

### Syntetyki (`tests/fixtures/classify`, 9 negatywów + 1 pozytyw) — **8 z 9 negatywów klasyfikowanych błędnie**
| Fixture | Oczekiwano | Wynik | Wyniki (odw / pełn / przel) |
|---|---|---|---|
| neg_wyrok_kio | None | odwolanie | 14 / −2 / −5 |
| neg_zawiadomienie_o_wyborze | None | odwolanie | 14 / 1 / −3 |
| neg_postanowienie_kio_umorzenie | None | odwolanie | 11 / 1 / −3 |
| neg_ogloszenie_bzp | None | odwolanie | 11 / −2 / 3 |
| neg_swz_wadium | None | odwolanie | 13 / 4 / 2 |
| neg_wezwanie_do_uzupelnienia | None | odwolanie | 12 / 1 / 0 |
| neg_pismo_do_zamawiajacego | None | odwolanie | 8 / 1 / −2 |
| neg_faktura_vat | None | przelew | 0 / 0 / 9 |
| neg_umowa_zamowienie | None | None (margines 1 < 2) | 9 / 3 / 8 |
| pos_przelew_wadium | przelew | przelew | 0 / 0 / 24 |

Decyzja o `pos_przelew_wadium`: typ dokumentu wynika z **formy** (potwierdzenie przelewu bankowego), nie z celu
płatności; potwierdzenie wpłaty wadium jest więc pozytywem `przelew`. Wadium w SWZ/ogłoszeniu/umowie (opis zasad,
numer rachunku zamawiającego) to natomiast negatyw.

### Warianty pozytywów (prawdziwe teksty dev: przyklad_01, 05, 12 × 3 typy)
Warianty: tylko 1. strona; szum OCR (ł→l, ą→a, ę→e, Ę→E, ó→o, …; 0 zamiast 'o' w 3% liter, seed stały); tytuł małymi
literami; tytuł rozstrzelony; łamanie wiersza co ~40 znaków. **Wszystkie 45 wariantów przechodzą** (4 pominięte:
odwołania 05/12 nie mają osobnej linii tytułowej, więc warianty tytułowe nie mają zastosowania).

## Marginesy decyzji
Najniższy wynik/margines prawdziwego pozytywu vs najwyższy wynik negatywu (pula UZP, bez syntetyków):

| Typ | najniższy pozytyw (wynik / margines nad drugim) | najwyższy negatyw z puli | min_score |
|---|---|---|---|
| odwolanie | 11 (holdout, przyklad_59) / 14; dev 15 / 16 | 6 (KIO_KIO 2617-21 — wyrok) | 8 |
| pelnomocnictwo | 7 (przyklad_02, rozstrzelony tytuł) / 5 | 3 (TED) | 5 |
| przelew | 11 (przyklad_17) / 9 | 4 (Broszura JPK) | 6 |

Na prawdziwych danych odstęp jest wyraźny (odwołanie 6 vs 11; przelew 4 vs 11; pełnomocnictwo 3 vs 7). Syntetyki
pokazują, że ten odstęp nie wynika z cech pozwalających odróżnić odwołanie od innych pism KIO/zamówieniowych.

## Znane ograniczenia (8 xfail strict w `tests/test_classify_robustness.py`)
Główna przyczyna: cecha `title: ["odwolanie"]` szuka frazy w pierwszych **1500 znakach**, więc dowolne pismo
z zakresu zamówień publicznych, które w nagłówku/pierwszym akapicie ma słowo „odwołanie/odwołania” (+4), razem z
`odwolujacy`, `zarzut`, `krajowej izby odwolawczej` (+2 każde) i `zamawiajacy` (+1) przekracza `min_score` 8.
Frazy `negative` („wyrok”, „postanowienie”, „ogloszenie o zamowieniu”: −3) nie wystarczają (wyrok KIO: 14 mimo −3).
Drugi problem: faktura z IBAN-em i kwotą spełnia `required_any` i wzorzec strukturalny przelewu (+4), a
„przelew”/„kwota”/„rachunek”/„tytul”/„pln” dobijają do 9 > 6.

Rekomendacje dla T1/orkiestratora (nie wprowadzane w T2): (1) `title` dla odwołania wymagać jako **osobnej linii**
(regex `^\s*odwolanie\s*$`) zamiast podciągu w 1500 znakach; (2) większa kara dla nagłówków innych dokumentów
(„wyrok”, „postanowienie”, „zawiadomienie”, „wezwanie”, „faktura”, „specyfikacja”, „umowa”) wykrywanych w
pierwszych liniach; (3) dla przelewu nagłówek/tytuł jako wymagana cecha albo `negative: ["faktura", "nip", "vat"]`;
(4) podnieść `min_score` odwołania lub wymagać wzorca strukturalnego (`odwolujacy:`/`zarzut nr`) razem z tytułem.
Każda zmiana: najpierw weryfikacja na dev, holdout raz na końcu.

Ograniczenia testów: syntetyki są pisane ręcznie (zawierają celowo dużo słów domenowych), więc zawyżają trudność
względem typowych pism; warianty OCR to symulacja, nie prawdziwy OCR; skany sprawdza osobny test `slow` z T1.

## Jak dodać nowy typ dokumentu
1. Dodaj `config/doctypes/<id>.yaml` z `classify:` (title, strong/weak/negative, patterns, required_any,
   min_score, min_margin) — bez zmian kodu (opis: `docs/nowy-typ-dokumentu.md`).
2. Dodaj szablon wyniku w `config/schemas/` i wpis w `output_template`.
3. Dodaj 1–2 syntetyczne negatywy „podchwytliwe” dla nowego typu (`tests/fixtures/classify/neg_*.txt`) i
   pozytyw `pos_<id>_*.txt` (nazwa po prefiksie `pos_` = id typu).
4. Dodaj typ do `REAL_DOCS`/`TITLE_RE` w teście odporności, jeśli są dla niego dane treningowe.
5. Uruchom `python -m pytest tests/test_classify_robustness.py` oraz bramkę (`--split dev`, na końcu `holdout`).
