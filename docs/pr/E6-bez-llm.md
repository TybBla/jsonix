## E6: decyzja „bez LLM” na piśmie

Gałąź `etap/E6-bez-llm` → `main`. Tylko dokumentacja: `docs/decyzje/E6-bez-llm.md`.

- **Kryterium z roadmapy:** bez LLM, jeśli strata F1 jest mniejsza niż wartość punktów za rozmiar modelu. Bez LLM = 20 pkt, ale model ≤ 8B też = 20 pkt, więc decyzja wynika z F1 reguł i czasu przetwarzania.
- **Liczby z reguł** (v0.4.0, `eval/baseline.json`): dokumenty z tekstem dev 0,999 / holdout 0,997; skany dev 0,977 / holdout 0,912, w tym przelew 0,882 / 0,933 i pełnomocnictwo 0,980 / 0,833 (3 dokumenty); klasyfikacja 0 błędów. Bramka etapu E6 (F1 ≥ 0,95, różnica dev–holdout ≤ 0,03) spełniona z zapasem.
- **Luka na skanach** wynika z błędów OCR, których LLM nie naprawi. Dochodzi limit czasu UZP: 99% czasu to dziś OCR, a każde zapytanie do LLM to sekundy plus limity API.
- **Decyzja:** w oddawanej konfiguracji `llm_enabled: false`, a warstwa LLM zostaje jako opcja (tylko model ≤ 8B z UE).

Liczby z `eval/baseline.json` na `main` (v0.4.0); raport per pole: `python scripts/quality_report.py`.
