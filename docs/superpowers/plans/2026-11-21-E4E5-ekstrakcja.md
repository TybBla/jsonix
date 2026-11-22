# E4+E5 — Ekstrakcja (scalone): plan etapu (zakres v1.0)

> Dla agentów: przeczytaj `AGENTS.md`, `docs/kryteria-uzp.md` (zwłaszcza §4 — jak liczone jest F1, §5 — mianownik imion, formaty) i ten plan. Realizuj TYLKO swoje zadanie, w TDD. Osobny worktree, gałąź `etap/E4/<id>` z `etap/E4-ekstrakcja`. Commity **bez stopek `Co-Authored-By`**. Przed commitem: ruff check + ruff format --check + `python -m pytest -q -m "not slow"` (exit 0) + `python -m eval.gate --split dev --source tekst` (bez regresji; poprawa F1 jest oczekiwana — NIE aktualizuj baseline, robi to orkiestrator). Polecenia uruchamiaj osobno. Nie pushuj.

**Cel:** wypełnić wszystkie pola trzech typów dokumentów **regułami sterowanymi YAML** (rdzeń F1 + punkty za konfigurowalność), z trace (strona + fragment) dla każdej wartości. LLM nie w tym etapie (E6).
**Gałąź etapu:** `etap/E4-ekstrakcja` (z `etap/E3-klasyfikacja`). Tag: `v0.4.0`.

## Decyzje projektowe orkiestratora (wiążące)
1. **Silnik ogólny, typ w YAML.** `odw2json/extract/engine.py` interpretuje sekcję `fields:` w `config/doctypes/<typ>.yaml`. Kod nie zna nazw pól UZP.
2. **DSL pola** (klucz = ścieżka w szablonie, np. `ZamowieniePubliczne.numer_bzp`, listy: `Odwolujacy[].nip`):
   ```yaml
   fields:
     przelew_bankowy.kwota:
       type: amount            # str | int | amount | date | iban | digits | email | name | company | enum | lookup
       scope: {after: 're:kwota', before: 're:data|tytul', max_chars: 400}   # opcjonalny zakres wyszukiwania
       extract:                # lista ekstraktorów w kolejności; pierwszy z wynikiem wygrywa
         - label: ['kwota przelewu', 'kwota operacji', 'kwota']   # wartość po etykiecie (dopuszcza \s+ i nową linię, ':' opcjonalny)
         - regex: '(?P<v>\d[\d ]*[,.]\d{2})\s*(pln|zl)'           # grupa nazwana v
       normalize: [amount]     # nazwy z rejestru normalizatorów
       validate: {regex: '^\d+\.\d{2}$'}   # niepoprawna → null (FP = FN; null przy braku w GT = TN)
     OdwolanieKIO.czynnosc_opis:
       derived: {lookup: czynnosc_powod, from: OdwolanieKIO.czynnosc_powod_id}
   lists:
     Odwolujacy:               # podział na elementy listy
       split: {start: 're:^odwolujac', end: 're:^zamawiajac', item_sep: 're:^\s*\d+\)'}   # sekcje/bloki
       max_items: 5
   ```
   Ekstraktory: `label`, `regex`, `section_line` (n-ta linia po nagłówku sekcji), `near` (wartość typu X najbliżej frazy), `const`, `derived/lookup`. Rejestry: `EXTRACTORS`, `NORMALIZERS`, `VALIDATORS` (dekorator rejestrujący), żeby nowe typy/pola dodawać konfiguracją.
3. **Normalizatory** (osobny moduł `odw2json/extract/normalize.py`, czyste funkcje): `date` (DD.MM.RRRR, „11 września 2026 r.”, RRRR-MM-DD → ISO), `amount` (`1 234,56 zł` → 1234.56), `iban` (26 cyfr bez PL/spacji), `digits` (NIP/KRS/REGON/PESEL – same cyfry, długości 10/10/9|14/11) — **PESEL jako string** (w GT wszystkie wartości to stringi; przykład w schemacie UZP ma liczbę, ale oceniane jest GT), `bzp` (`2026/BZP 00551100` → `2026/BZP00551100`), `ted` (`2025/S 112-383751` → `383751-2025`), `email`, `ws` (zwinięcie białych znaków), `ocr_fix` (np. `Sp. z 0.0.`→`Sp. z o.o.`, `0.0.`→`o.o.` w formach prawnych), `company` (forma prawna jak w dokumencie, bez rozwijania), `name_nominative` (patrz 4).
4. **Mianownik imion** (`odw2json/extract/names.py`): reguły odmiany polskich imion i nazwisk (celownik/dopełniacz/narzędnik → mianownik), słownik imion z danych treningowych + reguły końcówek (-owi/-emu/-iej/-ej/-ą/-a…), z zachowaniem polskich znaków; testy na parach (tekst ↔ GT) z `data/train`. Niepewny wynik → zostaw formę z tekstu (pole oceniane dokładnie, ale null też jest FN).
5. **Trace:** każda wartość → `FieldResult(path, value, method, source_snippet, page)`; snippet = linia/fragment z tekstu po czyszczeniu; `page` z `Document.page_of(offset)`.
6. **Strojenie tylko na `dev`**; holdout raz na końcu etapu. Raport F1 per pole po każdym zadaniu (`python -m eval.gate --split dev --source tekst` + `--source skan` gdy dotyczy).

## Zadania i kolejność
| Fala | Zadanie | Model | Pliki |
|---|---|---|---|
| 1 | **T1 Silnik + DSL + typ wzorcowy „przelew”** | Opus | `odw2json/extract/{__init__,engine}.py`, `odw2json/config_loader.py` (model `fields`/`lists`), `config/doctypes/przelew.yaml` (`fields`), `tests/test_extract_engine.py`, `tests/test_extract_przelew.py`, `docs/nowy-typ-dokumentu.md` (sekcja `fields`) |
| 1 | **T2 Normalizatory** | Haiku | `odw2json/extract/normalize.py`, `tests/test_normalize.py` |
| 1 | **T3 Mianownik imion** | Opus | `odw2json/extract/names.py`, `tests/test_names.py` |
| 2 | **T4 Odwołanie** (wszystkie pola, listy, `czynnosc_powod_id` z pierwszego zarzutu — słownik fraz → id) | Opus | `config/doctypes/odwolanie.yaml` (`fields`, `lists`), `config/lookups/*`, `tests/test_extract_odwolanie.py` |
| 2 | **T5 Pełnomocnictwo** (mocodawcy, podpisujący, pełnomocnicy, PESEL, typ osoby) | Opus | `config/doctypes/pelnomocnictwo.yaml`, `tests/test_extract_pelnomocnictwo.py` |
| 3 | **T6 Pętla jakości** (najgorsze pola dev, skany: OCR-fix) | Opus | konfiguracje + normalizatory |

T1–T3 równolegle: T1 definiuje interfejs rejestrów (`NORMALIZERS[name](value:str)->Any|None`, `normalize_name(text:str)->str`); do czasu scalenia T2/T3 T1 używa minimalnych wersji lokalnych w `engine.py` za tym samym interfejsem, które po scaleniu zastąpi import z `normalize.py`/`names.py`.

## Bramka E4+E5
- F1 dev (tekst) ≥ 0,90 i holdout raportowany; skany raportowane osobno;
- każde pole z F1 < 0,8 opisane (przyczyna) w `docs/decyzje/E4-ekstrakcja.md`;
- 0 błędów schematu; trace z `page`+`source_snippet` dla ≥ 90% niepustych wartości;
- dodanie pola do istniejącego typu samą konfiguracją pokazane testem;
- CI zielone; review etapu (Opus); PR → `main`, tag `v0.4.0`.
