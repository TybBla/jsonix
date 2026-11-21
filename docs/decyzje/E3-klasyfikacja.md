# E3 — Klasyfikacja typu dokumentu: podejście, pomiary, ograniczenia

Status: raport T2 (odporność) + utwardzenie T3. Dotyczy klasyfikatora z T1 (`odw2json/classify/`). Typ rozpoznawany wyłącznie
z treści; nazwa pliku i katalog nie są używane.

## Podejście
Dla każdego typu z `config/doctypes/*.yaml` liczony jest wynik z cech zapisanych w sekcji `classify:`
(silnik: `odw2json/classify/features.py`, bez zmian kodu przy nowym typie):

- `strong` / `weak` / `negative` — obecność frazy (wagi domyślne +2 / +1 / −3), na tekście znormalizowanym
  (małe litery, bez polskich znaków — błędy OCR ł→l, Ę→E są neutralne);
- `title` — fraza w nagłówku (pierwsze `header_chars` znaków, rozstrzelone litery zwinięte), +4 raz. Od T3
  `title_mode: line` (wszystkie trzy typy): fraza musi być **tytułem** — linią nagłówka (po zdjęciu interpunkcji)
  o długości <= `title_line_max_chars`, w której fraza zajmuje >= `title_line_min_cover` długości; fraza
  wielowyrazowa pasuje też bez spacji (OCR gubi odstępy). Domyślne `anywhere` zostaje dla zgodności wstecznej;
- `foreign_titles` (T3, globalnie w `config/classify.yaml`) — kara −10 dla **wszystkich** typów, gdy linia
  nagłówka (pierwsze 600 znaków) **zaczyna się** od frazy typu „wyrok”, „postanowienie”, „sygn. akt”, „ogłoszenie o”,
  „zawiadomienie”, „faktura”, „wezwanie”, „specyfikacja”, „umowa”, „protokół”;
- `patterns` — regex z wagą (np. numer rachunku 26 cyfr w pobliżu kwoty: +4; `zarzut nr \d+`: +3);
- `required_any` — bez trafienia typ odpada; wpis to fraza, `re:<regex>`, `@title` (trafił tytuł) albo grupa
  `{all_of: [...]}` (T3);
- `min_score`, `min_margin` — poniżej typ nieznany (`None`).
Wygrywa typ o najwyższym wyniku; `confidence = margines * nasycenie` (szczegóły w docstringu `classify/__init__.py`).

### Progi (z YAML) i uzasadnienie
| Typ | min_score | min_margin | header_chars | title_mode (max znaków / min pokrycie) | Uzasadnienie |
|---|---|---|---|---|---|
| odwolanie | 8.0 | 2.0 | 1500 | line (60 / 0,6) | tytuł stoi po blokach adresowych, stąd dłuższy nagłówek; wymagane: tytuł-linia albo `odwolujacy:` albo `zarzut nr N` (same słowa domenowe z pisma/wyroku nie wystarczają) |
| pelnomocnictwo | 5.0 | 1.0 | 600 | line (60 / 0,5) | krótki dokument, tytuł na początku; 0,5, bo „PEŁNOMOCNICTWO PROCESOWE” zajmuje 58% linii |
| przelew | 6.0 | 2.0 | 600 | line (80 / 0,4) | tytuł bywa z nazwą banku („Bank X potwierdzenie przelewu krajowego”); wymagane: IBAN i (tytuł albo etykiety nadawca + odbiorca); słowa faktury (`nabywca`, `sprzedawca`, `nip nabywcy`, `stawka vat`, `do zaplaty`) −3 każde |

Etykiety slipu bankowego (grupa `required_any` przelewu) są szerokie celowo, bo skany wydruków bankowych nie mają
linii „Potwierdzenie…”: nadawca = `z rachunku|rachunek nadawcy|rachunek zleceniodawcy|rachunek obciazany|zleceniodawc|nadawc|numer transakcji`,
odbiorca = `na rachunek|beneficjent|odbiorc|kontrahent` (w dev 6 skanów potwierdzeń przechodzi wyłącznie przez tę grupę).

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

### Syntetyki (`tests/fixtures/classify`, 9 negatywów + 1 pozytyw) — po T3 **wszystkie poprawne**
Przed T3 (T2): 8 z 9 negatywów klasyfikowanych błędnie (osiem `xfail strict`). Po T3 lista `KNOWN_XFAIL` jest pusta.
| Fixture | Oczekiwano | Wynik T2 (odw / pełn / przel) | Wynik T3 (odw / pełn / przel) |
|---|---|---|---|
| neg_wyrok_kio | None | odwolanie (14 / −2 / −5) | None (0 / −12 / −15) |
| neg_zawiadomienie_o_wyborze | None | odwolanie (14 / 1 / −3) | None (0 / −9 / −13) |
| neg_postanowienie_kio_umorzenie | None | odwolanie (11 / 1 / −3) | None (−3 / −9 / −13) |
| neg_ogloszenie_bzp | None | odwolanie (11 / −2 / 3) | None (−3 / −12 / −7) |
| neg_swz_wadium | None | odwolanie (13 / 4 / 2) | None (−1 / −6 / −8) |
| neg_wezwanie_do_uzupelnienia | None | odwolanie (12 / 1 / 0) | None (−2 / −9 / −10) |
| neg_pismo_do_zamawiajacego | None | odwolanie (8 / 1 / −2) | None (8 / 1 / −2; **wykluczone przez `required_any`**: brak tytułu-linii, `odwolujacy:` i `zarzut nr N`) |
| neg_faktura_vat | None | przelew (0 / 0 / 9) | None (−10 / −10 / −10) |
| neg_umowa_zamowienie | None | None (9 / 3 / 8, margines 1 < 2) | None (−5 / −7 / −2) |
| pos_przelew_wadium | przelew | przelew (0 / 0 / 24) | przelew (0 / 0 / 24) |

Uwaga: `neg_pismo_do_zamawiajacego` ma surowy wynik odwołania 8 = `min_score`; chroni go wyłącznie wymaganie
strukturalne (`required_any`), nie próg. Pismo z „Odwołujący:” w treści byłoby błędnie uznane za odwołanie — to
świadomy kompromis (takie pismo jest praktycznie odwołaniem).

Decyzja o `pos_przelew_wadium`: typ dokumentu wynika z **formy** (potwierdzenie przelewu bankowego), nie z celu
płatności; potwierdzenie wpłaty wadium jest więc pozytywem `przelew`. Wadium w SWZ/ogłoszeniu/umowie (opis zasad,
numer rachunku zamawiającego) to natomiast negatyw.

### Warianty pozytywów (prawdziwe teksty dev: przyklad_01, 05, 12 × 3 typy)
Warianty: tylko 1. strona; szum OCR (ł→l, ą→a, ę→e, Ę→E, ó→o, …; 0 zamiast 'o' w 3% liter, seed stały); tytuł małymi
literami; tytuł rozstrzelony; łamanie wiersza co ~40 znaków. **Wszystkie 45 wariantów przechodzą** (4 pominięte:
odwołania 05/12 nie mają osobnej linii tytułowej, więc warianty tytułowe nie mają zastosowania).

## Marginesy decyzji (po T3)
Najniższy wynik prawdziwego pozytywu vs najwyższy wynik negatywu, na dev + holdout, tekst + skany OCR, pula UZP i
syntetyki razem („wykluczony” = typ odpadł przez `required_any`, więc wynik surowy nie decyduje):

| Typ | najniższy pozytyw | najwyższy negatyw (typ nie wykluczony) | najwyższy negatyw — wynik surowy | min_score | min. przewaga nad drugim typem (pozytywy) |
|---|---|---|---|---|---|
| odwolanie | 11 (holdout przyklad_59; skan dev 0009 też 11) | 0 (neg_wyrok_kio; rzeczywiste wyroki/ogłoszenia < 0) | 8 (neg_pismo_do_zamawiajacego, wykluczony) | 8 | 10 (skan odwolania/0004) |
| pelnomocnictwo | 7 (przyklad_32) | 3 (skan odwołania 0010/0007/0006) | 3 | 5 | 7 |
| przelew | 10 (skan potwierdzenia/0008) | brak — żaden nie-przelew nie spełnia `required_any` | 1 (przyklad_50/pełnomocnictwo, Broszura JPK) | 6 | 9 |

Dla porównania przed T3 (tylko prawdziwe dane, bez syntetyków): odwolanie 11 vs 6, pelnomocnictwo 7 vs 3, przelew 11 vs 4.
Po T3 negatywy zdobywają ≤ 1 pkt (przelew), ≤ 3 pkt (pełnomocnictwo) albo są wykluczone/ujemne (odwołanie), więc odstęp
nie zależy już od jednego progu.

Potwierdzenia po zmianach: `python -m pytest -q` → 616 passed, 4 skipped, exit 0;
`python -m eval.gate --split all --source tekst` → `classification_errors=0`, negatywy 100% (dev i holdout), exit 0;
`python -m eval.gate --split all --source skan` → `classification_errors=0`, negatywy 100%, exit 0.
(Baseline w `eval/` pochodzi sprzed E3 — wskazuje 5/2 błędów klasyfikacji; nie był aktualizowany.)

## Znane ograniczenia i historia (T2 → T3)
T2 zmierzył 8 z 9 syntetycznych negatywów klasyfikowanych błędnie. Przyczyny i ich usunięcie w T3:

1. `title` szukany jako podciąg w 1500 znakach → „odwołanie” w pierwszym akapicie dowolnego pisma dawało +4.
   Naprawa: `title_mode: line` (tytuł = osobna krótka linia, spójne z rekomendacją (1) z T2).
2. Wyrok/postanowienie/ogłoszenie/zawiadomienie/SWZ/wezwanie/umowa zawierają słowa domenowe. Naprawa: globalna kara
   `foreign_titles` za nagłówek obcego dokumentu (rekomendacja (2)).
3. Faktura z IBAN-em i kwotą spełniała `required_any` + wzorzec strukturalny przelewu. Naprawa: IBAN **i** (tytuł
   albo etykiety nadawca + odbiorca) oraz `negative` faktury (rekomendacja (3)).
4. Pismo bez tytułu z samymi słowami domenowymi (8 = `min_score`). Naprawa: odwołanie wymaga tytułu-linii albo
   `odwolujacy:` albo `zarzut nr N` (rekomendacja (4)).

Pozostałe ograniczenia:
- Kara `foreign_titles` jest miękka (−10): dokument o bardzo wielu cechach (np. odwołanie z sygn. akt w nagłówku)
  nadal przejdzie. To celowe — twarde odrzucenie raziłoby odwołania zaczynające się od „Sygn. akt …”.
- Skanowe slipy bankowe bez tytułu są rozpoznawane po etykietach (nadawca/odbiorca + IBAN); wydruk o zupełnie innych
  etykietach przejdzie tylko z tytułem. Dodając nowy format banku, dopisz jego etykiety do grupy w `przelew.yaml`.
- Syntetyki są pisane ręcznie (celowo dużo słów domenowych), warianty OCR to symulacja; skany sprawdza test `slow`.
- Strojenie T3 na dev + 10 fixture’ach T2; holdout sprawdzony raz po ustaleniu konfiguracji (0 błędów).

## Jak dodać nowy typ dokumentu
1. Dodaj `config/doctypes/<id>.yaml` z `classify:` (title, strong/weak/negative, patterns, required_any,
   min_score, min_margin) — bez zmian kodu (opis: `docs/nowy-typ-dokumentu.md`).
2. Dodaj szablon wyniku w `config/schemas/` i wpis w `output_template`.
3. Dodaj 1–2 syntetyczne negatywy „podchwytliwe” dla nowego typu (`tests/fixtures/classify/neg_*.txt`) i
   pozytyw `pos_<id>_*.txt` (nazwa po prefiksie `pos_` = id typu).
4. Dodaj typ do `REAL_DOCS`/`TITLE_RE` w teście odporności, jeśli są dla niego dane treningowe.
5. Uruchom `python -m pytest tests/test_classify_robustness.py` oraz bramkę (`--split dev`, na końcu `holdout`).

## Zmiana T4: szerszy `required_any` odwołania
Prawdziwe odwołanie nie musi mieć etykiety „Odwołujący:” (bywa „Wykonawca:”), osobnej linii tytułu „ODWOŁANIE”
ani zarzutów „Zarzut nr N” (bywa „Zarzut 1.”). Taki tekst miał wynik 9 ≥ `min_score` 8, ale odpadał na `required_any`.
`required_any` rozszerzono o akt wniesienia (`wnosze odwolanie`, `wnosimy odwolanie`, `niniejszym wnosze odwolanie`)
oraz o numerację zarzutów bez „nr” (`zarzut\s*(nr\s*)?\d+`). Pisma do zamawiającego i wyroki KIO nie zawierają aktu
wniesienia ani numerowanych zarzutów — negatywy bez zmian (test `test_letter_mentioning_odwolanie_without_filing_act_is_unknown`).
Cyfry rzymskie pominięto celowo („zarzut i …” to spójnik).
