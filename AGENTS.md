# AGENTS.md — zasady pracy w repo Odwołania2JSON

Przeczytaj w całości przed pierwszą zmianą. Dotyczy ludzi i agentów AI.

## Co budujemy
Aplikacja (Python 3.13+), która z PDF-ów spraw odwoławczych KIO rozpoznaje typ dokumentu (odwołanie / pełnomocnictwo / potwierdzenie przelewu / nieznany) i zwraca JSON ściśle wg schematu UZP. Konkurs HackNation 2026 (UZP).
- **Kryteria, ocena i wszystkie ustalenia organizatora: [docs/kryteria-uzp.md](docs/kryteria-uzp.md)** — czytaj najpierw.
- Architektura: [docs/superpowers/specs/2026-11-21-odwolania2json-design.md](docs/superpowers/specs/2026-11-21-odwolania2json-design.md)
- Roadmapa i zakres wydania v1.0: [docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md](docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md) (sekcja „Aktualizacja zakresu” ma pierwszeństwo)
- Plany etapów: `docs/superpowers/plans/2026-11-21-E*.md`; decyzje: `docs/decyzje/`.

## Mapa kodu
| Ścieżka | Co |
|---|---|
| `odw2json/contracts.py` | Wspólne struktury: `Document`, `Classification`, `FieldResult`, `ExtractionResult`, `IngestError`. **Zmiana tylko za zgodą właściciela projektu.** |
| `odw2json/ingest/` | PDF → tekst (pypdfium2 + fallbacki), czyszczenie, OCR (rapidocr) |
| `odw2json/classify/` | Rozpoznanie typu z treści (reguły z `config/doctypes/*.yaml`) |
| `odw2json/extract/` | Ekstrakcja pól wg konfiguracji (w budowie) |
| `odw2json/pipeline.py` | `process_file`, `run(input, output)`; zapis JSON + trace (`output/.trace/`) |
| `odw2json/api/` | FastAPI (`python -m odw2json serve`) |
| `web/` | GUI (statyczne pliki serwowane przez FastAPI) |
| `config/` | Typy dokumentów (YAML), szablony wyników (`schemas/`), słowniki, ustawienia (`app.yaml`) |
| `eval/` | F1 wg reguł UZP (`score.py`), bramka regresji (`gate.py`), pokrycie tekstu |
| `data/train/` | Dane treningowe UZP (`przyklad_*`, `negatywne/`, `skany/`) + podział `data/splits.yaml` |

## Uruchamianie
```powershell
pip install -r requirements-dev.txt
python -m odw2json run input output        # albo start.bat
python -m odw2json serve                   # API + GUI: http://127.0.0.1:8000
python -m pytest -q -m "not slow"          # szybkie testy
python -m eval.gate --split dev            # bramka F1 (od v0.2.1: dodaj --source tekst, jak w CI)
```

## Harness — obowiązkowe przed każdym commitem/PR
1. `python -m ruff check .` i `python -m ruff format --check .` — czysto.
2. `python -m pytest -q` — exit 0 (sprawdzaj **kod wyjścia**, nie przepuszczaj przez `| tail`).
3. `python -m eval.gate --split dev` (od v0.2.1 z `--source tekst`) — exit 0 (bez regresji F1). `--update-baseline` tylko świadomie i z uzasadnieniem w PR.
4. TDD: najpierw test, potwierdź, że pada, potem kod.
5. Testy bez sieci; prawdziwy OCR tylko w testach `@pytest.mark.slow`.

## Git
- `main` zawsze zielony; zmiany przez **PR** z gałęzi `etap/<etap>-<nazwa>` (zadania: `etap/<etap>/<id>`). CI (GitHub Actions) musi być zielone.
- Commity małe, konwencja `typ(zakres): opis` po polsku (`feat`, `fix`, `test`, `docs`, `chore`, `ci`).
- **Bez stopek `Co-Authored-By` i bez dopisków „Generated with …” w commitach i PR** (regulamin §4 — autorstwo zespołu).
- Nie commituj sekretów (`.env`), wyników (`output/`), dużych plików spoza `data/`.
- Pracując równolegle z innymi: trzymaj się plików swojego etapu (lista w planie etapu). Jeśli musisz zmienić plik spoza listy — opisz to w PR.

## Twarde reguły domenowe (skrót z kryteriów)
- Typ dokumentu **z treści**, nigdy z nazwy pliku. Nieznany dokument → plik `.json` z `{}`.
- JSON dokładnie wg `config/schemas/*.json` (kolejność kluczy, `null` gdy brak).
- Imiona w **mianowniku**; daty ISO; BZP `YYYY/BZP########`; TED `NNNNNN-YYYY`; `czynnosc_opis` = słownik wg `czynnosc_powod_id` z **pierwszego zarzutu**.
- LLM opcjonalny; jeśli jest — tylko firma z UE z polityką prywatności (zakres i miejsce przetwarzania). Domyślnie **bez LLM**.
