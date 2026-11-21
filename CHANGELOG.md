# Changelog

Format: etapy z roadmapy (`docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md`). Każdy wpis zawiera wynik bramki F1.

## v1.0.0 — wydanie zgłoszeniowe (SZKIC, do uzupełnienia przy scaleniu)

> Szkic przygotowany 22.11.2026 przed scaleniem PR-ów. Właściciel repo: popraw listę według faktycznie scalonych
> gałęzi, wpisz liczby z `python scripts/quality_report.py` po scaleniu E4 i usuń tę notkę. Notatki wydania dla
> GitHub Release: [docs/wydanie-v1.0.md](docs/wydanie-v1.0.md).

**E4+E5 — ekstrakcja** (`etap/E4-ekstrakcja`)
- Silnik pól sterowany YAML (`fields`/`lists`, ekstraktory, normalizatory, walidatory w rejestrach), reguły dla
  wszystkich pól 3 typów, imiona w mianowniku, trace (strona + fragment) dla GUI.

**E6 — bez LLM** (`etap/E6-bez-llm`)
- Decyzja `docs/decyzje/E6-bez-llm.md`: reguły spełniają bramkę etapu, 20/20 pkt za moc modelu, limit czasu UZP;
  warstwa LLM zostaje jako opcja (≤ 8B, dostawca z UE).

**E10 — rozszerzalność** (`etap/E10-nowy-typ`)
- Przykład 4. typu (orzeczenie KIO, 8 pól) wyłącznie konfiguracją w `examples/nowy-typ/`; test „0 linii kodu”,
  nowe pole w istniejącym typie samą konfiguracją; typ nieaktywny w `config/` (UZP: orzeczenie = `{}`).

**E11 — pakowanie i uruchomienie** (`etap/E11-docker`, `etap/E11-instalacja`, `etap/E11-limit-czasu`, `etap/E11-wydajnosc`)
- Docker Compose bez wymaganego `.env`, healthcheck, `scripts/smoke_docker.py` (wynik w kontenerze = CLI, także skan z OCR).
- `start.bat`/`start-gui.bat` same przygotowują środowisko (Python 3.13/3.14, `.venv`); instalacja działa też na
  Pythonie 3.15 (bez OCR); przypięte wersje `requirements-lock.txt`; CI na 3.13 i 3.14; „test jury” (`docs/test-jury.md`).
- Limit czasu UZP: `{}` dla każdego PDF przed przetwarzaniem, więc przerwany przebieg zostawia częściowe wyniki;
  pomiar czasu `scripts/bench_cases.py` (99% czasu to OCR skanów).

**E12 — dokumentacja i zgłoszenie** (`etap/E12-dokumentacja`, `etap/E12-raport-jakosci`, `etap/E12-demo`, `etap/kryteria-uzp-2111`)
- `docs/architektura.md`, `docs/zgloszenie.md` (checklista regulaminu, licencje), ustalenia UZP z 21.11 wieczorem.
- Raport jakości `scripts/quality_report.py` → `docs/raport-jakosci.md`.
- Scenariusz demo, prezentacja `docs/prezentacja.html`, GIF z GUI (plan B).

**GUI** (`etap/E9-dlaczego-typ`)
- „Dlaczego ten typ?” zdaniami po polsku (surowe cechy w „Szczegółach technicznych”); poprawka kontrastu
  podświetleń w PDF w trybie wysokiego kontrastu.

**Dane** (`etap/dane-iban-pl`)
- GT przelewów: numer rachunku z „PL”, gdy ma go dokument (96 pól) — ustalenie UZP; normalizator `iban` w E4 do zmiany.

| Bramka (pomiar 21.11 na gałęzi E4, Docker, OCR) | dev | holdout |
|---|---|---|
| F1 — dokumenty z tekstem | 0,999 | 0,997 |
| F1 — skany | 0,975 | 0,903 |
| Błędy klasyfikacji | 0 | 0 |
| Negatywy (tekst) | 12/12 | 10/10 |
| Czas: dokument z tekstem / skan (średnio) | 0,01 s / 3,95 s | |

## v0.3.0 — E3: klasyfikacja + E8+E9: aplikacja (2026-11-21)

- Klasyfikacja sterowana YAML: tytuł jako linia nagłówka (z rozstrzelonymi literami), wzorce strukturalne, `required_any`, `min_score`/`min_margin`, pewność z marginesu, uzasadnienie (`evidence`) w trace.
- Globalne `config/classify.yaml`: kara za nagłówki obcych dokumentów liczona per typ, z automatycznym zwolnieniem własnego tytułu (`ignore_foreign`) — nowy typ dodawany samą konfiguracją.
- Testy odporności: syntetyczne dokumenty spoza puli, warianty OCR/tytułu, sygnatura sprawy w nagłówku, losowe nazwy plików; zestaw kontrolny 24 dokumentów.
- Aplikacja (drugi członek zespołu): API z zadaniami w tle (upload wielu PDF, status, PDF/JSON/ZIP) i GUI bez kroku budowania (Gov.pl, PDF.js lokalnie): wgrywanie, wyniki klasyfikacji, PDF obok pól z podświetleniem źródła, edycja wartości, `start-gui.bat`, test dymny.

| Bramka | przed | po |
|---|---|---|
| Błędy klasyfikacji dev / holdout | 5 / 2 | 0 / 0 |
| Negatywy odrzucone (tekst) dev / holdout | 9/12 / 8/10 | 12/12 / 10/10 |
| Syntetyczne negatywy | 1/9 | 9/9 |
| Zestaw kontrolny | 18/24 | 24/24 |

## v0.2.1 — E2b: skany (2026-11-21)

- 30 syntetycznych skanów UZP (bez warstwy tekstowej, z GT) w `data/train/skany/`; podział dev/holdout 23/7.
- OCR obowiązkowy (`rapidocr` + `onnxruntime` w `requirements.txt`) i ~4× szybszy: **2,99 s/str.** (`docs/decyzje/E2b-ocr-wydajnosc.md`).
- Ewaluacja świadoma skanów: GT `X.pdf → X.json`, typ z kluczy GT, metryki `tekst`/`skan`, `eval.gate --source`.
- Trace z `ocr_used`, `backend`, `warnings`; czyszczenie artefaktów OCR tylko na stronach z OCR.
- CI bramkuje dokumenty z tekstem (`--source tekst`); testy z prawdziwym OCR oznaczone `ocr_live`.
- Dokumentacja zespołu: `AGENTS.md`, `CLAUDE.md`, `docs/kryteria-uzp.md`, zakres v1.0, plan E8+E9.

| Bramka | wynik |
|---|---|
| Skany wczytane z OCR | 30/30 |
| Pokrycie GT na skanach | cyfrowe 100%, dosłowne 91,0%, razem 94,4% |
| Pokrycie GT na dokumentach z tekstem | 1460/1460 |
| Skany: negatywy / błędy klasyfikacji | 3/3 / 0 |

## v0.2.0 — E2: ingest produkcyjny (2026-11-21)

- Wymienne backendy PDF (pypdf, pdfplumber, pypdfium2) z fallbackiem; wybrany **pypdfium2** (benchmark: `docs/decyzje/E2-backend-pdf.md`).
- Czyszczenie tekstu jako konfigurowalna lista kroków na całym dokumencie (stopki usuwane z zachowaniem pierwszego wystąpienia; bez `dashes`, bo GT zachowuje „–”).
- `Document.page_offsets` / `page_of`, `backend`, `warnings`; `IngestError` z polskimi komunikatami; walidacja konfiguracji fail-fast.
- Opcjonalny OCR (rapidocr, polskie znaki, modele w paczce) dla stron bez tekstu, cache `output/.cache/ocr` (`docs/decyzje/E2-ocr.md`).
- Miara pokrycia wartości GT w tekście (`python -m eval.ingest_coverage`), fixture'y uszkodzonych PDF i testy odporności.
- Ustalenie UZP: LLM wyłącznie u firmy z polityką prywatności (zakres i miejsce przetwarzania danych).

| Bramka | wynik |
|---|---|
| PDF-y wczytane bez wyjątku | 196/196 |
| Pokrycie wartości GT w tekście | 1460/1460 (100%) |
| F1 dev / holdout (ekstrakcja = zaślepki) | 0.000 / 0.000 |
| Negatywy odrzucone dev / holdout | 12/15 / 11/13 |

## v0.1.0 — E1: harness jakości (2026-11-21)

- Ruff, `pyproject.toml`, pre-commit (szybkie testy w hooku), pin `ruff==0.17.6`.
- Deterministyczny podział danych `dev`/`holdout` (`data/splits.yaml`, 46/14).
- Kontrakt kształtu wyniku (`odw2json/schema.py`); wszystkie pliki GT UZP przechodzą walidację.
- LLM record/replay (kasety w `tests/cassettes/`, tryby live/record/replay/auto, licznik zużycia).
- Strukturalne logi JSONL, `run_id`, podsumowanie przebiegu (`output/.logs/`).
- Bramka regresji F1 `python -m eval.gate` z baseline per split; ścisła kontrola negatywów (`{}`), błędy klasyfikacji porównywane jako zbiory.
- GitHub Actions (Ubuntu + Windows): lint, pytest, bramka dev/holdout, smoke na czystym venv, docker build. `.dockerignore`.
- Ustalenia UZP: kod 6 ze skośnikiem, kod 12, `{}` dla dokumentów spoza puli; wariant bez LLM w roadmapie (E6).

| Bramka | dev | holdout |
|---|---|---|
| F1 (ekstrakcja = zaślepki) | 0.000 | 0.000 |
| Negatywy odrzucone | 12/15 | 11/13 |
| Błędy klasyfikacji | 5 | 2 |
| Błędy schematu / pipeline | 0 / 0 | 0 / 0 |

## v0.0.1 — E0: fundament (2026-11-21)

Szkielet: kontrakty, rejestr typów z YAML, pipeline input→output, CLI, zalążek API, skrypt F1, dane treningowe UZP.
