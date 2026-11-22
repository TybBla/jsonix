## E7: przelewy ze skanów — reguły pod błędy OCR (plan v1.0, pkt 9)

Gałąź `etap/E7-skany` → `main`.

### Co się zmienia
- **`config/doctypes/przelew.yaml`** (tylko reguły):
  - `data_operacji`: data bez kropek („Zlecona data wykonania 20 04 2026”) i etykieta rozbita na dwie linie („Data 2026-03-26⏎wykonania”);
  - `numer_transakcji`: „Numer 305494⏎transakcji”, czyli etykieta rozbita i numer krótszy niż 8 znaków;
  - `tytul`: etykieta „Szczegóły płatności” (też w zniekształceniu OCR „Szczegoty platnosci”), stop na „Signature…”, oraz kolumny przestawione przez OCR („…wartość… Opis” w jednej linii).
- **`odw2json/extract/normalize.py`:** `date` przyjmuje też spację jako separator („20 04 2026”), z tym samym separatorem w obu miejscach. Wzorzec wyszukiwania dat w silniku jest bez zmian.
- Testy: `tests/test_extract_przelew_ocr.py` (3 przypadki z prawdziwych tekstów OCR) i `test_date_with_spaces_from_ocr`.

### Wyniki
Strojenie wyłącznie na dev; holdout sprawdzony raz. Docker, Python 3.13, OCR.

| Sekcja | przed | po |
|---|---|---|
| dev@skan, F1 | 0,977 | **0,992** |
| dev@skan, przelew | 0,882 | **0,987** |
| holdout@skan, F1 | 0,912 | **0,922** |
| holdout@skan, przelew | 0,933 | **0,968** |
| dev@tekst, F1 | 0,999 | 0,999 (bez zmian) |

Pozostałe różnice na skanach to litery w tytule zmienione przez OCR („DEBNICY”, „odwolania”). Tytuł jest liczony z progiem podobieństwa 80%, więc zwykle przechodzi. Na holdoucie zostają dwa tytuły (0004: etykieta w innym miejscu; 0006: numer CEN na początku). Nie stroiłem ich, bo holdout służy do kontroli.

### Do zrobienia przez właściciela
Uprawnienia zablokowały mi `--update-baseline`. Po review zaktualizuj sekcje skanów (maszyna z OCR albo Docker):
`python -m eval.gate --split dev --source skan --update-baseline` oraz to samo dla `--split holdout`. Wzrost F1 jest uzasadniony tabelą wyżej.

### Bramka
- `ruff`: czysto.
- Testy przelewów, odporności przelewów, nowe testy OCR i `test_normalize`: 197 passed.
- `eval.gate --split dev --source tekst`: exit 0, F1 0,999.
- Bramki skanów (Docker): dev exit 0, holdout exit 0.
