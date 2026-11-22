# Kryteria i ustalenia UZP — jedno źródło prawdy

Zebrane z: regulaminu zadania „Odwołania2json” (HackNation 2026), pełnej treści zadania, prezentacji wyzwania, FAQ v1.0, README repozytorium organizatora (https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026) oraz odpowiedzi UZP na Discordzie (21.11.2026). W razie sprzeczności obowiązuje **najnowsze ustalenie** (Discord / README), a te nadpisują wcześniejsze punkty.

## 1. Zadanie
- Wejście: dokumenty PDF sprawy odwoławczej KIO. Rozwiązanie **rozpoznaje typ** (klasyfikacja po **treści**, nie po nazwie pliku) i **wyodrębnia dane** do JSON zgodnego ze schematem UZP (`data/oczekiwane-json/*.json`).
- Typy: **odwołanie**, **pełnomocnictwo**, **potwierdzenie przelewu**.
- Dokument spoza tych typów: **plik `<nazwa_pdf>.json` z zawartością dokładnie `{}`** (UZP, Discord 13:50).
- Brak informacji w dokumencie → `null`; nie zmyślać danych.
- JSON **ściśle zgodny z formatem** (bez dodatkowych pól).
- Dane testowe: syntetyczne, oparte na realnych sprawach; **zawierają też skany bez warstwy tekstowej** (UZP dodało `dane/skany/` — OCR obowiązkowy).

## 2. Wymagania techniczne i formalne
- **Python 3.13+**, `requirements.txt`, uruchomienie z **CLI** / wrappera (`start.bat`).
- Foldery **`input/`** i **`output/`** w katalogu głównym; wynik `output/<sprawa>/<nazwa_jak_pdf>.json`.
- Wyłącznie komponenty **open source**; laptop testowy: i7, 16 GB RAM, **bez GPU**, z internetem; **czas na rozwiązanie ograniczony** (pkt 5a).
- LLM (opcjonalny): **open source**, przez API **firmy z serwerami w UE/EOG**, która ma **Politykę Prywatności określającą zakres i miejsce przetwarzania danych**; dostarczamy klucz API. **Hosting przez osobę prywatną (własny komputer/serwer) wykluczony.**
- Zgłoszenie: tytuł projektu + link do GitHub z działającym prototypem (wgranie dokumentów i odczyt wyników). Dodatkowo: dokumentacja techniczna (w tym opis użytego LLM), wyniki testów jakości.
- Warunek wypłaty nagrody (regulamin §3.5): kod źródłowy, instrukcja uruchomienia, **Docker Compose**, dokumentacja: **opis architektury, konfiguracja ekstrakcji danej klasy dokumentów, dodawanie nowej klasy dokumentów**.
- Regulamin §4: uczestnik oświadcza, że jest twórcą rozwiązania; rozwiązania zewnętrzne trzeba wskazać w prezentacji. **W repo nie umieszczamy atrybucji narzędzi AI w commitach/PR** (decyzja zespołu).

## 3. Ocena
- **Etap 1 (preselekcja): 100% F1** na ukrytym zbiorze (≥ 10 spraw).
- **Etap 2 (finał, max 3 zespoły): 50% F1 + 50% elastyczność**, w tym:
  - 1–20 pkt za **moc modelu LLM** wg **średniej liczby parametrów wszystkich użytych modeli** (przy MoE liczą się parametry ogółem, nie aktywne): **≤ 8B = 20**, >8–14B = 18, >14–32B = 12, >32–70B = 8, >70–150B = 4, >150B = 0. Bez LLM = maksimum (UZP Discord 13:52). Przykład UZP: modele 3B i 32B → średnia 17,5B → 12 pkt. **Wniosek: każdy model ≤ 8B nie kosztuje punktów; nie mieszamy z większymi.**
  - 1–20 pkt za **łatwość dodawania nowych typów dokumentów i pól bez przebudowy** (konfiguracja zamiast kodu),
  - 1–10 pkt za **inne funkcje** (np. GUI).
- GUI nie jest wymagane, ale punktowane; idealnie: wgranie PDF, uruchomienie analizy, **podgląd dokumentu obok wyodrębnionych danych**.
- Premiowane: konfiguracja nowych klas bez zmian kodu, **transparentność ekstrakcji**.

## 4. Jak liczone jest F1 (UZP)
- TP: wartość w JSON zgodna z GT; TN: brak w JSON i w GT; FP: wartość tylko w JSON albo niezgodna; FN: brak w JSON, jest w GT.
- **Długie stringi z progiem podobieństwa 80%** (UZP, Discord 13:26): nazwa firmy pełnomocnika, tytuł przelewu, nazwa Odwołującego/Zamawiającego, tytuł zamówienia. **Wszystko inne dokładnie** (KRS, NIP, daty, kwoty, imiona, opis czynności…).
- Listy dopasowywane **po treści** (nie po kolejności).

## 5. Ustalenia szczegółowe (Discord UZP, 21.11.2026)
- 60 przykładów treningowych (prezentacja mówiła o 39 — nieaktualne); `ground_truth.yaml` usunięty (to były scalone JSON-y).
- `czynnosc_powod_id` 1–12, słownik `data/oczekiwane-json/czynnosc_powod_id_dict.md`; 12 = „Projektowane postanowienia umowy”; 6 = „Odpowiedzi/wyjaśnienia do SWZ” (**ze skośnikiem**). `czynnosc_opis` ustalany wyłącznie z **pierwszego zarzutu**.
- Sumy kontrolne NIP/REGON/PESEL w danych demo są celowo błędne — **nie walidujemy sum**, tylko format.
- **Imiona i nazwiska w mianowniku** (np. „Mateusz Szymański”, nie „Mateusza Szymańskiego”).
- Maszyna oceniająca ma internet. ~~Brak limitu czasu~~ — nieaktualne, patrz 5a: każde rozwiązanie ma ograniczony czas.

### 5a. Ustalenia z Discorda, wieczór 21.11.2026 (UZP, MateuszSz)
- **Limit czasu na rozwiązanie (21:13):** rate limit i liczba zapytań do API **nie wpływają na ocenę**, ale **każde rozwiązanie dostaje ograniczony czas** (wartość nieznana) i program, który nie skończy, może nie zostać w pełni oceniony. Wcześniejsze „bez limitu czasu” jest nieaktualne. Wnioski: liczy się czas na sprawę na CPU (szczególnie OCR skanów); ponawianie zapytań przy limicie API wolno stosować, ale zjada ten sam budżet czasu.
- **Numer rachunku w potwierdzeniu przelewu (21:17):** wpisujemy numer **tak, jak jest w dokumencie** — z prefiksem „PL”, jeśli dokument go ma. Brak „PL” w części wzorcowych JSON-ów to **błąd danych treningowych**, którego **nie będzie w zbiorze oceniającym**. Spacje: odpowiedź UZP ich nie rozstrzyga wprost (pytanie dotyczyło „PL i spacji”); dane wzorcowe nigdy nie mają spacji, więc zostajemy przy zapisie bez spacji (do potwierdzenia na Discordzie).
- **Nazwa firmy w pełnomocnictwie (21:17):** wpisujemy **tak, jak w analizowanym dokumencie**, nawet jeśli różni się od CEIDG (np. przy jednoosobowej działalności: pełna firma z imieniem i nazwiskiem, jeśli tak jest w dokumencie).

**Wpływ na projekt (stan 21.11, wieczór):**
- `data/train`: w 138 ze 140 numerów rachunków w GT brak „PL”, a w 95 ze 119 przypadków, w których numer da się znaleźć w warstwie tekstu PDF, dokument ma „PL” przed numerem (w 71 numer jest zapisany ze spacjami). Bramka F1 liczona na obecnym GT będzie więc **karać poprawny wynik z „PL”** — GT trzeba poprawić albo porównywać IBAN po normalizacji (decyzja etapu E4/eval).
- Ekstrakcja (gałąź E4, `odw2json/extract/normalize.py: iban`) **usuwa prefiks „PL”** — zgodnie z obecnym GT, ale niezgodnie z ustaleniem UZP: do zmiany na „PL” zachowane, gdy jest w dokumencie.
- Nazwa firmy (`company`) bierze tekst z dokumentu (np. „pod firmą …”) bez rozwijania skrótów — zgodnie z ustaleniem.
- Czas: raport jakości ma podawać czas na sprawę (CPU, z OCR i bez); aplikacja nie powinna wykonywać zbędnej pracy (cache OCR, LLM domyślnie wyłączony).

### 5b. VM do oceny (VM.md, 22.11.2026)
- Każdy zespół dostaje VM Azure: **Ubuntu 24.04, 2 vCPU / 16 GB RAM, bez GPU**, Docker + Compose v2, git, **Python 3.12** (za stary dla nas, więc rozwiązanie działa w Dockerze, obraz `python:3.13-slim`). Internet jest.
- **Dostęp zespołów zostanie odcięty 22.11.2026 o 11:00**, potem ocena odbywa się bez nas: obrazy i zależności muszą być pobrane/zbudowane wcześniej.
- Ocena: jury wgrywa tajny zbiór do **`/opt/solution/input`**, w katalogu **`/opt/solution`** uruchamia z `sudo` **komendę z pliku `/opt/solution/RUN.md`** i zabiera pliki z **`/opt/solution/output`**. Komenda ma działać bez interakcji i sama się zakończyć po przetworzeniu wszystkich plików; usługa w tle jest niepotrzebna.
- Katalogi `input/` i `output/` już istnieją i mogą zostać wyczyszczone przed oceną. Cały projekt leży w `/opt/solution` (u nas klon w `/opt/solution/repo`). Klucze API (my: bez LLM) byłyby w `/opt/solution/.env`.
- **Limit czasu jury (22.11.2026): maksymalnie 60 minut na 150 plików** (średnio 24 s na plik) na tej VM (2 vCPU). **Pomiar na VM (v1.0.1, 22.11):** cały zbiór treningowy (226 PDF, w tym 30 skanów) w 365 s; skan średnio ok. 12 s, dokument z tekstem < 0,1 s; 150 plików nawet w proporcji skanów jak w danych to ok. 30 min. Wdrożenie: obraz `jsonix:latest`, `/opt/solution/RUN.md`, test jak u jury z `sudo` i po restarcie — exit 0, w `output/` same JSON-y; `input/` i `output/` zostawione puste. Po przekroczeniu liczy się to, co jest w `output/` — stąd `{}` od startu, zapis każdego wyniku od razu i dokumenty z tekstem przed skanami (#13).
- Wpływ na projekt: w `output/` mają być **wyłącznie** `<sprawa>/<nazwa_jak_pdf>.json`, dlatego profil `config/app.jury.yaml` (`JSONIX_APP_CONFIG`) wyłącza trace i wynosi logi oraz cache OCR poza output. `RUN.md` w repo = wzorzec pliku jury, wdrożenie i testy: `scripts/deploy-vm.sh`, [vm-jury.md](vm-jury.md).

## 6. Gdzie to jest w projekcie
- Architektura i decyzje: `docs/superpowers/specs/2026-11-21-odwolania2json-design.md`, `docs/decyzje/`.
- Roadmapa i zakres v1.0: `docs/superpowers/plans/2026-11-21-roadmap-produkcyjna.md` (sekcja „Aktualizacja zakresu”).
- Ewaluacja (F1 wg reguł z pkt 4): `eval/score.py`, bramka `python -m eval.gate`.
