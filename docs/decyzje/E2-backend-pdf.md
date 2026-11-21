# E2 - wybor backendu PDF i czyszczenia (T4)

Status: rekomendacja do zatwierdzenia przez orkiestratora. `config/app.yaml` NIE zostal zmieniony.
Odtworzenie: `python scripts/bench_ingest.py` (dane: `bench_out/ingest/report.json`, `report.md`).

## Kontekst

Pokrycie T1 (`eval/ingest_coverage.py`) jest nasycone: 100% (dokladne i fuzzy) dla wszystkich trzech backendow,
z czyszczeniem i bez, wiec nie rankuje backendow. Benchmark dodaje miary komplementarne, liczone na wszystkich
196 PDF-ach treningowych (dev + holdout + negatywy; 851 wartosci doslownych i cyfrowych w pozytywach),
z wylaczonymi fallbackami (backendy wolane bezposrednio, wiec wynik nalezy tylko do danego backendu).
Bazą porownan jest pypdf bez czyszczenia (obecna konfiguracja). Czasy: 1 proces, Windows, Python 3.14,
ekstrakcja (+ czyszczenie w kolumnach "clean").

Przy okazji poprawiono `eval/ingest_coverage.py`: przy `--backend` ladowanie idzie z `fallback_backends: []`,
raport zawiera `foreign_backend` (dokumenty obsluzone innym backendem; ma byc puste), a padniecie backendu to
blad wczytania, nie ciche obsluzenie przez fallback (test w `tests/test_ingest_coverage.py`).

## Wyniki

Czyszczenie: `none` = brak; `clean` = `clean.DEFAULT_ORDER` (9 krokow); `clean-bez-dashes` = DEFAULT_ORDER bez `dashes`.

| backend | czyszczenie | pokrycie exact / +fuzzy | dosl. scisle (znak w znak) z 851 | strona jak w bazie | uszk. znaki | polskie litery | dok. tracace >1% PL | kolejnosc czytania = baza | wiersze KRS/NIP/REGON/Kwota vs baza | mediana s | p95 s | suma s (196 PDF) | bledy | zle sklasyfikowane poz./neg. | min. podobienstwo tekstu do bazy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pypdf | none | 100% / 100% | 851 | 100% | 18 | 51882 | 0 | 100% | 100% | 0.013 | 0.154 | 10.4 | 0 | 2 / 3 | 1.000 |
| pypdf | clean | 100% / 100% | 847 | 100% | 0 | 51513 | 21 | 100% | 100% | 0.013 | 0.166 | 11.1 | 0 | 2 / 3 | 0.987 |
| pypdf | clean-bez-dashes | 100% / 100% | 851 | 100% | 0 | 51513 | 21 | 100% | 100% | 0.013 | 0.181 | 11.1 | 0 | 2 / 3 | 0.988 |
| pdfplumber | none | 100% / 100% | 851 | 100% | 0 | 51882 | 0 | 100% | 97.7% | 0.097 | 1.540 | 59.3 | 0 | 2 / 3 | 0.832 |
| pdfplumber | clean | 100% / 100% | 847 | 100% | 0 | 51879 | 0 | 100% | 97.7% | 0.097 | 1.559 | 60.0 | 0 | 2 / 3 | 0.832 |
| pdfplumber | clean-bez-dashes | 100% / 100% | 851 | 100% | 0 | 51879 | 0 | 100% | 97.7% | 0.097 | 1.548 | 59.8 | 0 | 2 / 3 | 0.832 |
| pypdfium2 | none | 100% / 100% | 851 | 100% | 18 | 51882 | 0 | 100% | 98.9% | 0.003 | 0.016 | 1.1 | 0 | 2 / 3 | 0.994 |
| pypdfium2 | clean | 100% / 100% | 847 | 100% | 0 | 51510 | 21 | 100% | 98.9% | 0.003 | 0.029 | 1.7 | 0 | 2 / 3 | 0.987 |
| pypdfium2 | clean-bez-dashes | 100% / 100% | 851 | 100% | 0 | 51510 | 21 | 100% | 98.9% | 0.003 | 0.024 | 1.5 | 0 | 2 / 3 | 0.988 |

Objasnienia miar:
- **dosl. scisle**: wartosc GT musi wystapic w tekscie znak w znak (tylko zwiniete biale znaki; bez casefold i bez
  ujednolicania cudzyslowow/myslnikow), czyli ostrzejsza od miary T1.
- **strona jak w bazie**: odsetek wartosci GT (cyfrowych i doslownych) znalezionych na tej samej stronie co w pypdf raw.
- **uszk. znaki**: U+FFFE/U+FFFD/U+FFFF, znaki sterujace (poza `\n \f \t`), ligatury FB00-FB06, spacje typu NBSP,
  znaki zerowej szerokosci. W calym zbiorze wystapil tylko jeden rodzaj: 18 spacji NBSP-podobnych w jednym dokumencie.
- **dok. tracace >1% PL**: dokumenty, w ktorych liczba liter ąćęłńóśźżĄĆĘŁŃÓŚŹŻ jest o >1% nizsza niz maksimum
  z backendow w tym samym trybie czyszczenia.
- **kolejnosc czytania**: dla 60 odwolan sygnatura (Odwolujacy przed Zamawiajacy, tytul zamowienia przed "Zarzut")
  identyczna jak w bazie.
- **wiersze etykiet**: liczba wierszy zaczynajacych sie od `KRS|NIP|REGON ... 9+ cyfr` lub `Kwota przelewu ... cyfra`
  wzgledem bazy.
- **klasyfikacja**: `odw2json.classify.classify` na tekscie; oczekiwanie jak w `eval.gate` (pozytyw = typ z GT,
  negatyw = brak typu).

## Obserwacje

1. **Rozstrzygajace roznice nie leza w tresci, tylko w ukladzie tekstu.** Na wszystkich miarach tresciowych
   (pokrycie, polskie litery, strony, kolejnosc, klasyfikacja) trzy backendy sa nierozroznialne. pypdf i pypdfium2
   daja niemal ten sam tekst (min. podobienstwo 0.994; roznice to scalanie etykiety z wartoscia w jednym wierszu,
   np. w negatywie `2025_BZP 00143067_01.pdf` pypdf zostawia `1.4) Krajowy Numer Identyfikacyjny: \nREGON 142917040`,
   a pypdfium2 i pdfplumber `...Identyfikacyjny: REGON 142917040`, dlatego wiersze etykiet 98.9% / 97.7% wzgledem pypdf).
2. **pdfplumber zmienia uklad wielokolumnowy (36 z 196 dokumentow ponizej 0.97 podobienstwa do bazy).**
   Najbardziej widac to na `potwierdzenie_przelewu.pdf` (min. 0.832): pdfplumber skleja kolumny w jeden wiersz,
   np. `Dane nadawcy Rachunek obciążany` / `Corvella Serwis sp. k. PL78686803479783141916212008`, i `Kwota operacji Data realizacji`
   / `200,00 zł 25.07.2026`, podczas gdy pypdf i pypdfium2 zachowuja pary etykieta-nastepna linia z wartoscia.
   Podobnie w pelnomocnictwach: `Dane KRS 9997927279, NIP 9990600725, REGON` / `rejestrowe 9...` (przez to 4 wiersze
   KRS/NIP mniej niz w bazie). Reguly ekstrakcji oparte na wartosci w wierszu po etykiecie beda wrazliwe na te zmiane.
   Dokumenty TED (`2025_S 112-383751`, `OJS107`) w tym zbiorze nie pokazaly przestawienia kolumn (podobienstwo
   0.989-0.998 dla pdfplumber i pypdfium2), wiec ryzyko wielokolumnowe dotyczy glownie formularzy przelewu.
3. **Kolejnosc stron i bloki:** zero wartosci GT przeniesionych na inna strone u zadnego backendu; zero zmian
   kolejnosci Odwolujacy/Zamawiajacy i tytul/Zarzut.
4. **Uszkodzone znaki:** surowe wyjscie pypdf i pypdfium2 zawiera 18 spacji NBSP-podobnych w jednym dokumencie
   (`negatywne/Broszura_JPK_FA(2).pdf`); pdfplumber normalizuje je do zwyklych spacji. U+FFFE z pdfium obsluguje
   juz `_fix_pdfium_text` w `backends.py`. Po czyszczeniu uszkodzonych znakow jest 0 u wszystkich.
5. **Polskie litery:** surowe sumy identyczne (51882) u wszystkich trzech backendow, wiec zadnego backendu nie
   dotyczy utrata ą/ę/ł. Spadek po czyszczeniu u pypdf/pypdfium2 (-369/-372 liter, 21 odwolan) to NIE uszkodzenie
   znakow: `strip_page_artifacts` usuwa powtarzajacy sie naglowek `Odwołanie - postępowanie nr ...` i `Strona X z Y`
   (np. 18 liter w `przyklad_42`). U pdfplumber ten krok nic nie usuwa, bo pdfplumber zwraca strony bez konczacego
   `\n`, wiec po zlaczeniu `\f` wiersz stopki skleja sie z naglowkiem kolejnej strony (`Strona 1 z 11\fOdwołanie ...`).
   Czyszczenie dziala wiec niespojnie miedzy backendami; poprawka nalezy do T2/T3 (rozbijanie po `\f` w krokach),
   nie do tego zadania.
6. **Krok `dashes` pogarsza zgodnosc znak w znak:** zamienia pauze `–` na `-`, a GT zachowuje pauze (np. tytuly
   `... w latach 2026–2029`: przyklad_42, 46, 53, 60). Pokrycie T1 tego nie widzi (normalizuje myslniki), miara
   scisla spada z 851 do 847. Pole `tytul` jest oceniane rozmyto (prog 0.8), wiec skutek w F1 jest maly, ale
   wariant bez `dashes` odzyskuje 851/851 bez innych kosztow. Krok `quotes` nie dal straty w tym zbiorze.
7. **Klasyfikacja:** te same 5 bledow u wszystkich konfiguracji (negatywy `2025_S 112-383751.pdf` (x2) i
   `Broszura_JPK_FA(2).pdf` jako `przelew`; `przyklad_02/pelnomocnictwo.pdf` jako `odwolanie`;
   `przyklad_32/pelnomocnictwo.pdf` jako nieznany). Zmiana backendu ani czyszczenie ich nie naprawia ani nie
   psuje; to kwestia slow kluczowych klasyfikatora (osobny temat niz E2). 3 negatywy bez warstwy tekstowej
   (decyzje Ministra, pismo RDSSP) maja pusty tekst u wszystkich backendow i sa poprawnie "nieznane" (czeka na OCR, T5).
8. **Czas:** pypdfium2 jest ok. 9x szybszy od pypdf i ok. 54x od pdfplumber (suma 1.1 s / 10.4 s / 59.3 s dla 196 PDF).
   Czyszczenie dodaje ok. 0.4-0.7 s na caly zbior.
9. **Bledy:** 0 wyjatkow i 0 pustych wynikow poza trzema skanami u kazdego backendu.

## Rekomendacja

| element | wybor |
|---|---|
| backend glowny | `pypdfium2` |
| fallback | `[pypdf, pdfplumber]` (pypdf: ta sama zawartosc i uklad, najblizszy poprzedniemu zachowaniu; pdfplumber ostatni, bo wolny i zmienia uklad kolumn) |
| czyszczenie | wlaczone: `clean.DEFAULT_ORDER` bez `dashes` (czyli `unicode_nfc, nbsp_to_space, ligatures, quotes, strip_page_artifacts, dehyphenate, join_wrapped_lines, collapse_spaces`) |

Uzasadnienie (jakosc, potem szybkosc, licencja):
1. **Jakosc:** remis. Na miarach tresciowych (pokrycie, polskie litery, strony, kolejnosc, klasyfikacja) backendy sa
   rowne, a pdfplumber jest gorszy ukladowo (laczenie kolumn, 97.7% wierszy etykiet). pypdfium2 i pypdf sa
   rownowazne; pypdfium2 ma dodatkowo najwiekszy margines niezawodnosci dla uszkodzonych plikow (silnik PDFium).
2. **Szybkosc:** pypdfium2 najszybszy (suma 1.1 s vs 10.4 s pypdf).
3. **Licencja:** pypdfium2 BSD-3-Clause / Apache-2.0 (metadata pakietu 5.15.2; silnik PDFium BSD-3 w kole binarnym),
   zgodna z wymaganiem MIT/BSD/Apache. Wszystkie rozwazane biblioteki sa zgodne: pypdf 7.1.1 BSD-3-Clause,
   pdfplumber 0.11.11 MIT (zaleznosc pdfminer.six 20260107 MIT). PyMuPDF (AGPL) pozostaje wykluczony.
4. **Czyszczenie wlaczone:** usuwa NBSP, ligatury i powtarzane stopki/naglowki bez straty pokrycia ani
   zgodnosci doslownej (po wylaczeniu `dashes`); nie zmienia cyfr ani polskich liter (sumy liter roznia sie tylko o
   usuniete naglowki, patrz punkt 5 obserwacji).

Warunek wejscia w zycie: zmiana backendu z pypdf na pypdfium2 zmienia uklad tekstu w ok. 1-2% wierszy etykiet,
a ekstraktory i baseline `eval.gate` byly stroje pod pypdf. Przed zmiana `config/app.yaml` trzeba uruchomic
`python -m eval.gate --split all`; jesli pojawi sie regresja F1, pozostac przy `pypdf` jako glownym (jakosc
rowna, koszt +9 s na 196 PDF) i `pypdfium2` jako pierwszym fallbacku.

## Ryzyka

- **Rozjazd ekstraktorow z ukladem tekstu:** wiersze etykieta/wartosc roznia sie miedzy backendami (obs. 1-2);
  pdfplumber nie nadaje sie na glowny wlasnie z tego powodu.
- **Niespojnosc `strip_page_artifacts` z pdfplumber** (obs. 5): fallback na pdfplumber zwroci tekst z niezdjetymi
  naglowkami; nie psuje pokrycia, ale zmienia tekst. Do poprawy w T2/T3.
- **`dashes` i `quotes` zmieniaja znaki obecne w GT** (obs. 6): `dashes` wylaczone w rekomendacji; `quotes` nie dal straty
  w zbiorze treningowym, ale na ukrytym zbiorze testowym moze (cudzyslowy w nazwach). Do ponownej oceny po bramce.
- **Nasycenie metryk:** zbior treningowy jest syntetyczny i jednorodny (jedna czcionka na typ); brak roznic miedzy
  backendami moze nie przeniesc sie na prawdziwe odwolania z innych edytorow (np. skany z warstwa OCR, tabele wielokolumnowe).
  Miary scisle i polozenia na stronach zostaja w skrypcie do ponownego uzycia na nowych danych.
- **Binarne wheel pypdfium2** zawieraja natywna biblioteke PDFium; pip dziala na Windows i Linux, lecz zmienia sie
  rozmiar instalacji i trzeba przypiac wersje w `requirements.txt`.
- **Skany bez warstwy tekstowej** (3 negatywy) daja pusty tekst u wszystkich backendow; obsluga w T5 (OCR).

## Decyzja orkiestratora (2026-11-21)

Zatwierdzone i wdrozone w `config/app.yaml`:

- `ingest.backend: pypdfium2`
- `ingest.fallback_backends: [pypdf, pdfplumber]`
- czyszczenie wlaczone, kolejnosc `clean.DEFAULT_ORDER` bez kroku `dashes` (krok `dashes` pozostaje w `CLEAN_STEPS`).
  Uzasadnienie: `dashes` zamienial pauzy `–` w tytulach na `-`, a GT zachowuje `–` (obs. 6).

Bramka (`python -m eval.gate --split all`), zakonczona exit 0, bez regresji, baseline nie zmieniany:

```
f1=0.0000 neg=12/15 schema=0 klasyfikacja=5 pipeline=0 -> exit 0
f1=0.0000 neg=11/13 schema=0 klasyfikacja=2 pipeline=0 -> exit 0
```

Uwaga: f1 wynosi 0.0000 zarowno w baseline, jak i w biezacym wyniku, wiec bramka potwierdza brak regresji,
ale nie mierzy jakosci ekstrakcji pol. Pokrycie:

`python -m eval.ingest_coverage --split all`: razem 1460/1460, 100.0% (exact), 100.0% (+fuzzy).

Zmiany w testach (tylko dopasowanie do nowej konfiguracji, asercje nieosłabione):
- `tests/test_clean.py::test_registry_names`: `DEFAULT_ORDER` == rejestr bez `dashes`, plus unikalnosc krokow.
- `tests/test_ingest.py`: domyslny backend to `pypdfium2` (wczesniej `pypdf`).
