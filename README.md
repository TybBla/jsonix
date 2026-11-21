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
