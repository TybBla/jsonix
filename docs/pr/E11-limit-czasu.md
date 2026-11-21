## Limit czasu UZP: częściowe wyniki przetrwają przerwanie przebiegu

Gałąź `etap/E11-limit-czasu` → `main`. UZP (21.11, 21:13): każde rozwiązanie ma ograniczony czas, a program, który nie skończy, może nie zostać w pełni oceniony.

### Co się zmienia (`odw2json/cli.py`)
- Przed przetwarzaniem `python -m odw2json run` (i `start.bat`) zapisuje dla **każdego** PDF-a plik wynikowy jak dla dokumentu nieznanego: `{}`, a przy `unknown_output: empty_file` pusty plik.
- `pipeline.run` nadpisuje ten plik pełnym wynikiem **zaraz po przetworzeniu** danego PDF-a, więc wyniki już wcześniej trafiały na dysk na bieżąco.
- Efekt przy przerwaniu: gotowe pliki mają pełne wyniki, a reszta ma `{}`. Dokumenty spoza typów są wtedy ocenione poprawnie (TN) zamiast braku pliku, a dla pozostałych nic się nie pogarsza.
- `unknown_output: none` działa jak dotąd, bez plików zastępczych.
- Testy `tests/test_cli_limit_czasu.py`: przerwanie po pierwszym pliku (pozostałe mają `{}`), pełny przebieg nadpisuje pliki zastępcze, zgodność z `unknown_output`.

### Czego nie ruszyłem (do decyzji właściciela `pipeline.py`)
Uprawnienia zablokowały mi edycję `odw2json/pipeline.py` (plik chroniony), więc dwie rzeczy zostają propozycją:
1. **Najtańsze dokumenty najpierw.** `pipeline.run` przetwarza pliki alfabetycznie. Sortowanie po rozmiarze (małe PDF-y z tekstem ~0,01 s, na końcu duże skany 4–12 s) sprawia, że przerwanie zabiera najmniej gotowych wyników:
   ```python
   pdfs = sorted((p for p in Path(input_dir).rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
                 key=lambda p: (p.stat().st_size, str(p)))
   ```
2. **Timeout na dokument.** Bez osobnego procesu na dokument nie da się bezpiecznie przerwać OCR w trakcie, a osobny proces to ładowanie modeli OCR za każdym razem. Pomiar (`docs/decyzje/E11-wydajnosc.md`, PR `etap/E11-wydajnosc`): najwolniejszy skan to 12,6 s, więc timeout nie jest dziś potrzebny. Bezpieczniejszy byłby limit stron OCR na dokument w `ingest/ocr.py`, czyli obszar OCR.

### Bramka
`ruff`: czysto. `smoke_gui.py` i `eval.gate --split dev --source tekst`: exit 0. `pytest` lokalnie (3.15): tylko 5 testów OCR, jak na `main`.
