# E6: pomiar wariantu hybrydowego (reguły + LLM dla pól null)

## Co
- `odw2json/llm_fill.py`: LLM uzupełnia tylko pola, w których reguły dały `null`, na wycinku tekstu (nagłówek +
  okna wokół fraz z promptu, limit 6000 znaków). Odpowiedź przechodzi normalizatory i walidatory z YAML oraz
  kontrolę „jest w tekście”. Błąd LLM zostawia wynik reguł.
- `odw2json/pipeline.py`: wypełniacz tylko przy `llm_enabled: true`. **Domyślnie `false` (bez zmian w oddawanej
  konfiguracji).** API/GUI nie używa wariantu hybrydowego.
- `odw2json/llm.py` (poza samym `llm_fill`): odstęp między zapytaniami (`min_interval_s`, env
  `LLM_MIN_INTERVAL_S`), dostęp anonimowy (`LLM_API_KEY=anonim`, np. OVH), env `LLM_TEMPERATURE`,
  `LLM_EXTRA_BODY`, `LLM_CASSETTE_DIR`; odpowiedź uciętą na `max_tokens` zgłasza jako błąd i nie zapisuje kasety.
- Prompty `config/prompts/*.md` (+ `wspolne.md`), nakładka `config/app.llm.yaml`, `config/llm.yaml`: sekcja
  `hybryda`, `max_tokens: 4000`.
- `scripts/bench_hybryda.py`: bramka F1 bez i z LLM + ocena każdego uzupełnienia względem GT.
- Wyniki i wnioski: `docs/decyzje/2026-11-21-llm-darmowe-vs-bez.md`.

## Wynik
Dev, model Olala-v1.0-mini-7A1B (OVH, ≤ 8B):
- skany: F1 0,9919 (reguły) → **0,9899** (hybryda); jedyne uzupełnienie było zmyślone (KRS przypisany
  Zamawiającemu, w GT null); 0 poprawnych; czas 10,6 s → 584 s,
- tekst (przebieg przerwany po 7 dokumentach z odpowiedzią): 0 uzupełnień, F1 0,9990 bez zmian.
- Reguły mają na dev FN = 0, więc wariant „LLM dla pól null” nie ma czego odzyskać. **Decyzja E6 zostaje: bez LLM.**
Holdout nieużyty.

## Harness
- `ruff check .` i `ruff format --check .`: czysto.
- `pytest -q` (Python 3.13 z OCR): 1341 passed, 29 skipped, kod 0.
- `python -m eval.gate --split dev --source tekst`: kod 0, bez regresji (LLM wyłączony).
- Kod przejrzany przez niezależną recenzję (4 obszary, każde znalezisko weryfikowane): 9 potwierdzonych błędów
  (m.in. zmyślone daty i e-maile przechodziły kontrolę, 1.0 w polu int dawało 10) poprawionych z testami.
