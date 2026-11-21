# Podział pracy — sektory A / B / C

Zasady wspólne:
- `main` = działająca baza. Pracujesz na swojej gałęzi, merge przez PR (małe, często).
- **Przed PR:** `python -m pytest -q` zielone + `python -m eval.score --pred output --gt data/train` (wynik F1 w opisie PR).
- `odw2json/contracts.py` zmieniamy tylko za zgodą całej trójki.
- Każdy sektor ma działający stub na `main`, więc pipeline działa end-to-end od początku.
- Sync: godz. 6 (pierwsze F1 end-to-end), godz. 12 (lista najgorszych pól), godz. 19 freeze.

## A — `feat/a-ingest-classify`
Pliki: `odw2json/ingest/`, `odw2json/classify/`, sekcje `classify:` w `config/doctypes/*.yaml`.
1. Napraw 4 błędy bazowej klasyfikacji (stan na starcie: 190/194):
   - `negatywne/2025_S 112-383751.pdf` → wykryty jako przelew (ma być nieznany)
   - `negatywne/Broszura_JPK_FA(2).pdf` → przelew (ma być nieznany)
   - `przyklad_02/pelnomocnictwo.pdf` → odwołanie
   - `przyklad_32/pelnomocnictwo.pdf` → nieznany
2. Wagi pozycji (tytuł/nagłówek pierwszej strony), kalibracja progów; dorzuć własne negatywy (wyrok KIO, ogłoszenia, faktury).
3. LLM fallback przy niskiej pewności (lista typów z rejestru + „nieznany”).
4. OCR fallback (strony bez tekstu) — Tesseract `pol` / rapidocr, bez GPU; czyszczenie tekstu (dzielenie wyrazów, spacje, ligatury).
5. Po zrobieniu swojego: pomoc sektorowi B przy najgorszych polach.

## B — `feat/b-extraction`
Pliki: `odw2json/extract/`, `odw2json/normalize/` (nowy), `odw2json/llm.py`, `config/doctypes/*.yaml` (`fields:`, `llm:`), `config/prompts/`, `config/lookups/`.
1. Format sekcji `fields:` w YAML (metoda: regex/llm/derived, typ, normalizator, walidator) + loader.
2. Regexy + normalizacja + walidacja sum kontrolnych: KRS, NIP, REGON, PESEL, IBAN (26 cyfr, bez PL), kwota (float), daty (słownie i liczbowo → ISO), BZP (`YYYY/BZP########`), TED (`NNNNNN-YYYY`).
3. LLM dla pól semantycznych: nazwy podmiotów, osoby (mianownik!), tytuł zamówienia, `czynnosc_powod_id` (tylko pierwszy zarzut), role (pełnomocnik, prowadzący postępowanie). Prompt z opisów pól w `data/oczekiwane-json/`.
4. Merge regex/LLM, walidacja → `null` przy niepewności (FP = FN w F1; null przy braku w GT = TN). Wynik dokładnie wg szablonu, trace dla każdego pola.
5. Hold-out: ~15 spraw nie używać w promptach/few-shot; raportuj F1 osobno na hold-out.

## C — `feat/c-app`
Pliki: `odw2json/cli.py`, `odw2json/api/`, `web/`, `Dockerfile`, `docker-compose.yml`, `README.md`, `docs/`.
1. GUI React (Vite+TS) wg `web/README.md`, `web/dist` commitowany.
2. API: wyniki z trace, podgląd PDF, (opcjonalnie) edycja YAML typów.
3. Docker Compose + test na czystym Windowsie: `pip install -r requirements.txt` → `start.bat`.
4. Dokumentacja wymagana do nagrody: architektura, konfiguracja typu, dodanie nowego typu (`docs/nowy-typ-dokumentu.md` — demo z prawdziwym nowym typem, np. „wyrok KIO”).
5. Checklista zgłoszenia (tytuł, link, README, wyniki testów F1).

## LLM (decyzja 2026-11-21)
- Główny: **Mistral Ministral 3 8B** przez `https://api.eu.mistral.ai/v1` (Apache 2.0, firma z UE, inferencja w UE, ~0,17 $/1M tok.).
- Test na 5 dokumentach: Ministral 3 **3B** vs 8B — bierzemy 3B, jeśli F1 nie spada (więcej punktów za rozmiar).
- Fallback: **Bielik-11B-v3.0** (CloudFerro Sherlock, Apache 2.0, polski) — JSON mode niepotwierdzony, wymuszać promptem + walidacją.
- Do sprawdzenia na starcie: `models.list` na endpoincie UE zawiera wybrany model; nazwa modelu w `.env`.
- Qwen/DeepSeek odrzucone decyzją zespołu.
