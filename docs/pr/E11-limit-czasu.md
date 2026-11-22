## Limit czasu UZP: częściowe wyniki przetrwają przerwanie przebiegu

Gałąź `etap/E11-limit-czasu` → `main`. UZP (21.11, 21:13): każde rozwiązanie ma ograniczony czas, a program, który nie skończy, może nie zostać w pełni oceniony.

### Co się zmienia (`odw2json/cli.py`)
- Przed przetwarzaniem `python -m odw2json run` (i `start.bat`) zapisuje dla **każdego** PDF-a plik wynikowy jak dla dokumentu nieznanego: `{}`, a przy `unknown_output: empty_file` pusty plik.
- `pipeline.run` nadpisuje ten plik pełnym wynikiem **zaraz po przetworzeniu** danego PDF-a, więc wyniki już wcześniej trafiały na dysk na bieżąco.
- Efekt przy przerwaniu: gotowe pliki mają pełne wyniki, a reszta ma `{}`. Dokumenty spoza typów są wtedy ocenione poprawnie (TN) zamiast braku pliku, a dla pozostałych nic się nie pogarsza.
- `unknown_output: none` działa jak dotąd, bez plików zastępczych.
- Testy `tests/test_cli_limit_czasu.py`: przerwanie po pierwszym pliku (pozostałe mają `{}`), pełny przebieg nadpisuje pliki zastępcze, zgodność z `unknown_output`.

### Po review (zmiany w `odw2json/pipeline.py`, na prośbę właściciela)
- **Zapis atomowy** (`write_text_atomic`): plik `.tmp` w tym samym katalogu, potem `os.replace`. Dotyczy wyniku JSON, `{}`, pustego pliku, trace i placeholderów z CLI. Przerwanie nie zostawi pustego ani uciętego JSON-a.
- **`pipeline.list_inputs(input_dir)`**: jedna lista wejść dla CLI (placeholdery) i `pipeline.run`.
- **Kolejność:** najpierw PDF-y z warstwą tekstu, skany na końcu, według liczby stron z mniej niż `min_chars_per_page` (30) znakami. Sprawdzam to przez pypdfium2, bez OCR. Nieczytelny PDF idzie na początek, żeby błąd wyszedł od razu.
- **Timeout na dokument:** bez zmian. Pomiar pokazał najwolniejszy skan 12,6 s, a przerwanie OCR w trakcie wymaga osobnego procesu.
- Testy: kolejność, nieczytelny PDF, kolejność w `run`, atomowość zapisu, CLI korzysta z `list_inputs`.

### Bramka
`ruff`: czysto. `smoke_gui.py` i `eval.gate --split dev --source tekst`: exit 0. `pytest` lokalnie (3.15): tylko 5 testów OCR, jak na `main`.
