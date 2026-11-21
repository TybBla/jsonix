# Odwołania2JSON — projekt i plan wykonawczy

Data: 2026-11-21 · Repo zespołu: https://github.com/TybBla/HackNation-Project · Termin: ~24h · Zespół: 3 osoby (sektory A/B/C)

---

## 1. Cel i dlaczego

Aplikacja, która z PDF-ów sprawy odwoławczej KIO rozpoznaje typ dokumentu (odwołanie / pełnomocnictwo / potwierdzenie przelewu / **nieznany**) i zwraca JSON zgodny ze schematem z `oczekiwane-json/`.

Co decyduje o wygranej:
1. **Preselekcja = 100% F1** na ukrytym zbiorze (≥10 spraw, syntetyczne dokumenty oparte na realnych case'ach). Bez wysokiego F1 nie ma finału → jakość ekstrakcji to priorytet nr 1.
2. **Finał (README organizatora):** 50% F1 + 50% rozbudowa, w tym:
   - 1–20 pkt **za rozmiar modelu (mniejszy = więcej punktów)**,
   - 1–20 pkt za dodawanie typów dokumentów/pól **samą konfiguracją**,
   - 1–10 pkt za dodatki (GUI itp.).

## 2. Ograniczenia (twarde fakty)

| Źródło | Wymaganie |
|---|---|
| README | Python **3.13+**, `requirements.txt`, foldery `input/` i `output/` w katalogu głównym |
| README | `output/<case>/<nazwa_pliku_wejściowego>.json` — nazwa JSON = nazwa PDF (np. `potwierdzenie_przelewu.pdf` → `potwierdzenie_przelewu.json`) |
| README | Uruchomienie z CLI / wrappera (`start.bat`); GUI opcjonalne, punktowane |
| README/FAQ | Tylko open source, otwarty LLM po **API firmy z serwerami w UE/EOG**; dostarczamy klucz API |
| README | Maszyna testowa: laptop i7, 16 GB RAM, bez GPU, z internetem; brak limitu czasu |
| Discord UZP | JSON **ściśle zgodny z formatem** (bez dodatkowych pól typu cytat źródła) |
| Discord UZP | Brak skanów bez warstwy tekstowej w zbiorze testowym (OCR = tylko zabezpieczenie) |
| Regulamin §3.5 | Do wypłaty nagrody: Docker Compose, instrukcja, dokumentacja architektury, konfiguracji klasy i dodawania nowej klasy |
| FAQ 6 | Nie zmyślać — brak informacji → `null` |

**Sprzeczność do wyjaśnienia z UZP:** dokument spoza puli — README: „pusty plik .json”, Discord: „nie zwracamy JSON-a”. Implementujemy przełącznik `unknown_output: empty_file | none` w konfiguracji; domyślnie wg najnowszej odpowiedzi (Discord → `none`) do czasu potwierdzenia.

## 3. Wnioski z danych treningowych (60 spraw)

- Każda sprawa: `odwolanie.pdf`, `pelnomocnictwo.pdf`, `potwierdzenie_przelewu.pdf` + 3 JSON GT. W przykładach 10 i 37 dorzucone negatywy (ogłoszenie TED, ogłoszenie BZP). `dane/negatywne/` — 12 dokumentów, 3 to skany bez tekstu.
- Wszystkie pozytywne PDF-y mają warstwę tekstową.
- `czynnosc_powod_id` → `czynnosc_opis` to **słownik 1:1** (w danych id 1–11; 12 nieznane). LLM wybiera tylko id, opis wstawia kod ze słownika.
- Odwołanie: 1 odwołujący zawsze; 3/60 ma wielu zamawiających; `data`/`miejscowosc` null w 15/60, `numer_bzp` null 12/60, `numer_ted` null 13/60.
- Pełnomocnictwo: 6/60 wielu mocodawców, 4/60 osoba fizyczna, PESEL tylko 1/60; często kilku pełnomocników; imiona w **mianowniku**.
- Przelew: bardzo regularny układ (Nadawca/Beneficjent/Kwota/Data/Numer/Tytułem) — prawie w całości regex.
- Formaty normalizowane: daty ISO, BZP `YYYY/BZP########` bez spacji, TED `NNNNNN-YYYY`, kwota float, PESEL int, IBAN bez `PL` i spacji.

## 4. Podejścia (rozważone)

| Podejście | Plusy | Minusy |
|---|---|---|
| A. Wszystko przez LLM (cały tekst → JSON) | szybkie w budowie, elastyczne | mały model myli formaty i liczby; F1 zależy od modelu; drogo w tokenach; słaba transparentność |
| B. Tylko reguły/regex | deterministyczne, darmowe | nazwy podmiotów, odmiana imion, powód odwołania, tytuł — nie do opanowania na ukrytych wariantach |
| **C. Hybryda: reguły + mały LLM, sterowana konfiguracją (WYBRANE)** | pola o sztywnym formacie z regex (pewne), LLM tylko do pól semantycznych → mały model wystarczy (punkty za rozmiar); każde pole ma źródło i metodę (transparentność); nowe typy dokumentów = nowy plik YAML | więcej projektowania kontraktów na starcie |

Zasada łączenia: dla każdego pola konfiguracja mówi `regex` / `llm` / `derived` (np. opis ze słownika) i kolejność. Wartość regexowa wygrywa, LLM uzupełnia; walidator (format, suma kontrolna NIP/REGON/PESEL/IBAN) odrzuca śmieci → `null` (FP kosztuje tyle co FN, a `null` przy braku w GT daje TN).

## 5. Architektura

```
PDF ─► [A] ingest ─► Document(text, pages, meta) ─► [A] classifier ─► doc_type | UNKNOWN
                                                                   │
                         doctypes/<typ>.yaml  ◄────────────────────┘
                                │
                     [B] extractor: regex rules ─┐
                                 LLM (prompt+schema z YAML) ─┤─► merge ─► normalize ─► validate ─► JSON (ściśle wg schematu)
                                 derived/lookup ─┘                                                   + trace (osobny plik, GUI)
                                │
              [C] CLI (input/→output/) · FastAPI REST · React GUI (PDF | JSON + źródła pól)
```

**Konfiguracja typu dokumentu** (`config/doctypes/odwolanie.yaml`, szkic):
```yaml
id: odwolanie
output_template: schemas/odwolanie.json      # kształt wyniku (kolejność kluczy, nulle)
classify:
  keywords: {strong: ["ODWOŁANIE", "Krajowej Izby Odwoławczej", "Zarzut"], negative: ["Ogłoszenie o zamówieniu"]}
  llm_fallback: true
fields:
  OdwolanieKIO.data:          {type: date,  sources: [regex: header_date, llm]}
  OdwolanieKIO.czynnosc_powod_id: {type: int, sources: [llm], enum_ref: lookups/czynnosc_powod.yaml}
  OdwolanieKIO.czynnosc_opis: {type: str, derived: {lookup: czynnosc_powod, from: OdwolanieKIO.czynnosc_powod_id}}
  Odwolujacy[].krs:           {type: krs,  sources: [regex, llm]}
  ...
llm:
  prompt: prompts/odwolanie.md               # instrukcje pól, przykłady few-shot
```
Dodanie nowego typu = nowy YAML + szablon wyniku + (opcjonalnie) prompt. Zero zmian w kodzie — to pokazujemy w finale na żywo.

**LLM:** jeden klient OpenAI-kompatybilny; `base_url`, `model`, `api_key` z `.env` / `config/llm.yaml`. Temperatura 0, wymuszony JSON (json mode / schema, jeśli dostawca wspiera), retry + cache odpowiedzi na dysku (powtarzalność, oszczędność tokenów). Model: Qwen z abonamentu (szczegóły → §10 ryzyka); próbujemy od najmniejszego, który trzyma F1.

## 6. Struktura repo (`main` = baza)

```
HackNation-Project/
├── README.md                 # instrukcja uruchomienia (CLI, GUI, Docker), opis LLM
├── requirements.txt
├── .env.example              # LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
├── start.bat / start.sh      # wrapper: python -m odw2json run input output
├── docker-compose.yml, Dockerfile
├── input/  output/           # wymagane przez organizatora (.gitkeep)
├── config/
│   ├── app.yaml              # unknown_output, progi, ścieżki
│   ├── llm.yaml
│   ├── doctypes/{odwolanie,pelnomocnictwo,przelew}.yaml
│   ├── schemas/{...}.json    # szablony wyników (bez komentarzy)
│   ├── lookups/czynnosc_powod.yaml
│   └── prompts/{...}.md
├── odw2json/                 # (pakiet w katalogu głównym — działa bez instalacji)
│   ├── contracts.py          # Document, Classification, FieldResult, ExtractionResult  ← WSPÓLNE, zamrożone na start
│   ├── ingest/               # [A] pdf → tekst, OCR fallback
│   ├── classify/             # [A]
│   ├── extract/              # [B] regex, llm, merge
│   ├── normalize/            # [B] daty, kwoty, numery, walidatory sum kontrolnych
│   ├── config_loader.py      # [B] ładowanie i walidacja YAML
│   ├── pipeline.py           # sklejenie: ingest→classify→extract→write (stub na main)
│   ├── cli.py                # [C]
│   └── api/                  # [C] FastAPI (+ serwuje web/dist)
├── web/                      # [C] React + Vite + TS; dist/ commitowany
├── eval/
│   ├── score.py              # nasz F1 wg reguł organizatora
│   └── README.md
├── data/train/               # kopia dane/ z repo UZP (+ dane/negatywne)
├── tests/
└── docs/                     # architektura, „jak dodać nowy typ dokumentu”
```

## 7. Kontrakty między sektorami (ustalane na `main` w godzinie 0)

```python
@dataclass
class Document:            # A → wszyscy
    path: Path; text: str; pages: list[str]; ocr_used: bool

@dataclass
class Classification:      # A → B, C
    doc_type: str | None   # id z config/doctypes lub None = nieznany
    confidence: float; method: str   # "keywords" | "llm"

@dataclass
class FieldResult:         # B → C (transparentność)
    path: str; value: Any; method: str  # "regex" | "llm" | "derived"
    source_snippet: str | None; page: int | None

@dataclass
class ExtractionResult:    # B → C
    doc_type: str; data: dict  # dokładnie kształt schematu
    trace: list[FieldResult]
```
Funkcje-interfejsy: `ingest.load(path) -> Document`, `classify.classify(doc, registry) -> Classification`, `extract.extract(doc, doctype_cfg) -> ExtractionResult`, `pipeline.process_case(dir) -> list[...]`. Na `main` każda ma działający **stub** (np. klasyfikacja po nazwie pliku, ekstrakcja zwraca szablon z nullami), więc każdy sektor może pracować i testować end-to-end od pierwszej minuty.

Trace zapisujemy **osobno** (`output/.trace/<case>/<plik>.trace.json` lub tylko w API), bo wynikowy JSON ma być ściśle zgodny z formatem.

## 8. Ewaluacja F1 (`eval/score.py`) — wspólne narzędzie wszystkich

Implementacja reguł z kryteriów:
- jednostka = liść JSON (ścieżka pola); TP = obecne i zgodne; TN = brak w obu (null/null); FP = tylko u nas **lub** obecne w obu, ale niezgodne; FN = brak u nas, jest w GT.
- „długie stringi” (nazwy, tytuł, tytuł przelewu, opis): podobieństwo ≥ 80% (rapidfuzz `ratio` po normalizacji whitespace/wielkości liter); reszta (KRS, NIP, daty, kwoty, id) — dokładnie po normalizacji.
- listy (Odwolujacy, Zamawiajacy, mocodawca, pelnomocnicy): dopasowanie po treści (optymalne przypisanie wg podobieństwa nazwy), nadmiarowe elementy = FP, brakujące = FN.
- dokument nieznany: poprawne „brak wyniku” = TN; dowolny wynik = FP. Błędny typ = wszystkie pola FP/FN.
- raport: F1 globalne, per typ dokumentu, per pole + lista najgorszych przypadków. Uruchamiane przed każdym merge do `main`.

Założenia, których nie znamy dokładnie (lista vs kolejność, miara 80%), zapisujemy jako parametry skryptu — można je potem dopytać na stoisku UZP i przestawić.

## 9. Sektory i gałęzie

Workflow: `main` chroniony, tylko przez PR; gałęzie `feat/a-ingest-classify`, `feat/b-extraction`, `feat/c-app`. Małe PR-y, merge co kilka godzin, każdy PR z wynikiem `eval/score.py`.

### Sektor A — wczytywanie, OCR, klasyfikacja
- `ingest`: pdfplumber/pypdf (tekst + strony), czyszczenie (łamania, myślniki, ligatury, polskie znaki); OCR fallback (Tesseract `pol` przez `pytesseract` lub `rapidocr` — bez GPU) gdy tekst < N znaków/stronę.
- `classify`: punktacja słów kluczowych z YAML (silne/negatywne/położenie w nagłówku), próg pewności; poniżej progu → LLM z listą typów z rejestru i opcją „nieznany”. Cel: **100% na 180 pozytywach + wszystkie negatywy** (w tym `dane/negatywne`, TED/BZP z przykładów 10 i 37, decyzje KIO).
- Done: `eval` klasyfikacji = macierz pomyłek bez błędów na danych treningowych; czas < 1 s/dokument bez LLM.

### Sektor B — ekstrakcja, konfiguracja, normalizacja
- `config_loader` + walidacja YAML (pydantic); rejestr typów dokumentów.
- Regexy: KRS/NIP/REGON/PESEL (z sumami kontrolnymi), IBAN, kwoty, daty słownie („20 marca 2026”) → ISO, BZP/TED z normalizacją, nagłówek „Miejscowość, dnia…”.
- LLM: prompt per typ z opisami pól (przeniesione z komentarzy w `oczekiwane-json`), few-shot z danych treningowych, wybór `czynnosc_powod_id` tylko z pierwszego zarzutu, imiona w mianowniku.
- merge + walidacja → `null` przy niepewności; budowa wyniku dokładnie wg szablonu (kolejność kluczy, typy: int vs str, float kwoty).
- Done: F1 ≥ 0.95 na zbiorze treningowym (hold-out ~15 spraw nieużywanych w promptach), wynik zgodny ze schematem w 100%.

### Sektor C — aplikacja, GUI, Docker, dokumentacja
- `cli.py`: `python -m odw2json run [input] [output]` (+ `start.bat`/`start.sh`), przetwarza wszystkie podfoldery `input/`, log postępu, odporność na błąd pojedynczego pliku.
- FastAPI: `POST /api/process` (upload PDF/ów), `GET /api/doctypes`, `GET /api/result/{id}` z trace; serwuje `web/dist`.
- React (Vite+TS): upload wielu PDF, lista dokumentów z typem i pewnością, **widok obok siebie: PDF (react-pdf) | JSON**, kliknięcie pola → podświetlenie źródłowego fragmentu, pobranie JSON. Dodatkowo podgląd/edycja YAML typów (pokaz „nowy typ bez kodu”).
- Docker Compose (jedna usługa `app`), README z instrukcją, `docs/architektura.md`, `docs/nowy-typ-dokumentu.md` (wymagane do nagrody).
- Done: czysty klon → `pip install -r requirements.txt` → `start.bat` działa na Windows bez Node; `docker compose up` działa.

## 10. Harmonogram (~24h)

| Godz. | Wszyscy / main | A | B | C |
|---|---|---|---|---|
| 0–1.5 | **Szkielet na main** (struktura, kontrakty, stuby, `eval/score.py`, dane, CI-lite) — przygotowuję ja | — | — | — |
| 1.5–6 | | ingest + klasyfikacja słownikowa | regexy + normalizacja + loader YAML | CLI + FastAPI + szkielet React |
| 6 | **Sync #1**: merge, pierwsze F1 end-to-end | | | |
| 6–12 | | negatywy, OCR fallback, LLM fallback | LLM dla pól semantycznych, merge, prompty | widok PDF/JSON, trace, Docker |
| 12 | **Sync #2**: F1 per pole → lista błędów, podział poprawek | | | |
| 12–19 | | pomoc B przy najgorszych polach | tuning, próby mniejszego modelu | edytor YAML, docs, demo „nowy typ” |
| 19–22 | **Freeze funkcji**; test na czystej maszynie Windows, klucz API, limity | | | |
| 22–24 | Zgłoszenie: tytuł, link, README, wyniki testów | | | |

## 11. Ryzyka i otwarte kwestie

1. **LLM „Qwen z abonamentu za 7 €” — największe ryzyko formalne.** Regulamin wymaga API świadczonego przez firmę z serwerów w UE/EOG, a klucz trafia do organizatora. Trzeba ustalić: który dostawca, gdzie są serwery, czy API jest OpenAI-kompatybilne, jakie limity zapytań (test na ≥10 sprawach × 3–4 dokumenty) i czy wolno udostępnić klucz osobie trzeciej. Jeśli coś nie pasuje → plan B: Scaleway / OVHcloud / Mistral (UE, OpenAI-kompatybilne). Architektura na to pozwala — zmiana to 3 linie w `.env`.
2. Pusty plik vs brak pliku dla dokumentu nieznanego → zapytać UZP; przełącznik w konfiguracji.
3. `czynnosc_powod_id = 12` — brak w danych; zapytać UZP o kanoniczny opis, dopisać do `lookups`.
4. Dokładna miara 80% i dopasowanie list w ocenie → zapytać na stoisku UZP; parametry w `eval/score.py`.
5. Przeuczenie na syntetycznych wzorcach → hold-out w ewaluacji, wgląd w dane testowe na stoisku UZP (FAQ 9).

## 12. Co zostawiam wykonawcom (decyzje lokalne)

Wybór biblioteki PDF/OCR (A), dokładna składnia YAML i promptów (B, w ramach kontraktów), biblioteki UI (C). Zmiana kontraktów z §7 — tylko przez PR do `main` z akceptacją pozostałych.
