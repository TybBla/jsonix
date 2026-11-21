# Changelog

Format: etapy z roadmapy (`docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md`). Każdy wpis zawiera wynik bramki F1.

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
