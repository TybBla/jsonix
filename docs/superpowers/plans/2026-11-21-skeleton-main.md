# Szkielet `main` — plan implementacji

> **Dla agentów:** wymagany sub-skill: superpowers:executing-plans. Kroki to checkboxy (`- [ ]`).

**Cel:** baza na `main`, na której sektory A/B/C pracują równolegle: działa od początku do końca (input → output), ma zamrożone kontrakty, rejestr typów z YAML i skrypt F1.

**Architektura:** pakiet `odw2json/` (w katalogu głównym, a nie w `src/`, żeby `python -m odw2json` działało bez instalacji). Etapy ingest → classify → extract → write komunikują się dataclassami z `odw2json/contracts.py`. Typy dokumentów są w `config/doctypes/*.yaml`. Każdy etap ma prostą implementację bazową, którą sektory potem zastępują.

**Stack:** Python 3.13+, pypdf, PyYAML, pydantic 2, rapidfuzz, FastAPI, uvicorn, openai (klient OpenAI-kompatybilny), pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-odwolania2json-design.md`

## Ograniczenia globalne
- Python 3.13+; zależności w `requirements.txt`; foldery `input/` i `output/` w katalogu głównym.
- Wynik: `output/<case>/<nazwa_pdf_bez_rozszerzenia>.json`, JSON ściśle wg szablonu z `config/schemas/`.
- Dokument nieznany: zachowanie z `config/app.yaml: unknown_output` (`none` = brak pliku, `empty_file` = pusty plik).
- Trace tylko w `output/.trace/`, nigdy w wynikowym JSON-ie.
- Sekrety tylko w `.env` (w `.gitignore`); w repo jest `.env.example`.

## Na co zwrócić uwagę przy review
1. PDF bez tekstu albo uszkodzony: CLI nie może przerwać całego batcha, tylko loguje błąd i jedzie dalej (test w Task 3).
2. Nazwy plików ze spacjami i polskimi znakami (`negatywny przyklad.pdf`) muszą trafić do wyjścia pod tą samą nazwą (Task 3).
3. Pliki inne niż PDF w `input/` są ignorowane (Task 3).
4. Scorer: `null` u nas i `null` w GT to TN, a nie FP. Listy różnej długości dają nadmiar jako FP, brak jako FN (Task 4).
5. Plik wyjściowy jest kodowany w UTF-8 z `ensure_ascii=False` (Task 3).

---

### Task 1: Struktura, konfiguracja, kontrakty, rejestr
**Pliki:** `requirements.txt`, `.gitignore`, `.env.example`, `config/app.yaml`, `config/llm.yaml`, `config/doctypes/{odwolanie,pelnomocnictwo,przelew}.yaml`, `config/schemas/{odwolanie,pelnomocnictwo,przelew}.json`, `config/lookups/czynnosc_powod.yaml`, `odw2json/{__init__,contracts,config_loader}.py`, `tests/test_config_loader.py`
**Produkuje:**
- `Document(path: Path, text: str, pages: list[str], ocr_used: bool = False)`
- `Classification(doc_type: str | None, confidence: float, method: str)`
- `FieldResult(path: str, value: Any, method: str, source_snippet: str | None = None, page: int | None = None)`
- `ExtractionResult(doc_type: str, data: dict, trace: list[FieldResult])`
- `DocTypeConfig` (pydantic): `id: str`, `output_template: str`, `classify: ClassifyConfig(strong: list[str], weak: list[str], negative: list[str], min_score: float)`, `fields: dict[str, dict] = {}`, `llm: dict = {}`, `template() -> dict` (głęboka kopia szablonu)
- `load_registry(config_dir: Path = CONFIG_DIR) -> dict[str, DocTypeConfig]`, `load_app_config(...) -> dict`, `load_lookup(name) -> dict`
- [ ] Test: `load_registry()` zwraca klucze `{"odwolanie","pelnomocnictwo","przelew"}`, a `template()` z odwołania ma klucze `OdwolanieKIO, Odwolujacy, Zamawiajacy, ZamowieniePubliczne`. `load_lookup("czynnosc_powod")[9] == "Decyzja o unieważnieniu postępowania"`.
- [ ] Implementacja, uruchomienie `pytest tests/test_config_loader.py`: ma przechodzić.

### Task 2: Etapy bazowe (ingest, classify, extract)
**Pliki:** `odw2json/ingest/__init__.py`, `odw2json/classify/__init__.py`, `odw2json/extract/__init__.py`, `odw2json/llm.py`, `tests/test_stages.py`
**Produkuje:** `ingest.load(path: Path) -> Document` (pypdf, tekst stron), `classify.classify(doc, registry) -> Classification` (punktacja słów kluczowych z YAML z normalizacją polskich znaków; wynik poniżej `min_score` daje `None`), `extract.extract(doc, cfg) -> ExtractionResult` (wersja bazowa: szablon z nullami plus `derived` z lookupów), `llm.LLMClient.from_config().complete_json(system, user) -> dict`.
- [ ] Test: na `data/train/przyklad_01` trzy PDF-y klasyfikują się poprawnie, a `data/train/przyklad_10/2025-OJS107-*.pdf` daje `None`.
- [ ] Implementacja, testy przechodzą.

### Task 3: Pipeline, zapis wyników, CLI
**Pliki:** `odw2json/pipeline.py`, `odw2json/cli.py`, `odw2json/__main__.py`, `start.bat`, `start.sh`, `tests/test_pipeline.py`
**Produkuje:** `pipeline.process_file(pdf, registry) -> tuple[Classification, ExtractionResult | None]`, `pipeline.run(input_dir: Path, output_dir: Path) -> RunReport` (obsługuje case'y w podfolderach i PDF-y luzem, błąd jednego pliku nie przerywa batcha), CLI `python -m odw2json run [input] [output]`.
- [ ] Testy (tmp_path): nazwa ze spacją daje wyjście pod tą samą nazwą; uszkodzony PDF trafia do `report.errors`, a reszta się przetwarza; plik `.txt` jest ignorowany; negatyw przy `unknown_output=none` nie tworzy pliku.
- [ ] Implementacja, testy przechodzą.

### Task 4: Ewaluacja F1
**Pliki:** `eval/score.py`, `eval/README.md`, `tests/test_score.py`
**Produkuje:** `score_pair(pred: dict | None, gt: dict | None, cfg) -> Counts(tp, tn, fp, fn)`, `score_dirs(pred_root, gt_root) -> Report`, CLI `python -m eval.score --pred output --gt data/train`.
- [ ] Testy: identyczne → fp=fn=0; null/null daje TN; wartość u nas przy null w GT daje FP; null u nas przy wartości w GT daje FN; zła wartość daje FP; „STRABAG Sp. z o.o.” vs „STRABAG sp. z o.o.” przy `fuzzy_fields` daje TP; lista z dodatkowym elementem daje FP za jego pola.
- [ ] Implementacja: dopasowanie elementów list zachłannie po podobieństwie, mapowanie nazw GT↔wynik (`potwierdzenie_przelewu.json` ↔ `przelew.json`) z konfiguracji.

### Task 5: Dane, wynik bazowy, API, Docker, dokumentacja, git
**Pliki:** `data/train/**` (kopia `dane/` z repo UZP), `odw2json/api/__init__.py` (FastAPI: `GET /api/health`, `GET /api/doctypes`, `POST /api/process`), `web/README.md`, `Dockerfile`, `docker-compose.yml`, `README.md`, `docs/sektory.md`, `docs/nowy-typ-dokumentu.md`, `scripts/make_input_from_train.py`
- [ ] `python scripts/make_input_from_train.py` i `python -m odw2json run` przechodzą bez błędu. `python -m eval.score` daje wynik bazowy (zapisany w README).
- [ ] `git init`, commit, gałęzie `feat/a-ingest-classify`, `feat/b-extraction`, `feat/c-app`, push do `origin`.
