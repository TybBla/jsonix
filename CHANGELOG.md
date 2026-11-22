# Changelog

Format: etapy z roadmapy (`docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md`). Każdy wpis zawiera wynik bramki F1.

## v1.0.1 — nowy wygląd GUI (2026-11-22)

- **Źródło wartości w dymku (#28):** zamiast stałej linii „Źródło: strona N, …” pod każdą wartością jest mała ikonka „i” obok wartości. Dymek ze stroną, fragmentem i ostrzeżeniami otwiera się po najechaniu, kliknięciu albo z klawiatury (Enter/Spacja; Esc zamyka). Ostrzeżenia mają osobną ikonkę (trójkąt z „!”). Czytnik ekranu dostaje opis źródła bez otwierania dymka. Podświetlanie źródła w PDF bez zmian.
- **Nagłówek:** tytuł „jsonix” przy lewej krawędzi, większy, bez logo.
- **Czytelność:** szary tekst zmieniony z #656565 na #4a4a4a (kontrast 8,9:1 na bieli i 7,9:1 na jasnoszarym, poziom WCAG AAA).
- **Stopka:** „jsonix v1.0.1 · projekt HackNation 2026 (zadanie UZP)” oraz linki: Deklaracja dostępności, Dokumentacja API, Kod źródłowy.
- Ekstrakcja, klasyfikacja i wyniki F1 bez zmian względem v1.0.0.

## v1.0.0 — wydanie zgłoszeniowe (2026-11-22)

Notatki dla GitHub Release: [docs/wydanie-v1.0.md](docs/wydanie-v1.0.md). Zakres: wszystko scalone od v0.4.0.

- **Limit czasu UZP (#13):** `{}` dla każdego PDF przed przetwarzaniem, więc przerwany przebieg zostawia częściowe wyniki; zapis wyników atomowy (plik nigdy w połowie); dokumenty z tekstem przetwarzane przed skanami (OCR na końcu).
- **Przelewy ze skanów (#21):** etykiety rozbite przez OCR, daty bez kropek; dev@skan F1 0,977 → 0,992, holdout@skan 0,912 → 0,922.
- **Pełnomocnictwa ze skanów (#19):** dwa podpisy w jednej linii, konsolidacja wyników; holdout@skan 0,958. Uwaga: holdout@skan pełnomocnictw nie jest niezależny (poprawki dopasowano na tych samych skanach).
- **Sonda odporności i poprawki YAML (#22):** synonimy etykiet i warianty sformułowań sprawdzane syntetycznie, poprawki wyłącznie w `config/doctypes/*.yaml`.
- **Porządki testów (#20):** uporządkowane i ujednolicone testy.
- **Raport jakości (#15):** `scripts/quality_report.py` → `docs/raport-jakosci.md` (wygenerowany po pomiarze skanów).
- **Wdrożenie na VM jury (#23):** `RUN.md` dla oceniających, profil `config/app.jury.yaml` (wyniki tylko w katalogu wyjściowym), `scripts/deploy-vm.sh` z `--self-test`; instrukcja `docs/vm-jury.md`.
- **Bez LLM (#12):** decyzja `docs/decyzje/E6-bez-llm.md` — reguły spełniają bramkę, 20/20 pkt za moc modelu, dane nie opuszczają maszyny.
- **Dokumentacja (#10) i demo (#16):** `docs/architektura.md`, `docs/zgloszenie.md`, scenariusz demo, prezentacja.
- **Repozytorium** publiczne: https://github.com/TybBla/jsonix.

| Bramka | F1 | odwołanie | pełnomocnictwo | przelew | negatywy |
|---|---|---|---|---|---|
| dev tekst | 0,999 | 0,998 | 1,000 | 1,000 | 12/12 |
| holdout tekst | 0,997 | 0,997 | 1,000 | 0,994 | 10/10 |
| dev skany | 0,992 | 0,997 | 0,980 | 0,987 | 3/3 |
| holdout skany | 0,967 | 1,000 | 0,943* | 0,968 | 3/3 |

Skany przed → po (baseline po #19, #21, #22 w #25): dev 0,977 → 0,992, holdout 0,912 → 0,967. \* Holdout@skan pełnomocnictw nie jest niezależną oceną (błędy diagnozowano na holdoucie, #19). Razem (tekst + skany): dev 0,998 (negatywy 15/15), holdout 0,994 (13/13). Czas przy zimnym cache OCR: dokument z tekstem 0,04 s, skan 3–8 s (`docs/raport-jakosci.md`, #27).

## v0.4.0 — E4+E5: ekstrakcja + E11: instalacja i Docker (2026-11-22)

- Silnik ekstrakcji sterowany YAML (`odw2json/extract/engine.py`): pola i listy z `config/doctypes/*.yaml`, rejestry ekstraktorów/normalizatorów/walidatorów, trace z indeksami list, stroną i fragmentem źródła.
- Reguły 3 typów (przelew, pełnomocnictwo, odwołanie), normalizatory (daty PL, kwoty, IBAN z „PL” jak w dokumencie, BZP/TED), mianownik imion (także wersaliki).
- Odporność na inne sformułowania (synonimy etykiet, formaty kwot, nazwiska wersalikami) z testami wariantów.
- Dane referencyjne: numery rachunków z „PL” zgodnie z ustaleniem UZP z 21.11.
- Stabilność OCR pod obciążeniem (OpenBLAS 1 wątek, ponowienia, brak cache pustych wyników, slot międzyprocesowy).
- Drugi członek zespołu: instalacja przez `start.bat` (venv, plik ograniczeń wersji), Docker Compose z healthcheckiem, pomiar wydajności, nowe ustalenia UZP w kryteriach, „Dlaczego ten typ?” w GUI.

| Bramka | F1 | odwołanie | pełnomocnictwo | przelew | negatywy |
|---|---|---|---|---|---|
| dev tekst | 0,999 | 0,998 | 1,000 | 1,000 | 12/12 |
| holdout tekst | 0,997 | 0,997 | 1,000 | 0,994 | 10/10 |
| dev skany | 0,977 | 0,997 | 0,980 | 0,882 | 3/3 |
| holdout skany | 0,912 | 1,000 | 0,833 | 0,933 | 3/3 |

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
