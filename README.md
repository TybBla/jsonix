# jsonix

jsonix czyta dokumenty PDF ze sprawy odwoławczej KIO i zamienia je na dane JSON w formacie UZP. Sam rozpoznaje, czy dokument to odwołanie, pełnomocnictwo czy potwierdzenie przelewu, i wyciąga z niego pola. Przy każdej wartości zapisuje, z której strony i z którego fragmentu ją wziął. Dokument innego rodzaju dostaje plik z `{}`. Skany bez tekstu czyta lokalny OCR, bez GPU i bez wysyłania danych na zewnątrz. Nie używamy LLM.

![jsonix — demo GUI](docs/img/demo-gui.gif)

Wersja **v1.0.1** · F1 wg reguł UZP: **0,998** (dev) / **0,994** (holdout) · [raport jakości](docs/raport-jakosci.md) · projekt HackNation 2026 (zadanie UZP)

## Uruchomienie na VM jury (tak, jak sprawdza jury)

Ocena odbywa się na VM UZP: Ubuntu 24.04, 2 vCPU, 16 GB RAM, Docker. Jury wrzuca dokumenty do `/opt/solution/input`, w katalogu `/opt/solution` uruchamia z `sudo` komendę z pliku `/opt/solution/RUN.md` i zabiera wyniki z `/opt/solution/output`. Limit czasu to 60 minut na 150 plików.

**1. Przygotowanie VM** (jednorazowo, robi to zespół):

```bash
cd /opt/solution
git clone https://github.com/TybBla/jsonix.git repo
docker build -t jsonix:latest repo      # kilka minut; potem nic nie jest pobierane
cp repo/RUN.md /opt/solution/RUN.md
```

**2. Ocena** (to robi jury):

```bash
# dokumenty: /opt/solution/input/<sprawa>/<plik>.pdf (albo PDF-y luzem w input/)
cd /opt/solution
sudo docker run --rm -e JSONIX_APP_CONFIG=config/app.jury.yaml \
  -v /opt/solution/input:/app/input -v /opt/solution/output:/app/output \
  jsonix:latest python -m odw2json run input output
```

To ta sama komenda co w [RUN.md](RUN.md). Kończy się sama, nie zadaje pytań, nie potrzebuje usług w tle ani kluczy API.

**3. Wynik:** `/opt/solution/output/<sprawa>/<nazwa_pdf>.json`, jeden plik na każdy PDF, w tym `{}` dla dokumentów spoza trzech typów. W `output/` nie ma nic poza tymi plikami.

**Czas na tej VM:** 226 PDF-ów ze zbioru treningowego, w tym 30 skanów, przetwarza się w 6 minut. Dokument z tekstem zajmuje ułamek sekundy, skan średnio około 12 s. Nawet 150 samych skanów to około 30 minut. Plik `{}` powstaje dla każdego PDF-a od razu na starcie, a wyniki zapisują się na bieżąco. Dzięki temu po ewentualnym przerwaniu w `output/` są wszystkie gotowe wyniki.

Wdrożenie jest gotowe i przetestowane: komenda działa z `sudo` i po restarcie VM. Szczegóły i skrypt z autotestem: [docs/vm-jury.md](docs/vm-jury.md), `scripts/deploy-vm.sh`.

## Uruchomienie u siebie

**Windows** (Python 3.13 lub 3.14 z [python.org](https://www.python.org/downloads/), z zaznaczonym „Add python.exe to PATH”):

```powershell
.\start-gui.bat     # aplikacja w przeglądarce: http://127.0.0.1:8000
.\start.bat         # wsad: PDF-y z input\<sprawa>\ → wyniki w output\<sprawa>\
```

Za pierwszym razem skrypt sam tworzy środowisko i instaluje zależności. Trwa to kilka minut i wymaga internetu. Potem aplikacja działa offline.

**Docker** (dowolny system):

```bash
docker compose up --build                            # aplikacja: http://127.0.0.1:8000
docker compose run --rm app python -m odw2json run   # wsad: input/ → output/
```

**Linux/macOS:** `pip install -r requirements.txt`, potem `sh start.sh` (wsad) albo `python -m odw2json serve` (aplikacja).

W aplikacji wgrywasz PDF-y sprawy i klikasz „Analizuj”. Potem sprawdzasz rozpoznany typ (wraz z uzasadnieniem „Dlaczego ten typ?”) i przeglądasz dane obok podglądu dokumentu. Ikonka „i” przy wartości pokazuje stronę i fragment źródła, a najechanie na pole podświetla je w PDF. Wartości można poprawić i pobrać jako JSON albo ZIP. Więcej: [docs/gui.md](docs/gui.md).

## Wyniki

F1 liczone wg reguł UZP na danych treningowych (podział dev/holdout):

| Zbiór | Razem | Dokumenty z tekstem | Skany (OCR) |
|---|---|---|---|
| dev | 0,998 | 0,999 | 0,992 |
| holdout | 0,994 | 0,997 | 0,967 |

Klasyfikacja nie popełnia błędów, a wszystkie dokumenty spoza typów dostają `{}` (15/15 i 13/13). Wyniki per typ i pole oraz czasy są w [raporcie jakości](docs/raport-jakosci.md). Skrypt `python scripts/quality_report.py` generuje go od nowa.

## Jak to działa

```
PDF → tekst z PDF albo OCR → rozpoznanie typu → wyodrębnienie pól → JSON wg schematu UZP (+ źródło każdej wartości)
```

- **Konfiguracja zamiast kodu.** Każdy typ dokumentu to plik `config/doctypes/<typ>.yaml`: jak go rozpoznać i skąd brać pola. Nowy typ dodaje się samą konfiguracją ([instrukcja](docs/nowy-typ-dokumentu.md), [przykład: orzeczenie KIO](examples/nowy-typ/orzeczenie_kio/README.md)).
- **Przejrzystość.** Każda wartość ma zapisaną stronę i fragment tekstu, z którego pochodzi. GUI pokazuje je w dokumencie.
- **Bez LLM.** Reguły dają F1 0,999 na dokumentach z tekstem, nic nie kosztują, działają lokalnie i dają powtarzalny wynik, a za moc modelu jest wtedy maksimum punktów. Uzasadnienie: [decyzja E6](docs/decyzje/E6-bez-llm.md). Opcjonalną warstwę LLM można włączyć w `config/app.yaml`, wyłącznie z modelem do 8B od dostawcy z UE.

Pełny opis: [docs/architektura.md](docs/architektura.md).

## Dokumentacja

| Dokument | Co zawiera |
|---|---|
| [RUN.md](RUN.md) | komenda dla jury na VM |
| [docs/vm-jury.md](docs/vm-jury.md) | wdrożenie i test na VM krok po kroku |
| [docs/architektura.md](docs/architektura.md) | architektura: etapy, kontrakty danych, konfiguracja, API i GUI |
| [docs/nowy-typ-dokumentu.md](docs/nowy-typ-dokumentu.md) | konfiguracja ekstrakcji i dodawanie nowej klasy dokumentów |
| [docs/gui.md](docs/gui.md) | aplikacja w przeglądarce |
| [docs/raport-jakosci.md](docs/raport-jakosci.md) | wyniki testów jakości |
| [docs/test-jury.md](docs/test-jury.md) | test instalacji ze świeżego klonu (Windows, Docker) |
| [docs/decyzje/E6-bez-llm.md](docs/decyzje/E6-bez-llm.md) | dlaczego bez LLM |
| [docs/zgloszenie.md](docs/zgloszenie.md) | zgodność z regulaminem, użyte komponenty open source i licencje |
| [docs/kryteria-uzp.md](docs/kryteria-uzp.md) | kryteria oceny i ustalenia organizatora |
| [CHANGELOG.md](CHANGELOG.md) | historia wersji |

## Dla programistów

```bash
pip install -r requirements-dev.txt
python -m pytest -q -m "not slow"                  # szybkie testy
python -m eval.gate --split dev --source tekst     # bramka jakości F1 (jak w CI)
```

CI na GitHub Actions uruchamia lint, testy, bramkę F1, testy dymne na Windows i Ubuntu oraz `docker build`. Jak liczymy F1: [eval/README.md](eval/README.md). Zasady pracy w repo: [AGENTS.md](AGENTS.md).

Dane treningowe pochodzą z [repozytorium UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026).
