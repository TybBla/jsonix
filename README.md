# Odwołania2JSON — HackNation 2026 (UZP)

Klasyfikacja i ekstrakcja danych z dokumentów spraw odwoławczych KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) do JSON zgodnego ze schematami UZP. Dokumenty spoza tych typów są rozpoznawane jako **nieznane**.

## Szybki start (Windows, Python 3.13+)

```powershell
pip install -r requirements.txt
copy .env.example .env    # uzupełnij LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
start.bat                 # = python -m odw2json run input output
```

- Wejście: `input/<sprawa>/<plik>.pdf` (lub PDF-y luzem w `input/`).
- Wyjście: `output/<sprawa>/<plik>.json` — nazwa jak plik wejściowy.
- Dokument nieznany: plik `<nazwa>.json` z zawartością `{}` (wg UZP); przełącznik `config/app.yaml: unknown_output` (`empty_object` | `empty_file` | `none`).
- Ścieżka ekstrakcji (skąd pochodzi każda wartość): `output/.trace/`.

Inne komendy:
```powershell
python -m odw2json doctypes      # lista skonfigurowanych typów dokumentów
python -m odw2json serve         # API + GUI na http://127.0.0.1:8000
docker compose up --build        # to samo w Dockerze
```

## Architektura

```
PDF → ingest (tekst/OCR) → classify (reguły z YAML, LLM fallback) → extract (regex + LLM + słowniki)
    → normalizacja i walidacja → JSON wg config/schemas/ (+ trace)
```

- `odw2json/contracts.py` — wspólne struktury danych (Document, Classification, FieldResult, ExtractionResult).
- `config/doctypes/*.yaml` — **typy dokumentów są konfiguracją**: nowy typ = nowy YAML + szablon JSON ([instrukcja](docs/nowy-typ-dokumentu.md)).
- `config/schemas/` — szablony wyników, `config/lookups/` — słowniki (np. powód odwołania → opis), `config/prompts/` — prompty LLM.
- LLM: dowolny dostawca OpenAI-kompatybilny z serwerami w UE (konfiguracja w `.env`), temperatura 0, cache odpowiedzi.

## Ewaluacja

```powershell
python scripts/make_input_from_train.py --clean   # data/train → input/
python -m odw2json run
python -m eval.score --pred output --gt data/train
```
F1 liczone wg reguł organizatora (TP/TN/FP/FN per pole, długie napisy z progiem podobieństwa 80%) — szczegóły w [eval/README.md](eval/README.md).

| Wersja | Klasyfikacja (train) | F1 (train) |
|---|---|---|
| szkielet (stuby) | 190/194 | 0.000 (negatywy 14/14) |

## Praca zespołu

Gałęzie i zakresy: [docs/sektory.md](docs/sektory.md). Projekt: [docs/superpowers/specs](docs/superpowers/specs/).

## Dane

`data/train/` — zestawy treningowe UZP (https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026), `data/oczekiwane-json/` — schematy z opisami pól.

## Jakość i CI

```powershell
pip install -r requirements-dev.txt
pre-commit install                       # hook: ruff + szybkie testy (bez slow/live_llm)
ruff check . ; ruff format --check .     # lint i format
python -m pytest -q -m "not slow"        # szybkie testy (tak jak w pre-commit)
python -m pytest -q -m "not live_llm"    # pełny zestaw (z wolnymi), tak jak w CI; bez sieci
python -m eval.gate --split all          # bramka regresji F1 (dev + holdout) względem eval/baseline.json
python -m eval.gate --split dev --update-baseline   # TYLKO świadomie, razem ze zmianą poprawiającą wynik
powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1   # Windows: smoke end-to-end
bash scripts/smoke.sh                                         # Linux/macOS: smoke end-to-end
```

- **Gate**: szczegóły i kody wyjścia w [eval/README.md](eval/README.md); raporty trafiają do `output/.gate/`.
- **Smoke**: tworzy świeży venv w katalogu tymczasowym, instaluje tylko `requirements.txt`, kopiuje jedną sprawę
  i jeden negatyw, uruchamia `start.bat` / `start.sh` i sprawdza wynik (4 pliki JSON, negatyw = `{}`).
  `start.bat` / `start.sh` robią `cd` do katalogu repozytorium, więc **ścieżki wejścia/wyjścia podawane
  skryptom muszą być bezwzględne** (względne zostałyby rozwiązane względem katalogu repo).
- **CI** (`.github/workflows/ci.yml`, push i PR, Ubuntu + Windows, Python 3.13, `LLM_MODE=replay`):
  `ruff check`, `ruff format --check`, pełne testy (`-m "not live_llm"`), gate F1 dev i holdout (raporty
  jako artefakt), potem smoke na obu systemach oraz `docker build`. `PYTHONUTF8` celowo nie jest ustawione,
  aby sprawdzać odporność na kodowanie konsoli.
