# eval - ocena F1

Liczy TP/TN/FP/FN na poziomie pol (zasady organizatora) i F1 = 2TP/(2TP+FP+FN).

```
python -m eval.score --pred output --gt data/train [--threshold 0.8] [--json raport.json] [--worst 10]
```

Predykcja `output/<case>/<nazwa>.json` jest porownywana z GT dla `<nazwa>.pdf` (sprawy moga lezec w
podkatalogach, np. `skany/odwolania/0001/0001.pdf`; sciezki wzgledne sa zachowane):
- GT to `<nazwa>.json` w tym samym katalogu, jesli istnieje; w przeciwnym razie mapowanie `GT_NAME_FOR_PDF`
  (`potwierdzenie_przelewu.pdf` -> `przelew.json`); `gt_path_for_pdf(pdf)` zwraca sciezke albo `None`;
- **typ dokumentu w raporcie** to typ z rejestru (`config/doctypes`), ktorego szablon ma najwiecej kluczy
  najwyzszego poziomu wspolnych z GT (`infer_doc_type(gt, registry)`; remis albo brak wspolnych kluczy =
  `None`, wtedy nazwa pliku GT jak dawniej). Nazwa pliku (np. `0001`) nie decyduje o typie;
- PDF-y bez GT (np. `negatywne/`) to negatywy: poprawny wynik to brak pliku JSON (pusty plik = brak).

Zrodlo dokumentu (`tekst` / `skan`): `doc_source(pred_root, rel)` czyta `<pred>/.trace/<rel>.trace.json` i
zwraca `skan`, gdy jest tam `ocr_used: true` (czyli ingest uzyl OCR), inaczej `tekst` (takze przy braku trace).
`score_dirs(..., sources={rel: zrodlo})` nadpisuje odczyt z trace (uzywa tego bramka). Raport ma
`by_source`, `by_type_source` (`typ/zrodlo`, bez negatywow) i `docs_by_source`.

Zasady:
- TP: wartosc jest u nas i zgadza sie z GT; TN: null/brak po obu stronach;
  FP: wartosc tylko u nas albo rozna od GT; FN: brak u nas, jest w GT.
- Dlugie pola wg UZP (Discord 21.11, 13:26): `Odwolujacy[].nazwa`, `Zamawiajacy[].nazwa`, `Odwolujacy[].pelnomocnik.nazwa`, `ZamowieniePubliczne.tytul`, `przelew_bankowy.tytul` — podobienstwo >= 0.8 (rapidfuzz ratio, bez wielkosci liter). Pozostale pola (w tym imiona, `mocodawca[].data.nazwa`, `czynnosc_opis`) — dokladnie.
- Listy dopasowywane po tresci (potwierdzone przez UZP).
- Pozostale pola: rowno po usunieciu nadmiarowych spacji, z uwzglednieniem wielkosci liter;
  liczby porownywane numerycznie (`10000 == 10000.0`); `"123"` != `123` (flaga `--lenient-types` to wylacza).
- Listy obiektow: elementy parowane zachlannie wg podobienstwa tresci (kolejnosc nie ma znaczenia);
  nadmiarowe elementy daja FP, brakujace FN/TN.
- Brak pliku predykcji przy istniejacym GT: wszystkie niepuste pola GT to FN.
- Dodatkowe opcje: `--casefold-exact` (pola dokladne bez wielkosci liter).

Testy: `python -m pytest -q tests/test_score.py`

## Bramka regresji F1 (`eval.gate`)

```
python -m eval.gate [--split dev|holdout|all] [--source tekst|skan|all] [--update-baseline] [--tolerance 0.0] [--json PATH]
```

Dla wybranego splitu (`data/splits.yaml`) kopiuje PDF-y spraw + wszystkie negatywy (`data/train/negatywne`)
do katalogu tymczasowego, uruchamia `pipeline.run`, liczy `eval.score.score_dirs` tylko dla tych dokumentow,
sprawdza kazdy wynik (`schema.validate_output` dla pozytywow, `is_unknown_output` dla negatywow)
i porownuje z `eval/baseline.json` (osobna sekcja `dev` i `holdout`). `all` = oba splity osobno.

Baseline per split: `f1`, `precision`, `recall`, `f1_by_type`, `f1_by_field`, `neg_correct`/`neg_total`,
`schema_errors`, `classification_errors`, `pipeline_errors`, `updated`, `commit`, a od E2b takze
`by_source` (`tekst`/`skan`: `f1`, `precision`, `recall`, `tp`, `fp`, `fn`, `tn`, `docs`) i
`f1_by_type_source` (`odwolanie/skan`, ...). `by_source[<zrodlo>].f1` i `f1_by_type_source[...]` sa bramkowane
jak `f1_by_type` (spadek > tolerancja = regresja); klucze nieobecne w starym baseline to `new`, nieobecne w
biezacym wyniku to `gone` (bez bledu).

**Zrodlo dokumentu** to `skan`, gdy ingest faktycznie uzyl OCR (`doc.ocr_used`), inaczej `tekst`. Trace
pipeline'u nie zapisuje dzis `ocr_used`, wiec bramka zbiera te informacje sama (opakowanie `ingest.load`
na czas przebiegu) i przekazuje je do `score_dirs`. Skan, ktorego OCR nic nie rozpoznal, wpada wiec do `tekst`
(widac to jako spadek F1 tekstowych); narzedzie pokrycia lapie taki przypadek heurystyka z warstwa tekstu.

**Filtr `--source`** (domyslnie `all`; `run_gate(..., source=...)`): ogranicza sprawy i negatywy PRZED
uruchomieniem pipeline'u (OCR nie jest uruchamiany do filtrowania):
- `tekst` = sprawy spoza `skany/` (np. `przyklad_*`) + negatywy z warstwa tekstu,
- `skan` = sprawy `skany/...` + negatywy bez warstwy tekstu (surowa ekstrakcja `pypdfium2` < 30 znakow),
- `all` = wszystko (jak dawniej).
Dla `--source tekst|skan` sekcja baseline nazywa sie `<split>@<source>` (`dev@tekst`, `dev@skan`,
`holdout@tekst`...), a wynik trafia do `output/.gate/<split>@<source>.json`; `--source all` uzywa sekcji
`dev` / `holdout`. Dzieki temu CI moze bramkowac sam tekst (`--split dev --source tekst`) niezaleznie od
pelnej bramki. CI (`.github/workflows/ci.yml`) uruchamia bramke z `--source tekst` (dev i holdout);
bramka skanow (`--source skan`, wymaga OCR, ok. 4-5 min na zimno) jest uruchamiana lokalnie.
Brak sekcji = kod 2 (jak zawsze).

Kody wyjscia:
- `0` - brak regresji,
- `1` - regresja (spadek f1 ogolnego / per typ / per pole albo odsetka poprawnych negatywow o wiecej niz
  `tolerance` + 1e-9; wzrost `classification_errors`) albo awaria (`schema_errors` > 0, wyjatek pipeline),
- `2` - blad uzycia albo brak sekcji splitu w baseline (bez `--update-baseline`).

Pola/typy nieobecne w baseline sa raportowane jako `new` (nie sa bledem). `classification_errors` to negatyw
z niepustym wynikiem albo pozytyw z `{}` / kluczami innego typu. Negatywy sprawdzane sa scisle na SUROWYM
pliku wg `unknown_output` z `config/app.yaml` (`empty_object`: plik z `{}`; `empty_file`: pusty plik;
`none`: brak pliku); brak pliku, `null`, niepoprawny JSON czy niepusty obiekt to blad klasyfikacji
(niepoprawny JSON takze blad schematu). Brakujacy lub nieparsowalny wynik pozytywu to blad schematu.
Baseline przechowuje `classification_error_files` (posortowane sciezki); regresja = jakikolwiek plik z bledem
spoza zbioru z baseline, nawet gdy liczba bledow jest taka sama lub nizsza.

Kasety LLM: klucz kasety obejmuje wszystkie parametry zmieniajace odpowiedz; po kazdej zmianie promptu
nagraj kasety ponownie (`LLM_MODE=record`).

`--update-baseline` nadpisuje tylko wskazane sekcje i drukuje roznice wzgledem poprzedniej; odmawia zapisu
(kod 1), gdy wynik ma bledy schematu albo wyjatki pipeline. Pelny wynik trafia do `output/.gate/<split>.json`
(i do `--json PATH`). Baseline aktualizuj swiadomie, razem ze zmiana poprawiajaca wynik.

Python API: `eval.gate.run_gate(split, cases=None, baseline_path=..., update=False, tolerance=0.0,
train_dir=..., negatives=None, gate_dir=None, source="all") -> GateResult` (`.exit_code`, `.metrics`,
`.regressions`, `.section`). Oczekiwany typ pozytywu przy ocenie bledow klasyfikacji pochodzi z kluczy GT
(`infer_doc_type`), nie z nazwy pliku; sprawy w podkatalogach (`skany/odwolania/0001`) maja wyniki w
`<out>/skany/odwolania/0001/0001.json`.

Testy: `python -m pytest -q tests/test_gate.py`

## Pokrycie tekstu z ingestu (`eval.ingest_coverage`)

```
python -m eval.ingest_coverage [--backend NAME] [--split dev|holdout|all] [--show-missing 20] [--json PATH]
```

Mierzy, ile wartosci z GT wystepuje w tekscie wyciagnietym z PDF (`odw2json.ingest.load`), niezaleznie od
reszty pipeline'u. Sprawy z `data/splits.yaml` (takze `skany/<typ>/<NNNN>`); PDF -> GT i typ dokumentu jak
w `eval.score` (`X.json` obok PDF-a, inaczej `GT_NAME_FOR_PDF`; typ z kluczy GT), negatywy pomijane. `--backend` wywoluje `load(path, backend=NAME)` (gdy loader nie zna parametru,
drukuje uwage i uzywa `load(path)`). Kod wyjscia zawsze 0 (narzedzie pomiarowe).

- Pola doslowne: `nazwa`, `tytul`, `imie_nazwisko`, `mail`, `numer_postepowania`, `numer_transakcji`,
  `miejscowosc`. Normalizacja po obu stronach: NFKC, casefold, ujednolicone cudzyslowy i myslniki, biale
  znaki (takze nowe linie) zwiniete do spacji; trafienie na granicach slow.
- Pola cyfrowe: `krs`, `nip`, `regon`, `pesel`, `na_rachunek`, `z_rachunku`. Cyfry wartosci z opcjonalnym
  separatorem `[\s\-./]?` miedzy cyframi (`12 34` pasuje do 1234, `12 x 34` nie), bez cyfr po bokach.
- `found_fuzzy` (tylko `imie_nazwisko`, gdy brak trafienia dokladnego): kazde slowo >= 4 liter ma w tekscie
  token zaczynajacy sie od jego 4 pierwszych liter, krotsze slowa musza byc tokenem identycznym.
- Pomijane: daty, kwoty, BZP, TED, `czynnosc_*`, `typ`, `przez-pelnomocnika`, `prowadzacy_postepowanie`.

Podzial wg zrodla (`by_source`, `by_type_source`, `docs_by_source` w JSON): `skan`, gdy `doc.ocr_used`
albo gdy PDF nie ma warstwy tekstu (< 30 znakow w surowej ekstrakcji; dotyczy tez bledu wczytania i OCR bez
wyniku), inaczej `tekst`.

Raport: pokrycie globalne, per typ dokumentu, per zrodlo, per pole (sciezki jak w `eval.score`, od najgorszego) i lista
brakow. `--json` zapisuje `global`, `by_type`, `by_field`, `missing`, `docs`, `load_errors`.

Python API: `coverage_for_doc(text, gt, doc_type) -> Coverage` (`found`, `found_fuzzy`, `total`, `missing`,
`rate`, `rate_with_fuzzy`, `+`), `run_coverage(split, backend, train_dir, cases=None) -> Report`.

Testy: `python -m pytest -q tests/test_ingest_coverage.py`
