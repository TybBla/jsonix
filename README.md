# jsonix — HackNation 2026 (UZP)

**jsonix** zamienia dokumenty PDF spraw odwoławczych KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) na dane JSON zgodne ze schematami UZP: rozpoznaje typ dokumentu z treści i wyodrębnia pola, pokazując, skąd pochodzi każda wartość. Dokumenty spoza tych typów są rozpoznawane jako **nieznane**.

## Szybki start (Windows)

**Wymagania:** Windows 10/11 i **Python 3.13 lub 3.14** ([python.org](https://www.python.org/downloads/), przy instalacji zaznacz „Add python.exe to PATH”), internet przy pierwszym uruchomieniu (instalacja zależności). Albo zamiast Pythona: Docker Desktop (sekcja „Docker”).

1. Umieść dokumenty w `input\` — jeden podfolder na sprawę: `input\<sprawa>\<plik>.pdf` (PDF-y luzem w `input\` też działają).
2. Uruchom w terminalu (PowerShell albo cmd) w katalogu repozytorium:

```powershell
.\start.bat              # wsad: input\ -> output\ (python -m odw2json run input output)
.\start-gui.bat          # GUI w przeglądarce: http://127.0.0.1:8000
```

3. Wyniki: `output\<sprawa>\<plik>.json` (nazwa jak PDF). W `cmd.exe` wpisz `start.bat` bez `.\`; PowerShell wymaga `.\` przed nazwą pliku z bieżącego katalogu.

Przy pierwszym uruchomieniu `start.bat` (i `start-gui.bat`) sam przygotowuje środowisko (`scripts/setup-env.bat`): użyje Pythona z `PATH`, jeśli ma już zależności, a w przeciwnym razie utworzy `.venv` na **Pythonie 3.13 lub 3.14** (launcher `py`) i zainstaluje `requirements.txt` (jednorazowo, kilka minut, potrzebny internet). Plik `.env` jest opcjonalny — tylko z LLM (`copy .env.example .env`, uzupełnij `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`).

**Wersja Pythona.** Zalecany **Python 3.13 lub 3.14**. Na nowszym (3.15+) aplikacja się instaluje i działa, ale **OCR skanów jest niedostępny** (paczki `onnxruntime`/`pyclipper` nie mają jeszcze wersji dla 3.15): dokumenty z warstwą tekstową są przetwarzane normalnie, a skan bez tekstu dostaje ostrzeżenie. Ręcznie: `py -3.13 -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`, `.venv\Scripts\python -m odw2json run input output`. Linux/macOS: `pip install -r requirements.txt`, `sh start.sh` (wybiera Pythona 3.13+).

- Wejście: `input/<sprawa>/<plik>.pdf` (lub PDF-y luzem w `input/`).
- Wyjście: `output/<sprawa>/<plik>.json` — nazwa jak plik wejściowy.
- Dokument nieznany: plik `<nazwa>.json` z zawartością `{}` (wg UZP); przełącznik `config/app.yaml: unknown_output` (`empty_object` | `empty_file` | `none`).
- Ścieżka ekstrakcji (skąd pochodzi każda wartość): `output/.trace/`.

Inne komendy:
```powershell
python -m odw2json doctypes      # lista skonfigurowanych typów dokumentów
python -m odw2json serve         # API + GUI na http://127.0.0.1:8000
docker compose up --build        # to samo w Dockerze (sekcja „Docker” niżej)
```

**OCR.** Skany bez warstwy tekstowej czyta OCR (rapidocr + onnxruntime, w `requirements.txt`, modele w paczce, bez sieci w czasie działania). Paczki OCR są dostępne dla Pythona 3.13 i 3.14 (na 3.15+ OCR jest pomijany, patrz wyżej); ten sam OCR jest w obrazie Dockera.

## Docker

```powershell
docker compose up --build                              # API + GUI: http://127.0.0.1:8000
docker compose run --rm app python -m odw2json run     # wsad: input/ -> output/, bez GUI
python scripts/smoke_docker.py                         # test: build, healthcheck, GUI/API, wsad = CLI
```

- Plik `.env` jest **opcjonalny**: bez niego działa domyślny tryb bez LLM.
- Katalogi `input/`, `output/` i `config/` są montowane z repo, więc konfigurację typów dokumentów zmieniasz bez przebudowy obrazu (wystarczy restart).
- Port zmienisz zmienną `JSONIX_PORT` (np. `$env:JSONIX_PORT=8080; docker compose up`). Serwer nasłuchuje tylko na `127.0.0.1`.
- Kontener ma healthcheck (`/api/health`); `docker compose ps` pokazuje stan `healthy`.
- `scripts/smoke_docker.py` uruchamia osobny projekt `jsonix-smoke`, sprawdza GUI/API, przetwarza w kontenerze `przyklad_01` i skan (OCR), porównuje JSON-y z CLI na hoście i sprząta po sobie (kod wyjścia 0/1, 2 = brak Dockera).

## GUI

```powershell
.\start-gui.bat                  # = python -m odw2json serve + otwarcie http://127.0.0.1:8000
python scripts/smoke_gui.py      # test dymny API + GUI (kod wyjścia 0/1)
```

W GUI jsonix wgraj PDF-y sprawy, uruchom analizę, sprawdź wynik klasyfikacji, a potem przejrzyj wyodrębnione pola **obok podglądu PDF** z podświetleniem fragmentu, z którego pochodzi każda wartość. JSON pobierzesz dla jednego dokumentu albo dla wszystkich (ZIP). GUI działa offline (PDF.js i font dołączone lokalnie), styl wg Design System Gov.pl. Szczegóły i ograniczenia: [docs/gui.md](docs/gui.md).

## Architektura

```
PDF → ingest (tekst z PDF, czyszczenie, OCR skanów) → classify (punktacja cech z YAML)
    → extract (pola i listy z YAML, normalizacja, walidacja) → JSON wg config/schemas/ (+ trace)
```

Pełny opis (etapy, kontrakty, konfiguracja, API i GUI, jakość): **[docs/architektura.md](docs/architektura.md)**.

- `odw2json/contracts.py` — wspólne struktury danych (Document, Classification, FieldResult, ExtractionResult).
- `config/doctypes/*.yaml` — **typy dokumentów są konfiguracją**: nowy typ = nowy YAML + szablon JSON ([instrukcja](docs/nowy-typ-dokumentu.md)).
- `config/schemas/` — szablony wyników, `config/lookups/` — słowniki (np. powód odwołania → opis).
- **Domyślnie bez LLM** (`config/app.yaml: llm_enabled: false`): reguły z konfiguracji. Warstwa LLM jest opcjonalna — wyłącznie model open source ≤ 8B od dostawcy z serwerami w UE (konfiguracja w `.env`, temperatura 0, kasety odpowiedzi w testach).

## Ewaluacja

```powershell
python scripts/make_input_from_train.py --clean   # data/train → input/
python -m odw2json run
python -m eval.score --pred output --gt data/train
```
F1 liczone wg reguł organizatora (TP/TN/FP/FN per pole, długie napisy z progiem podobieństwa 80%) — szczegóły w [eval/README.md](eval/README.md).

Aktualne wyniki (F1 wg reguł UZP, pomiar 21.11 z ekstrakcją E4; pełny raport: `python scripts/quality_report.py` → `docs/raport-jakosci.md`):

| Zbiór | Dokumenty z tekstem | Skany: odwołanie | Skany: pełnomocnictwo | Skany: przelew |
|---|---|---|---|---|
| dev | 0,999 | 0,997 | 0,980 | 0,866 |
| holdout | 0,997 | 1,000 | 0,833 | 0,897 |

Klasyfikacja: 0 błędów na dev i holdout; dokumenty spoza typów odrzucone 12/12 (dev) i 10/10 (holdout).

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
