## E6: decyzja „bez LLM” na piśmie

Gałąź `etap/E6-bez-llm` → `main`. Tylko dokumentacja: `docs/decyzje/E6-bez-llm.md`.

- **Kryterium z roadmapy:** bez LLM, jeśli strata F1 jest mniejsza niż wartość punktów za rozmiar modelu. Według UZP bez LLM dostaje maksimum (20 pkt), więc LLM nie może tu niczego dodać.
- **Liczby z reguł** (pomiar na gałęzi E4, Docker z OCR):
  - tekst: dev 99,9%, holdout 99,7%;
  - skany: dev 97,5%, holdout 90,3%;
  - klasyfikacja: 0 błędów.

  Bramka etapu E6 (F1 ≥ 0,95, różnica dev–holdout ≤ 0,03) jest spełniona z zapasem.
- **Luka na skanach** wynika z błędów OCR, których LLM nie naprawi. Dochodzi limit czasu UZP: 99% czasu to dziś OCR, a każde zapytanie do LLM to sekundy plus limity API.
- **Decyzja:** w oddawanej konfiguracji `llm_enabled: false`, a warstwa LLM zostaje jako opcja (tylko model ≤ 8B z UE).

Po scaleniu E4 potwierdź liczby raportem `python scripts/quality_report.py` (PR `etap/E12-raport-jakosci`).
