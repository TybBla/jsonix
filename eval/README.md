# eval - ocena F1

Liczy TP/TN/FP/FN na poziomie pol (zasady organizatora) i F1 = 2TP/(2TP+FP+FN).

```
python -m eval.score --pred output --gt data/train [--threshold 0.8] [--json raport.json] [--worst 10]
```

Predykcja `output/<case>/<nazwa>.json` jest porownywana z `data/train/<case>/<nazwa>.json`
(wyjatek: `potwierdzenie_przelewu.pdf` -> GT `przelew.json`; mapowanie w `GT_NAME_FOR_PDF`).
PDF-y bez GT (np. `negatywne/`) to negatywy: poprawny wynik to brak pliku JSON (pusty plik = brak).

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
