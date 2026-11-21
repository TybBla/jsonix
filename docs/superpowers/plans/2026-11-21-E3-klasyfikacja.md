# E3 — Klasyfikacja: plan etapu (zakres v1.0)

> Dla agentów: przeczytaj `AGENTS.md` i `docs/kryteria-uzp.md`. Realizuj TYLKO swoje zadanie, w TDD (test → pada → kod). Osobny worktree, gałąź `etap/E3/<id>` z `etap/E3-klasyfikacja`. Commity **bez stopek `Co-Authored-By`** (AGENTS.md). Przed commitem: ruff check + ruff format --check + `python -m pytest -q -m "not slow"` (exit 0, sprawdzaj kod wyjścia) + `python -m eval.gate --split dev --source tekst`. Polecenia uruchamiaj osobno. Nie pushuj.

**Cel:** typ dokumentu rozpoznawany **wyłącznie z treści**, 100% na dev i holdout (tekst + skany), przewidywalna pewność i odporność na dokumenty spoza puli, **sterowane konfiguracją** (rozszerzalność = punkty w finale).
**Gałąź etapu:** `etap/E3-klasyfikacja`. Tag: `v0.3.0`.

## Stan wyjściowy (pomiar orkiestratora)
- Bramka `--source tekst`: 5 błędów na dev (+2 na holdout, te same pliki w innych sprawach); skany: 0 błędów, negatywy 3/3.
- Przyczyny:
  1. `przyklad_02/pelnomocnictwo.pdf`, `przyklad_32/pelnomocnictwo.pdf`: tytuł rozstrzelony „P E Ł N O M O C N I C T W O” → frazy nie trafiają (wyniki 3,0 vs 3,0 z odwołaniem; 2,0 < próg).
  2. `negatywne/2025_S 112-383751.pdf` (+ kopia w `przyklad_04`, ogłoszenie TED): przelew 4,0 — ogólne słowa („rachunek”, „kwota”) wystarczają do progu.
  3. `negatywne/Broszura_JPK_FA(2).pdf`: przelew 3,0 z tego samego powodu.
- Obecny klasyfikator: obecność fraz `strong` (+2), `weak` (+1), `negative` (−3) z YAML, próg `min_score`, typ o najwyższym wyniku.

## Decyzje projektowe orkiestratora (wiążące)
1. **Cechy w YAML, silnik w kodzie.** Rozszerzamy `classify:` w `config/doctypes/*.yaml` o (wszystko opcjonalne, wstecznie zgodne):
   - `title: [frazy]` — szukane w **nagłówku** (pierwsze `header_chars`, domyślnie 600 znaków) po normalizacji, w tym **zwinięciu rozstrzelonych liter** („P E Ł N O …” → „pelnomocnictwo”); waga `weights.title` (domyślnie 4).
   - `patterns: [{regex: ..., weight: ...}]` — cechy strukturalne (np. przelew: IBAN 26 cyfr **i** kwota z walutą w pobliżu etykiety; odwołanie: „Zarzut nr”/„Odwołujący:”); regex na tekście znormalizowanym.
   - `required_any: [frazy|regex]` — bez spełnienia przynajmniej jednej typ jest wykluczony (np. przelew wymaga IBAN-u).
   - `min_score`, `min_margin` (przewaga nad drugim typem; poniżej → `None`).
   - Wagi `strong/weak/negative` konfigurowalne (`weights:`), domyślne jak dziś.
2. **Pewność** `confidence` = funkcja marginesu i wyniku (udokumentowana), w [0,1]; `scores` i lista trafionych cech (`matched`) trafiają do `Classification` przez istniejące pole `scores` lub nowe opcjonalne pole `evidence: list[str]` w kontrakcie (dozwolone rozszerzenie z wartością domyślną — orkiestrator zatwierdza w T1). Evidence zapisujemy w trace (transparentność; GUI pokaże „dlaczego ten typ”).
3. **Bez LLM** (zakres v1.0). **Bez użycia nazwy pliku ani katalogu.**
4. Strojenie wyłącznie na `dev`; `holdout` sprawdzany na końcu, raz.

## Na co zwrócić uwagę przy review
1. Żadna cecha nie może opierać się na nazwie pliku/ścieżce (test: te same PDF-y pod losowymi nazwami → identyczny wynik).
2. Zwijanie rozstrzelonych liter nie może sklejać zwykłych krótkich słów („a i w z”) w nagłówku w fałszywe frazy — tylko ciągi ≥ 5 pojedynczych liter.
3. Dokumenty OCR (skany) muszą nadal klasyfikować się poprawnie — błędy OCR (ł→l, Ę→E) są neutralizowane przez normalizację bez polskich znaków.
4. Dokument nieznany musi dawać `None` także, gdy zawiera kilka słów z naszej domeny (ogłoszenia BZP/TED, wyroki KIO, broszury).
5. Konfiguracja nowego typu dokumentu (E10) musi działać tymi samymi mechanizmami — bez zmian w kodzie.

---

### T1 — Silnik cech i konfiguracja (Sonnet, high)
**Pliki:** `odw2json/classify/__init__.py`, `odw2json/classify/features.py` (nowy), `odw2json/textnorm.py` (funkcja zwijania rozstrzelonych liter), `odw2json/config_loader.py` (model `ClassifyConfig` — nowe pola), `odw2json/contracts.py` (tylko opcjonalne `evidence` w `Classification`, jeśli potrzebne), `odw2json/pipeline.py` (evidence w trace), `config/doctypes/*.yaml`, `tests/test_classify.py` (nowy), `tests/test_config_loader.py`, `docs/nowy-typ-dokumentu.md` (sekcja `classify:`).
- Wdrożenie decyzji 1–2; walidacja nowych pól w pydantic z czytelnymi błędami.
- Konfiguracja trzech typów: tytuły („odwołanie”, „pełnomocnictwo”, „potwierdzenie (realizacji) przelewu/operacji”), wzorce strukturalne, `required_any` dla przelewu (IBAN), `min_margin`.
- Testy (TDD): rozstrzelony tytuł → pełnomocnictwo; TED/JPK → `None`; wszystkie `przyklad_*` + skany (OCR z cache — test `slow`) poprawnie; losowe nazwy plików → ten sam wynik; zwijanie liter nie skleja „a i w z”; walidacja błędnego YAML; evidence obecne w trace.
- **Done:** bramka `--split all --source tekst` i `--source skan`: 0 błędów klasyfikacji, negatywy 100%; baseline zaktualizowany (orkiestrator zatwierdza różnice).

### T2 — Odporność na dokumenty spoza puli (Sonnet, medium) · po T1
**Pliki:** `tests/test_classify_robustness.py`, `tests/fixtures/classify/*.txt` (syntetyczne teksty), `docs/decyzje/E3-klasyfikacja.md`.
- Zestaw syntetycznych tekstów negatywnych (bez PDF; test bezpośrednio na `classify` z `Document`): wyrok KIO, postanowienie KIO, ogłoszenie o zamówieniu BZP, zawiadomienie o wyborze oferty, faktura, pismo do zamawiającego, SWZ (fragment), umowa — każdy z „podchwytliwymi” słowami domenowymi; oraz warianty pozytywów: tylko pierwsza strona, tekst z błędami OCR (ł→l, Ę→E, 0↔o), tytuł małymi literami, tytuł rozstrzelony.
- Raport `docs/decyzje/E3-klasyfikacja.md`: macierz pomyłek dev/holdout/syntetyki, margines decyzji per typ, znane ograniczenia.
- **Done:** wszystkie syntetyki poprawnie; jeśli któryś wymaga zmiany konfiguracji — zgłoś (zmienia T1 / orkiestrator).

## Bramka E3
- 0 błędów klasyfikacji na dev i holdout (tekst i skany), negatywy 100%;
- syntetyczne negatywy i warianty pozytywów poprawnie;
- test „losowe nazwy plików” zielony; evidence w trace;
- `docs/nowy-typ-dokumentu.md` opisuje nowe pola `classify:`;
- CI zielone; review etapu (Sonnet high) bez blokerów; PR → `main`, tag `v0.3.0`.
