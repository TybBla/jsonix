# Zgłoszenie — checklista zgodności z regulaminem i README UZP

Źródło wymagań: [kryteria-uzp.md](kryteria-uzp.md) (regulamin, treść zadania, FAQ, README organizatora, ustalenia z Discorda). Stan na 22.11.2026 (po v0.4.0). Legenda: ✅ spełnione (z dowodem), 🟡 w toku, ⬜ do zrobienia przed zgłoszeniem.

## Wymagania techniczne

| Wymaganie | Stan | Dowód |
|---|---|---|
| Python 3.13+, `requirements.txt` | ✅ | `pyproject.toml: requires-python >=3.13`, `requirements.txt` + `requirements-lock.txt`; CI na 3.13 i 3.14; `start.bat` sam tworzy `.venv` (3.13/3.14), na 3.15 działa bez OCR |
| Uruchomienie z CLI / wrappera | ✅ | `start.bat`, `start.sh` = `python -m odw2json run input output` |
| Foldery `input/` i `output/` w katalogu głównym, wynik `output/<sprawa>/<nazwa_jak_pdf>.json` | ✅ | `odw2json/pipeline.py: write_outputs`; smoke CLI w CI |
| Typ rozpoznawany z treści, nie z nazwy pliku | ✅ | `odw2json/classify/` (nazwa pliku nieużywana), [decyzje/E3-klasyfikacja.md](decyzje/E3-klasyfikacja.md) |
| Dokument nieznany → `<nazwa>.json` z `{}` | ✅ | `config/app.yaml: unknown_output: empty_object` |
| JSON ściśle wg schematu (kolejność kluczy, `null` gdy brak) | ✅ | szablony `config/schemas/*.json`, test kształtu w bramce (`schema_errors = 0`) |
| Skany bez warstwy tekstowej (OCR) | ✅ | RapidOCR w `requirements.txt` i w obrazie Dockera; F1 skanów dev 0,977, holdout 0,912 |
| **Ograniczony czas na rozwiązanie** (UZP, pkt 5a) | ✅ / 🟡 | dokument z tekstem 0,01 s, skan ~4 s ([decyzje/E11-wydajnosc.md](decyzje/E11-wydajnosc.md)); `{}` przed przetwarzaniem, zapis atomowy, najpierw dokumenty z tekstem — PR #13 |
| Wyłącznie open source; laptop i7 / 16 GB / bez GPU | ✅ | licencje niżej; OCR na CPU (onnxruntime) |
| LLM opcjonalny: open source, firma z serwerami w UE/EOG i polityką prywatności (zakres i miejsce przetwarzania) | ✅ | **decyzja: bez LLM** (`llm_enabled: false`) — 20/20 pkt za moc modelu, F1 z reguł 0,999 / 0,997 ([decyzje/E6-bez-llm.md](decyzje/E6-bez-llm.md)); wymogi dostawcy nie dotyczą |

## Zgłoszenie (formularz)

| Element | Stan | Uwagi |
|---|---|---|
| Tytuł projektu | 🟡 | roboczo **jsonix**; zespół potwierdza przed wysyłką |
| Link do repozytorium GitHub z działającym prototypem | ⬜ | repo musi być dostępne dla jury (publiczne albo z dostępem); sprawdzić w ustawieniach repo |
| Prototyp: wgranie dokumentów i odczyt wyników | ✅ | GUI (`start-gui.bat`, Docker) i CLI; [gui.md](gui.md) |
| Dokumentacja techniczna, w tym opis użytego LLM | ✅ | [architektura.md](architektura.md) (sekcja „LLM — decyzja: bez LLM”) |
| Wyniki testów jakości | 🟡 | v0.4.0: tekst 0,999 / 0,997, skany 0,977 / 0,912 (README, `eval/baseline.json`); pełny raport `docs/raport-jakosci.md` ze `scripts/quality_report.py` (PR #15) na finalnym kodzie — plan v1.0, pkt 15 |

## Warunek wypłaty nagrody (regulamin §3.5)

| Element | Stan | Dowód |
|---|---|---|
| Kod źródłowy | ✅ | repozytorium |
| Instrukcja uruchomienia | ✅ | [README](../README.md): szybki start, GUI, Docker |
| Docker Compose | ✅ | `docker-compose.yml` bez wymaganego `.env`, z healthcheckiem; test `scripts/smoke_docker.py` (wynik w kontenerze = CLI, także skan z OCR) |
| Opis architektury | ✅ | [architektura.md](architektura.md) |
| Konfiguracja ekstrakcji danej klasy dokumentów | ✅ | [nowy-typ-dokumentu.md](nowy-typ-dokumentu.md) (sekcje `classify`, `fields`, `lists`), decyzje: [decyzje/E4-ekstrakcja.md](decyzje/E4-ekstrakcja.md) |
| Dodawanie nowej klasy dokumentów | ✅ / 🟡 | [nowy-typ-dokumentu.md](nowy-typ-dokumentu.md); przykład 4. typu wyłącznie konfiguracją (orzeczenie KIO) z testem „0 linii kodu” — PR E10 |

## Autorstwo i rozwiązania zewnętrzne (regulamin §4)
- W commitach i PR nie umieszczamy atrybucji narzędzi AI (decyzja zespołu, `AGENTS.md`).
- Rozwiązania zewnętrzne **wskazujemy w prezentacji**. Lista komponentów open source, z wersjami z obrazu Dockera z 21.11.2026:

| Komponent | Do czego | Licencja |
|---|---|---|
| pypdfium2 (PDFium) | tekst z PDF (backend domyślny) | BSD-3-Clause / Apache-2.0 |
| pypdf, pdfplumber (pdfminer.six) | zapasowe backendy PDF | BSD-3-Clause, MIT |
| RapidOCR + onnxruntime + OpenCV (headless) | OCR skanów na CPU | Apache-2.0, MIT, Apache-2.0 |
| numpy, Pillow, shapely, pyclipper | zależności OCR | BSD-3-Clause i in., MIT-CMU, BSD-3-Clause, MIT |
| PyYAML, pydantic, rapidfuzz | konfiguracja, modele danych, podobieństwo tekstu | MIT |
| FastAPI, uvicorn, python-multipart | API i serwer | MIT, BSD-3-Clause, Apache-2.0 |
| openai (klient), python-dotenv | opcjonalny klient LLM (API zgodne z OpenAI), `.env` | Apache-2.0, BSD-3-Clause |
| PDF.js (Mozilla) | podgląd PDF w GUI | Apache-2.0 (`web/static/vendor/pdfjs/LICENSE`) |
| Open Sans | font GUI (Design System Gov.pl) | SIL OFL 1.1 (`web/static/vendor/fonts/LICENSE`) |
| Design System Gov.pl | wzorce interfejsu (kolory, komunikaty) | wzorzec stylu, bez kodu w repo |

## Przed wysłaniem
- [ ] `main` zielony w CI (testy, bramka dev i holdout, smoke, `docker build`).
- [ ] `python scripts/smoke_docker.py` i `python scripts/smoke_gui.py` zwracają 0 na czystym klonie.
- [ ] Tag wydania (`v1.0.0`) i CHANGELOG.
- [ ] `python -m odw2json doctypes` pokazuje **dokładnie 3 typy** (przykład 4. typu z `examples/` nie może zostać w `config/`) i bramka `python -m eval.gate --split dev` ma negatywy 15/15.
- [ ] Pełny przebieg `start.bat` na wszystkich sprawach treningowych mieści się w rozsądnym czasie (plan v1.0, pkt 11).
- [ ] Raport jakości F1 w repo i w zgłoszeniu.
- [ ] Repo dostępne dla jury; link sprawdzony w oknie prywatnym.
- [ ] Prezentacja: demo GUI, transparentność ekstrakcji (podświetlenie źródła), nowy typ bez kodu, uzasadnienie „bez LLM”, lista rozwiązań zewnętrznych.
