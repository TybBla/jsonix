# Zgłoszenie — checklista zgodności z regulaminem i README UZP

Źródło wymagań: [kryteria-uzp.md](kryteria-uzp.md) (regulamin, treść zadania, FAQ, README organizatora, ustalenia z Discorda). Stan na 22.11.2026: wydanie **v1.0.1** (tag `v1.0.1`), zgłoszenie wysłane, rozwiązanie wdrożone na VM jury. Legenda: ✅ spełnione (z dowodem), 🟡 w toku, ⬜ do zrobienia.

## Wymagania techniczne

| Wymaganie | Stan | Dowód |
|---|---|---|
| Python 3.13+, `requirements.txt` | ✅ | `pyproject.toml: requires-python >=3.13`, `requirements.txt` + `requirements-lock.txt`; CI na 3.13 i 3.14; `start.bat` sam tworzy `.venv` (3.13/3.14), na 3.15 działa bez OCR |
| Uruchomienie z CLI / wrappera | ✅ | `start.bat`, `start.sh` = `python -m odw2json run input output` |
| Foldery `input/` i `output/` w katalogu głównym, wynik `output/<sprawa>/<nazwa_jak_pdf>.json` | ✅ | `odw2json/pipeline.py: write_outputs`; smoke CLI w CI |
| Typ rozpoznawany z treści, nie z nazwy pliku | ✅ | `odw2json/classify/` (nazwa pliku nieużywana), [decyzje/E3-klasyfikacja.md](decyzje/E3-klasyfikacja.md) |
| Dokument nieznany → `<nazwa>.json` z `{}` | ✅ | `config/app.yaml: unknown_output: empty_object` |
| JSON ściśle wg schematu (kolejność kluczy, `null` gdy brak) | ✅ | szablony `config/schemas/*.json`, test kształtu w bramce (`schema_errors = 0`) |
| Skany bez warstwy tekstowej (OCR) | ✅ | RapidOCR w `requirements.txt` i w obrazie Dockera; F1 skanów: dev 0,992, holdout 0,967 (`docs/raport-jakosci.md`) |
| **Ograniczony czas na rozwiązanie** (UZP, pkt 5a) | ✅ | limit jury: 60 min na 150 plików. Na VM UZP (2 vCPU): 226 PDF w 365 s, skan śr. ok. 12 s, dokument z tekstem < 0,1 s ([kryteria-uzp.md](kryteria-uzp.md), pkt 5b); laptop 16 rdzeni, zimny cache OCR: tekst 0,04–0,1 s, skan 3–8 s ([raport-jakosci.md](raport-jakosci.md), [decyzje/E11-wydajnosc.md](decyzje/E11-wydajnosc.md)); `{}` przed przetwarzaniem, zapis atomowy, najpierw dokumenty z tekstem (PR #13) |
| Wyłącznie open source; laptop i7 / 16 GB / bez GPU | ✅ | licencje niżej; OCR na CPU (onnxruntime) |
| LLM opcjonalny: open source, firma z serwerami w UE/EOG i polityką prywatności (zakres i miejsce przetwarzania) | ✅ | **decyzja: bez LLM** (`llm_enabled: false`) — 20/20 pkt za moc modelu, F1 z reguł 0,999 / 0,997 ([decyzje/E6-bez-llm.md](decyzje/E6-bez-llm.md)); wymogi dostawcy nie dotyczą |

## Zgłoszenie (formularz)

| Element | Stan | Uwagi |
|---|---|---|
| Zgłoszenie wysłane | ✅ | formularz HackNation, tekst opisu na końcu tego pliku |
| Tytuł projektu | ✅ | **jsonix** |
| Link do repozytorium GitHub z działającym prototypem | ✅ | repozytorium publiczne: https://github.com/TybBla/jsonix |
| Prototyp: wgranie dokumentów i odczyt wyników | ✅ | GUI (`start-gui.bat`, `docker compose up --build`) i CLI (`start.bat`); [gui.md](gui.md); test na czystym Windows: [test-jury.md](test-jury.md) |
| Dokumentacja techniczna, w tym opis użytego LLM | ✅ | [architektura.md](architektura.md) (sekcja „LLM — decyzja: bez LLM”), uzasadnienie [decyzje/E6-bez-llm.md](decyzje/E6-bez-llm.md) |
| Wyniki testów jakości | ✅ | [raport-jakosci.md](raport-jakosci.md) (zimny cache OCR): razem 0,998 / 0,994, tekst 0,999 / 0,997, skany 0,992 / 0,967 (dev / holdout), negatywy 15/15 i 13/13; czas: tekst 0,04–0,1 s/dok., skan 3–8 s/dok.; `eval/baseline.json` |

## Ocena na VM UZP (VM.md)

| Element | Stan | Dowód |
|---|---|---|
| `RUN.md` w katalogu głównym repo (komenda oceny, obraz `jsonix:latest`) | ✅ | [RUN.md](../RUN.md); test `tests/test_cli_jury.py` (jedna komenda `docker run` bez interakcji) |
| Profil jury (w `output/` tylko pliki JSON, bez trace) | ✅ | `config/app.jury.yaml`, PR #23 |
| Wdrożenie na VM | ✅ | obraz `jsonix:latest` zbudowany na VM, `/opt/solution/RUN.md` skopiowany (`scripts/deploy-vm.sh`, [vm-jury.md](vm-jury.md)) |
| Test jak u jury (z `sudo`, także po restarcie VM) | ✅ | exit 0, w `output/` wyłącznie pliki JSON; po teście `input/` i `output/` zostawione puste |
| Limit czasu jury (60 min / 150 plików) | ✅ | pomiar na VM: 226 PDF (w tym 30 skanów) w 365 s, skan śr. ok. 12 s ([kryteria-uzp.md](kryteria-uzp.md), pkt 5b) |

## Warunek wypłaty nagrody (regulamin §3.5)

| Element | Stan | Dowód |
|---|---|---|
| Kod źródłowy | ✅ | repozytorium |
| Instrukcja uruchomienia | ✅ | [README](../README.md): szybki start (Windows, Docker, Linux), GUI; dla jury [RUN.md](../RUN.md) |
| Docker Compose | ✅ | `docker-compose.yml` bez wymaganego `.env`, z healthcheckiem; test `scripts/smoke_docker.py` (wynik w kontenerze = CLI, także skan z OCR) |
| Opis architektury | ✅ | [architektura.md](architektura.md) |
| Konfiguracja ekstrakcji danej klasy dokumentów | ✅ | [nowy-typ-dokumentu.md](nowy-typ-dokumentu.md) (sekcje `classify`, `fields`, `lists`), decyzje: [decyzje/E4-ekstrakcja.md](decyzje/E4-ekstrakcja.md) |
| Dodawanie nowej klasy dokumentów | ✅ | [nowy-typ-dokumentu.md](nowy-typ-dokumentu.md); przykład 4. typu wyłącznie konfiguracją: [examples/nowy-typ/orzeczenie_kio](../examples/nowy-typ/orzeczenie_kio/README.md), test „0 linii kodu” `tests/test_nowy_typ_konfiguracja.py` |

## Autorstwo i rozwiązania zewnętrzne (regulamin §4)
- W commitach i PR nie umieszczamy atrybucji narzędzi AI (decyzja zespołu, `AGENTS.md`).
- Rozwiązania zewnętrzne **wskazujemy w prezentacji** (ostatni slajd [prezentacja.html](prezentacja.html)). Lista komponentów open source (zależności z `requirements.txt`, wersje przypięte w `requirements-lock.txt`):

| Komponent | Do czego | Licencja |
|---|---|---|
| pypdfium2 (PDFium) | tekst z PDF (backend domyślny) | BSD-3-Clause / Apache-2.0 |
| pypdf, pdfplumber (pdfminer.six) | zapasowe backendy PDF | BSD-3-Clause, MIT |
| RapidOCR + onnxruntime + OpenCV (headless) | OCR skanów na CPU | Apache-2.0, MIT, Apache-2.0 |
| numpy, Pillow, shapely, pyclipper | zależności OCR | BSD-3-Clause i in., MIT-CMU, BSD-3-Clause, MIT |
| PyYAML, pydantic, rapidfuzz | konfiguracja, modele danych, podobieństwo tekstu | MIT |
| FastAPI, uvicorn, python-multipart | API i serwer | MIT, BSD-3-Clause, Apache-2.0 |
| pytest, httpx | testy (w tym klient testowy API) | MIT, BSD-3-Clause |
| openai (klient), python-dotenv | opcjonalny klient LLM (API zgodne z OpenAI), `.env` | Apache-2.0, BSD-3-Clause |
| PDF.js (Mozilla) | podgląd PDF w GUI | Apache-2.0 (`web/static/vendor/pdfjs/LICENSE`) |
| Open Sans | font GUI (Design System Gov.pl) | SIL OFL 1.1 (`web/static/vendor/fonts/LICENSE`) |
| Design System Gov.pl | wzorce interfejsu (kolory, komunikaty) | wzorzec stylu, bez kodu w repo |

## Przed wysłaniem
- [x] `main` zielony w CI (testy, bramka dev i holdout, smoke, `docker build`): przebiegi „Merge #29: wydanie v1.0.1” i „Merge #33” — success.
- [x] `python scripts/smoke_docker.py` zwraca 0 na świeżym klonie ([test-jury.md](test-jury.md), sekcja „Docker”); GUI z `start-gui.bat` i z Dockera sprawdzone w tym samym teście.
- [x] Tag wydania i CHANGELOG: `v1.0.0` i `v1.0.1` ([CHANGELOG.md](../CHANGELOG.md), [wydanie-v1.0.md](wydanie-v1.0.md)).
- [x] `python -m odw2json doctypes` pokazuje **dokładnie 3 typy** (przykład 4. typu jest tylko w `examples/`, pilnuje tego `tests/test_nowy_typ_konfiguracja.py`), bramka dev ma negatywy 15/15.
- [x] Pełny przebieg na wszystkich sprawach treningowych w rozsądnym czasie: 226 PDF w 213 s na laptopie ([decyzje/E11-wydajnosc.md](decyzje/E11-wydajnosc.md)) i w 365 s na VM jury.
- [x] Raport jakości F1 w repo i w zgłoszeniu — [raport-jakosci.md](raport-jakosci.md) (#27).
- [x] Repo dostępne dla jury — `gh repo view`: PUBLIC, https://github.com/TybBla/jsonix.
- [x] Test instalacji na czystym Windows ze świeżego klonu (Python 3.13, 3.14 i 3.15) — [test-jury.md](test-jury.md).
- [x] Wdrożenie na VM jury i test jak u jury (z `sudo`, po restarcie) — sekcja „Ocena na VM UZP” wyżej.
- [x] Prezentacja: demo GUI, transparentność ekstrakcji (podświetlenie źródła), nowy typ bez kodu, uzasadnienie „bez LLM”, lista rozwiązań zewnętrznych — [prezentacja.html](prezentacja.html), scenariusz [demo.md](demo.md).
- [x] Zgłoszenie wysłane (tytuł, link do repo, opis poniżej).

## Tekst opisu do formularza zgłoszenia

jsonix zamienia dokumenty PDF ze spraw odwoławczych KIO na dane JSON zgodne ze schematami UZP. Rozpoznaje z treści (nie z nazwy pliku) odwołanie, pełnomocnictwo i potwierdzenie przelewu, wyodrębnia pola, a dokument spoza tych typów zwraca jako `{}`. Rozwiązanie działa bez LLM: reguły z konfiguracji dają F1 0,999 (dev) i 0,997 (holdout) na dokumentach z tekstem, bez kosztów, bez wysyłania danych i z maksymalną liczbą punktów za moc modelu (20/20). Typy dokumentów i pola opisuje konfiguracja YAML zamiast kodu, więc nowy typ dodaje się bez zmian w programie (przykład 4. typu: orzeczenie KIO). Dla każdej wartości zapisujemy ślad (metoda, strona, fragment źródła), a GUI pokazuje PDF obok pól z podświetleniem miejsca, z którego pochodzi wynik, oraz uzasadnienie wyboru typu. Skany czytamy lokalnym OCR (RapidOCR) na CPU, bez GPU i bez dostępu do sieci; F1 na skanach: 0,992 (dev) i 0,967 (holdout). Wynik przerwanego przebiegu jest zachowany, bo `{}` zapisujemy dla każdego PDF przed przetwarzaniem. Uruchomienie: instrukcja dla jury w `RUN.md`, `start.bat` (Windows, Python 3.13/3.14) lub Docker Compose (`docker compose up --build`). Kod, dokumentacja i wyniki testów: https://github.com/TybBla/jsonix.
