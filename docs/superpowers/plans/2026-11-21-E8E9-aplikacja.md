# E8+E9 — Aplikacja: API + GUI (plan etapu, realizacja: drugi członek zespołu)

> **Dla wykonawcy i jego agenta (Claude Code):** najpierw przeczytaj `AGENTS.md`, `docs/kryteria-uzp.md` i ten plan. Etap jest niezależny od trwających prac nad skanami, klasyfikacją i ekstrakcją — pracujesz **wyłącznie na plikach z listy „Pliki”**. TDD, harness z AGENTS.md przed każdym commitem, commity bez stopek `Co-Authored-By`. Gałąź etapu: `etap/E8E9-aplikacja` (z `main`), zadania na `etap/E8E9/<id>`, na koniec PR do `main`.

## Cel
Działający prototyp „wgraj PDF → analiza → podgląd dokumentu obok wyodrębnionych danych → pobierz JSON”, zgodny z ideałem UZP z FAQ 12b („widok obok siebie: dokument źródłowy i wyodrębnione dane”). GUI daje 1–10 pkt w finale. Podgląd **PDF obok pól z podświetleniem źródła to wymóg must-have zespołu** (wyróżnik przed jury).

## Ograniczenia
- **Bez kroku budowania frontu** (decyzja redukcji zakresu v1.0): statyczne HTML/CSS/JS w `web/static/`, serwowane przez FastAPI. Bez Node na maszynie jury. React → backlog po v1.0.
- Podgląd PDF: **PDF.js** (Apache-2.0) **dołączony do repo** w `web/static/vendor/pdfjs/` (wersja `legacy`/`build` + `pdf.worker`), żeby działało offline. Bez CDN w ścieżce krytycznej.
- Dodatkowe biblioteki JS tylko z licencją MIT/BSD/Apache, dołączone lokalnie (np. bez frameworka albo Alpine.js/htmx — wybór wykonawcy, uzasadnij w PR).
- Backend: istniejący FastAPI w `odw2json/api/__init__.py`, uruchamiany `python -m odw2json serve`. Python 3.13+. Nowe zależności Python tylko jeśli konieczne (MIT/BSD/Apache), wpisane do `requirements.txt`.
- **Nie zmieniaj** `odw2json/contracts.py`, `pipeline.py`, `ingest/`, `classify/`, `extract/`, `eval/`, `config/` — korzystaj z ich publicznych API. Potrzebna zmiana → opisz w PR / zgłoś właścicielowi projektu.
- Ekstrakcja jest jeszcze w budowie (zwraca szablon z `null`). Do pracy nad GUI używaj **plików wzorcowych z realistycznym trace**: `tests/fixtures/gui/przyklad_01_*.result.json` (PDF-y: `data/train/przyklad_01/*.pdf`). Format = to, co zwraca API.
- Styl i dostępność: wg `docs/benchmarki-ux.md` (sekcje 2, 3, 6) — Design System Gov.pl (kolory, Open Sans, komunikaty), pełna obsługa klawiaturą, `role="alert"/"status"`, status nie tylko kolorem.

## Kontrakt danych (z backendu)
Wynik dla pliku (obecny `POST /api/process` + rozszerzenia z tego etapu):
```json
{
  "file": "odwolanie.pdf",
  "classification": {"doc_type": "odwolanie" | null, "confidence": 0.0-1.0, "method": "keywords"},
  "data": { ...JSON wg config/schemas/<typ>.json... } | {} ,
  "trace": [ {"path": "Odwolujacy[0].nip", "value": "9999284065", "method": "regex|llm|derived|default",
              "source_snippet": "KRS: 9999405188, NIP: 9999284065, REGON: 999642785" | null,
              "page": 0 | null} ],
  "warnings": ["..."], "pages": 2
}
```
- `page` jest **0-based** (strona 1 w PDF = `0`). `source_snippet` to fragment **tekstu po czyszczeniu** (cudzysłowy ASCII, zwinięte spacje) — w PDF.js szukaj go odporne na różnice białych znaków i łamania wierszy (normalizacja: casefold + zwinięte whitespace; dopasowanie po najdłuższym wspólnym fragmencie zawierającym `value`).
- `page: null` / brak snippetu → komunikat „Nie znaleziono tego fragmentu w dokumencie” (bez udawanego podświetlenia). Skany (warning „OCR strony N”) nie mają warstwy tekstowej w PDF → zawsze komunikat zamiast podświetlenia.
- Dokument nieznany: `classification.doc_type = null`, `data = {}`.

## Zadania

### A1 — API pod GUI (backend)
**Pliki:** `odw2json/api/**`, `tests/test_api.py`, `requirements.txt` (tylko jeśli konieczne).
- `POST /api/jobs` (multipart, wiele PDF) → `{job_id}`; przetwarzanie w tle (wątek/`BackgroundTasks`), pliki w katalogu tymczasowym joba (`output/.jobs/<job_id>/`, gitignored), sprzątanie po 24 h lub przy starcie.
- `GET /api/jobs/{job_id}` → status (`pending|running|done|error`), postęp `processed/total`, wyniki per plik (kontrakt wyżej, dokładnie te same pola co trace z `pipeline.process_file`).
- `GET /api/jobs/{job_id}/files/{name}/pdf` → oryginalny PDF (do PDF.js); `GET .../json` → wynikowy JSON (`Content-Disposition: attachment`, nazwa jak PDF z `.json`); `GET /api/jobs/{job_id}/zip` → wszystkie JSON-y.
- Zostaw `POST /api/process` (zgodność). `GET /api/health`, `GET /api/doctypes` bez zmian.
- Walidacja: tylko `.pdf` (sprawdź nagłówek `%PDF-` w pierwszych 1024 B), limit rozmiaru (konfigurowalny, domyślnie 25 MB/plik), czytelne błędy po polsku; nazwy plików sanityzowane (ochrona przed path traversal), polskie znaki zachowane w wyświetlanej nazwie.
- `GET /` serwuje `web/static/index.html`; statyczne pod `/static/`.
- Testy (TestClient): upload 3 PDF z `data/train/przyklad_01` → done, kontrakt pól; plik nie-PDF → błąd per plik; path traversal w nazwie; pobranie JSON i ZIP; nieznany job → 404. Testy szybkie (bez OCR: nie używaj `data/train/skany` w testach szybkich).

### A2 — GUI: wgrywanie i wyniki
**Pliki:** `web/static/**` (bez `vendor/`), `tests/test_gui_static.py`.
- Ekran 1 (uploader wg Gov.pl): przeciągnij/wybierz wiele PDF, lista z rozmiarem i usuwaniem, przycisk „Analizuj”, pasek postępu „2 z 3”, błędy per plik + podsumowanie błędów z fokusem.
- Ekran 2: lista dokumentów z typem (czytelna nazwa z `/api/doctypes`), pewnością i ostrzeżeniami; „Nieznany dokument” wyraźnie oznaczony; „Pobierz wszystkie (ZIP)”.
- Test statyczny: `index.html` się serwuje, zawiera wymagane landmarki/aria (prosty test HTML przez TestClient + parser `html.parser`).

### A3 — GUI: PDF obok pól z podświetleniem (MUST HAVE)
**Pliki:** `web/static/**`, `web/static/vendor/pdfjs/**` (dołączony PDF.js + plik `LICENSE`), `docs/gui.md`.
- Układ dwukolumnowy: lewa kolumna pola pogrupowane jak w JSON (sekcje, listy z numeracją), prawa PDF (PDF.js z warstwą tekstową). Wąski ekran: przełącznik „Pola / Dokument”.
- Klik/fokus pola → przewinięcie do `page` i podświetlenie `source_snippet` (obramowanie + etykieta pola, kontrast ≥ 3:1, nie tylko kolor). Klik w podświetlenie zaznacza pole. Obsługa klawiaturą.
- Pola `null` → „Nie podano”; brak źródła → komunikat ostrzegawczy (patrz kontrakt).
- Tekst dla czytnika ekranu przy polu: „Źródło: strona N, „…fragment…””.
- „Pobierz JSON” dla dokumentu.
- *Should-have (jeśli zostanie czas):* edycja wartości z „Przywróć wartość z dokumentu” i oznaczeniem zmian; pobrany JSON zawiera edycje.
- `docs/gui.md`: jak uruchomić, zrzuty ekranu (PNG w `docs/img/`), ograniczenia (skany bez podświetlenia).

### A4 — Uruchomienie i smoke
**Pliki:** `start-gui.bat` (nowy: `python -m odw2json serve` + otwarcie przeglądarki), `scripts/smoke_gui.py`, `README.md` (sekcja „GUI”, krótka), `docker-compose.yml` (tylko jeśli trzeba).
- `scripts/smoke_gui.py`: uruchamia serwer w tle, wysyła 3 PDF z `przyklad_01`, czeka na `done`, sprawdza kontrakt, pobiera ZIP; kod wyjścia 0/1.
- Ręczny test w przeglądarce (Chrome/Edge): checklista w opisie PR (upload, podświetlenie na 3 typach, nieznany dokument, klawiatura).

## Bramka etapu
- `python -m pytest -q` exit 0; ruff czysty; `python -m eval.gate --split dev` bez regresji (etap nie powinien jej dotykać).
- `scripts/smoke_gui.py` exit 0 lokalnie; CI zielone.
- Checklista ręczna w PR odhaczona, w tym podświetlenie źródła działające na `przyklad_01` dla wszystkich pól, które mają `page` w pliku wzorcowym.
- Licencje dołączonych bibliotek JS w repo (`LICENSE` przy `vendor/`).
- PR `etap/E8E9-aplikacja` → `main` z opisem, zrzutami i wynikami; review przez właściciela projektu.

## Integracja z resztą (dla świadomości)
Gdy ekstrakcja (E4+E5) zacznie zwracać prawdziwe wartości i trace, GUI zadziała bez zmian — kontrakt jest stały. Jeśli w trakcie okaże się, że GUI potrzebuje dodatkowego pola w trace (np. offsetu znaku), zgłoś to; dodamy je jako opcjonalne pole kontraktu.
