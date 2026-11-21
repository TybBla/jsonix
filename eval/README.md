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

## Bramka regresji F1 (`eval.gate`)

```
python -m eval.gate [--split dev|holdout|all] [--update-baseline] [--tolerance 0.0] [--json PATH]
```

Dla wybranego splitu (`data/splits.yaml`) kopiuje PDF-y spraw + wszystkie negatywy (`data/train/negatywne`)
do katalogu tymczasowego, uruchamia `pipeline.run`, liczy `eval.score.score_dirs` tylko dla tych dokumentow,
sprawdza kazdy wynik (`schema.validate_output` dla pozytywow, `is_unknown_output` dla negatywow)
i porownuje z `eval/baseline.json` (osobna sekcja `dev` i `holdout`). `all` = oba splity osobno.

Baseline per split: `f1`, `precision`, `recall`, `f1_by_type`, `f1_by_field`, `neg_correct`/`neg_total`,
`schema_errors`, `classification_errors`, `pipeline_errors`, `updated`, `commit`.

Kody wyjscia:
- `0` - brak regresji,
- `1` - regresja (spadek f1 ogolnego / per typ / per pole albo odsetka poprawnych negatywow o wiecej niz
  `tolerance` + 1e-9; wzrost `classification_errors`) albo awaria (`schema_errors` > 0, wyjatek pipeline),
- `2` - blad uzycia albo brak sekcji splitu w baseline (bez `--update-baseline`).

Pola/typy nieobecne w baseline sa raportowane jako `new` (nie sa bledem). `classification_errors` to negatyw
z niepustym wynikiem albo pozytyw z `{}` / kluczami innego typu.

`--update-baseline` nadpisuje tylko wskazane sekcje i drukuje roznice wzgledem poprzedniej; odmawia zapisu
(kod 1), gdy wynik ma bledy schematu albo wyjatki pipeline. Pelny wynik trafia do `output/.gate/<split>.json`
(i do `--json PATH`). Baseline aktualizuj swiadomie, razem ze zmiana poprawiajaca wynik.

Python API: `eval.gate.run_gate(split, cases=None, baseline_path=..., update=False, tolerance=0.0,
train_dir=..., negatives=None, gate_dir=None) -> GateResult` (`.exit_code`, `.metrics`, `.regressions`).

Testy: `python -m pytest -q tests/test_gate.py`
