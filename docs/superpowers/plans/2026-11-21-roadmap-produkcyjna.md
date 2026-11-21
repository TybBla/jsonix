# Odwołania2JSON — roadmapa produkcyjna (od stanu obecnego do finalizacji)

Tryb pracy: jedna osoba + agenci. Produkt budujemy jak komercyjny, etap po etapie: każdy etap kończy się
**bramką jakości (harness)** i dopiero po jej przejściu zaczynamy następny. Każdy etap dostaje przed startem
własny szczegółowy plan zadań (`docs/superpowers/plans/<data>-E<n>-*.md`), krótki projekt, jeśli wymaga decyzji,
oraz review po zakończeniu.

Spec: `docs/superpowers/specs/2026-11-21-odwolania2json-design.md`

## Co znaczy „harnessujemy”

Każda zmiana przechodzi przez te same automatyczne sprawdzenia, lokalnie i w CI:

| Warstwa harnessu | Co sprawdza | Narzędzie |
|---|---|---|
| Testy jednostkowe | logika etapów, normalizatory, loader konfiguracji | `pytest` |
| Testy kontraktowe | każdy YAML typu dokumentu waliduje się względem modelu konfiguracji; każdy wynik ma dokładnie kształt szablonu | `pytest` + JSON Schema generowany z `config/schemas/` |
| Testy regresji (golden) | F1 per typ i per pole na zbiorze treningowym nie spada poniżej zapisanej linii bazowej | `eval/gate.py` + `eval/baseline.json` |
| Hold-out | osobny, zamrożony podzbiór spraw, nieużywany do strojenia promptów ani reguł | `data/splits.yaml` |
| LLM record/replay | odpowiedzi modelu nagrane w kasetach, więc testy i CI są deterministyczne i darmowe; tryb `live` tylko świadomie | cache w `odw2json/llm.py` → kasety w `tests/cassettes/` |
| Lint/format/typy | spójny styl, brak oczywistych błędów | `ruff`, `ruff format`, (opcjonalnie `mypy` dla `contracts`/`config_loader`) |
| CI | wszystko powyżej przy każdym pushu/PR | GitHub Actions (Windows + Linux, Python 3.13) |
| Smoke na czystym środowisku | świeży venv: `pip install -r requirements.txt` → `start.bat` → output; `docker compose up` | skrypt `scripts/smoke.ps1` + job CI |
| Obserwowalność | trace pochodzenia każdego pola, logi strukturalne, licznik tokenów i kosztu LLM | `output/.trace/`, `logging` |

Zasada nadrzędna: **zmiana, która obniża F1 na bramce albo łamie kontrakt, nie wchodzi na `main`.**

---

## E0 — Fundament ✅ (zrobione)
Szkielet, kontrakty (`contracts.py`), rejestr typów z YAML, pipeline input→output, CLI, zalążek API, skrypt F1 zgodny z ustaleniami UZP, dane treningowe, decyzje z Discorda.
Stan: testy 29/29, klasyfikacja 191/196, F1 = 0 (zaślepki ekstrakcji).

## E1 — Harness jakości
**Cel:** zanim powstanie właściwa logika, mamy automat, który mierzy i pilnuje każdej kolejnej zmiany.
- `data/splits.yaml`: podział spraw na `dev` (~45) i `holdout` (~15), zamrożony z seedem, oraz lista negatywów.
- `eval/gate.py`: uruchamia pipeline na `dev` (i osobno na `holdout`), porównuje z `eval/baseline.json`, kończy się kodem ≠ 0 przy regresji; `--update-baseline` tylko świadomie.
- Walidator kształtu wyniku: JSON Schema generowany z szablonów, test na każdym wyniku.
- LLM record/replay: tryby `replay` (domyślny w testach/CI), `record`, `live`.
- `ruff` + `pyproject.toml` (konfiguracja narzędzi), `pre-commit`.
- GitHub Actions: lint → pytest → gate (replay) → smoke; macierz Windows/Linux.
- Strukturalne logowanie i identyfikator przebiegu (run id) w trace.
**Bramka:** CI zielone na `main`; gate wykrywa celowo wprowadzoną regresję (test negatywny harnessu).

## E2 — Ingest produkcyjny
**Cel:** wierny tekst z każdego PDF-a, z pozycjami do trace.
- Porównanie pypdf vs pdfplumber vs pdftotext (jakość polskich znaków, kolejność kolumn, nagłówki) na całym zbiorze; wybór i uzasadnienie w `docs/decyzje/`.
- Czyszczenie: łamanie wierszy, dzielenie wyrazów, twarde spacje, ligatury, unifikacja cudzysłowów i myślników.
- Zachowanie mapowania offset → strona (do podświetlania źródła w GUI).
- OCR fallback dla stron bez tekstu (Tesseract `pol` lub rapidocr, CPU), z flagą `ocr_used`.
- Odporność: zaszyfrowane, uszkodzone, puste, bardzo duże PDF-y.
**Bramka:** testy na wszystkich 196 PDF-ach (brak wyjątków, minimalna długość tekstu, obecność polskich znaków); testy przypadków brzegowych; negatywy-skany przechodzą przez OCR albo są jawnie oznaczone.

## E3 — Klasyfikacja produkcyjna
**Cel:** typ wyłącznie z treści (UZP: nazwy plików mogą być dowolne), przewidywalna pewność, poprawne odrzucanie obcych dokumentów.
- Cechy z konfiguracji: frazy silne, słabe i negatywne, wagi pozycji (tytuł, nagłówek pierwszej strony), struktura (np. „Kwota przelewu” + IBAN).
- Kalibracja progów na dev; LLM fallback przy niskiej pewności (lista typów z rejestru + „nieznany”).
- Dodatkowe negatywy: wyroki KIO, ogłoszenia BZP/TED, faktury, pisma; test z losowo zmienionymi nazwami plików.
**Bramka:** 100% na dev i holdout (pozytywy + negatywy), macierz pomyłek w raporcie, test „nazwy plików pomieszane”.

## E4 — Silnik ekstrakcji sterowany konfiguracją
**Cel:** jeden silnik, a typ dokumentu w całości opisany w YAML; to fundament punktów za rozszerzalność.
- Projekt DSL pól w YAML: źródła (`regex`, `llm`, `derived`, `const`), typ, normalizator, walidator, sekcja/kontekst (np. „po etykiecie Zamawiający”), listy elementów (np. pełnomocnicy).
- Rejestry wtyczek: normalizatory (data, kwota, IBAN, BZP, TED, NIP…), walidatory (format, bez wymuszania sum kontrolnych — ustalenie z UZP), ekstraktory.
- Polityka scalania i trace dla każdej wartości (metoda, fragment źródłowy, strona).
- Walidacja konfiguracji z czytelnymi błędami (`odw2json validate-config`).
- Typ referencyjny: **przelew** w całości na regułach.
**Bramka:** przelew F1 ≥ 0.98 na dev i holdout bez LLM; testy jednostkowe każdego normalizatora; błędny YAML daje zrozumiały komunikat.

## E5 — Reguły dla pełnomocnictwa i odwołania
**Cel:** wszystkie pola o sztywnym formacie bez LLM.
- Odwołanie: daty i miejscowość z nagłówka, KRS/NIP/REGON stron, BZP, TED, numer postępowania, e-mail pełnomocnika, `przez-pelnomocnika`.
- Pełnomocnictwo: KRS/NIP mocodawców, PESEL, typ mocodawcy.
- Raport pokrycia: które pola rozwiązują reguły, a które zostają dla LLM.
**Bramka:** precyzja pól regułowych ≥ 0.98 (FP kosztuje jak FN, więc lepiej `null` niż śmieć); gate bez regresji.

## E6 — Warstwa LLM i wybór modelu
**Cel:** najmniejszy model z UE, który domyka pola semantyczne (punkty za rozmiar modelu).
- Benchmark modeli (w toku w osobnej sesji: `scripts/bench_models.py` — Ministral 3B/8B/14B, Bielik 11B) → decyzja w `docs/decyzje/`.
- Prompty per typ z YAML: opisy pól, słownik powodów 1–12, reguła „tylko pierwszy zarzut”, mianownik imion; few-shot wyłącznie z dev.
- Wyjście strukturalne (JSON mode/schema), walidacja, ponowienie z informacją o błędzie, limit kosztu i tokenów, licznik kosztu w raporcie.
- LLM dostaje tylko brakujące pola i odpowiedni fragment tekstu, nie cały dokument.
**Bramka:** F1 globalne ≥ 0.95 na dev i różnica dev–holdout ≤ 0.03; kasety nagrane, więc CI deterministyczne; koszt przebiegu znany.

## E7 — Pętla jakości
**Cel:** systematyczne domykanie błędów bez przeuczenia.
- Raport błędów per pole i per dokument (diff predykcja vs GT), kategoryzacja przyczyn (ingest / klasyfikacja / reguła / LLM / normalizacja).
- Iteracje: poprawka → gate → commit; holdout sprawdzany tylko na końcu iteracji.
- Testy odporności: warianty formatowania (spacje w NIP, daty słownie i liczbowo, IBAN z `PL`), wielu zamawiających, konsorcja, osoba fizyczna jako mocodawca.
**Bramka:** F1 holdout na poziomie docelowym, ustalonym po E6; brak pól z F1 < 0.85 bez udokumentowanego powodu.

## E8 — API produkcyjne
**Cel:** stabilny interfejs REST dla GUI i przyszłej integracji w UZP.
- Endpointy: przetwarzanie dokumentów i spraw, wynik + trace, podgląd PDF, lista i walidacja typów, health/version.
- Walidacja wejścia (typ, rozmiar), spójne błędy, limity, logi żądań, dokumentacja OpenAPI.
**Bramka:** testy API (TestClient) dla ścieżek pozytywnych i błędów; kontrakt OpenAPI w repo.

## E9 — GUI (React + Vite + TS)
**Cel:** upload → analiza → PDF i JSON obok siebie, z przejrzystym pochodzeniem pól (wg `docs/benchmarki-ux.md`).
- Upload wielu plików/sprawy, lista dokumentów z typem i pewnością, podgląd PDF, JSON z podświetleniem źródła po kliknięciu pola, pobieranie JSON.
- Widok konfiguracji typów (podgląd, walidacja; edycja jako opcja).
- Dostępność (WCAG), stany błędów i ładowania; `web/dist` commitowany (tester nie ma Node).
**Bramka:** testy komponentów (Vitest), test e2e (Playwright: upload → wynik), audyt dostępności (axe).

## E10 — Rozszerzalność udowodniona
**Cel:** pokazać jury, że nowy typ dokumentu powstaje bez zmian w kodzie.
- 4. typ dokumentu dodany wyłącznie konfiguracją (kandydaci: wyrok/postanowienie KIO albo zawiadomienie o wyborze oferty) + mini-zbiór testowy.
- Komenda `odw2json new-doctype <id>` generująca szkielet YAML, szablonu i promptu; przewodnik `docs/nowy-typ-dokumentu.md` krok po kroku.
- Dodanie pola do istniejącego typu samą konfiguracją (test).
**Bramka:** test integracyjny „nowy typ z samej konfiguracji” zielony; diff kodu przy dodaniu typu = 0 linii.

## E11 — Pakowanie i wdrożenie
**Cel:** działa u organizatora za pierwszym razem.
- Przypięte wersje (`requirements.txt` + lock), `start.bat`/`start.sh`, Docker Compose, obsługa klucza API (`.env`) i limitów zapytań.
- Smoke na czystym Windowsie (świeży venv, brak Node) i w Dockerze; tryb offline bez LLM, który degraduje się do samych reguł zamiast się wywracać.
- Wydajność: czas na sprawę, równoległość, limity dostawcy.
**Bramka:** `scripts/smoke.ps1` zielony na czystej maszynie; README da się wykonać krok po kroku.

## E12 — Dokumentacja, zgłoszenie, finał
- README (uruchomienie, architektura, użyty LLM i uzasadnienie rozmiaru), `docs/architektura.md`, konfiguracja typów, dodawanie nowej klasy (wymagane do nagrody, §3.5 regulaminu).
- Raport jakości: F1 dev/holdout per typ i pole, koszt, czas.
- Zgłoszenie: tytuł, link do repo; checklista zgodności z regulaminem i README UZP.
- Prezentacja finałowa: demo GUI, demo nowego typu bez kodu, argumentacja rozmiaru modelu i kosztu.
**Bramka:** checklista zgłoszenia odhaczona, tag wydania `v1.0.0`.

---

## Zależności między etapami
E1 → (E2 → E3) → E4 → E5 → E6 → E7 → E10 → E11 → E12, równolegle E8 → E9 po E4. Benchmark modeli (część E6) trwa już w osobnej sesji i nie blokuje E1–E5.

## Model pracy: orkiestrator + agenci

Główna sesja (Opus) **nie pisze kodu produkcyjnego sama**. Projektuje, rozpisuje zadania, deleguje je, weryfikuje i scala. Każde podzadanie z planu etapu idzie do agenta z kompletnym briefem: pliki, interfejsy, testy do napisania, kryterium „done”.

### Kto co robi

| Rola | Model / rozumowanie | Zadania |
|---|---|---|
| Orkiestrator | **Opus**, główna sesja | projekt etapu, plan zadań, kontrakty i interfejsy, decyzje architektoniczne, finalna weryfikacja bramki, merge |
| Implementator | **Sonnet**, effort medium | zadania z jasnym interfejsem i testami: normalizatory, ekstraktory, endpointy API, komponenty GUI, skrypty harnessu |
| Implementator trudnych zadań | **Sonnet**, effort high | logika z niejednoznacznością: silnik DSL pól (E4), polityka scalania regex/LLM, prompty i pętla błędów (E6–E7), klasyfikacja z kalibracją (E3) |
| Prace mechaniczne | **Haiku**, effort low | kopiowanie i porządkowanie danych, generowanie fixture'ów i kaset, formatowanie dokumentacji, uruchomienie eval i zebranie raportu, aktualizacja CHANGELOG |
| Research | **Sonnet**, effort medium | porównania bibliotek i modeli, dokumentacja dostawców, wzorce UX |
| Reviewer zadania | **Sonnet**, effort high (świeży kontekst) | review każdego zadania względem planu: testy, kontrakty, zgodność ze specem |
| Reviewer etapu | **Opus** (świeży kontekst) | review całej gałęzi etapu przed merge; zawsze dla E4, E6, E10 i zmian w `contracts.py` |

Zasady, żeby tańsze modele nie obniżały jakości:
- Haiku nigdy nie dotyka logiki ekstrakcji, klasyfikacji ani kontraktów, tylko prac mechanicznych z jednoznacznym wynikiem.
- Agent nie zmienia `contracts.py`, `config_loader.py` ani bramki `eval/` bez zlecenia orkiestratora.
- Każde zadanie przechodzi przez pełny harness (pytest + gate), zanim orkiestrator je przyjmie. Raport agenta to deklaracja, nie dowód: orkiestrator sam odpala testy i patrzy w diff.
- Zadanie odrzucone przez reviewera wraca do implementatora z uwagami; po dwóch nieudanych próbach przejmuje je model o poziom wyżej.

## Git jako część harnessu

- `main` zawsze zielony (CI + gate). Bezpośrednie commity na `main` tylko dla dokumentacji orkiestratora.
- Gałąź na etap: `etap/E<n>-<nazwa>`. Każdy agent pracuje w **osobnym git worktree** na gałęzi zadania `etap/E<n>/<zadanie>`, więc równoległe agenty nie nadpisują sobie plików (w tym folderze pracuje już kilka sesji naraz).
- Jedno zadanie = jeden lub kilka małych commitów w konwencji `typ(zakres): opis` (`feat(extract): normalizator IBAN`), z wynikiem testów w treści.
- Zadanie → merge do gałęzi etapu po review; etap → PR do `main` z raportem gate (F1 dev/holdout, diff względem bazy) → merge po review etapu.
- Ochrona `main` na GitHubie (wymagane CI), tag `v0.<n>` po każdym etapie, `v1.0.0` na zgłoszenie.
- Hook lokalny (pre-commit): ruff + szybkie testy; pełny gate w CI.

## Rytm pracy w każdym etapie
1. Orkiestrator pisze plan etapu: zadania, przypisany model i effort, testy, bramka. Ty akceptujesz.
2. Zadania niezależne idą do agentów równolegle (worktrees), zależne kolejno; każde w TDD.
3. Każde zadanie przechodzi review zadania, pytest + gate i merge do gałęzi etapu.
4. Na koniec etapu: review etapu (Opus), pełny gate na dev i holdout, PR do `main`, tag, wpis w `CHANGELOG.md` z F1.
