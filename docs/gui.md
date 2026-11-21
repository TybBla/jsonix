# GUI — wgrywanie dokumentów, wyniki i podgląd źródła

GUI to statyczne pliki HTML/CSS/JS w `web/static/`, serwowane przez FastAPI. Nie wymaga Node ani kroku budowania i działa offline: PDF.js i font Open Sans są dołączone w `web/static/vendor/` (licencje i wersje: `web/static/vendor/README.md`).

## Uruchomienie

```powershell
python -m odw2json serve          # albo start-gui.bat (otwiera przeglądarkę)
```

Otwórz http://127.0.0.1:8000. Opis API (OpenAPI): http://127.0.0.1:8000/docs.

## Jak to działa

1. **Dodaj pliki** — przeciągnij pliki PDF na pole albo wybierz je przyciskiem „Dodaj plik”. Pliki są sprawdzane od razu (format PDF, pusty plik, limit 25 MB). Błędy są pokazywane przy pliku i w podsumowaniu na górze strony.
2. **Analizuj** — pliki trafiają do `POST /api/jobs`. Pasek postępu pokazuje wysyłkę (%), a potem „Przeanalizowano N z M”. Stan joba jest odpytywany z `GET /api/jobs/{id}`.
3. **Wyniki klasyfikacji** — tabela z typem dokumentu, pewnością (niska pewność ma ikonę i słowo „niska”), ostrzeżeniami i błędami. Dokument nierozpoznany ma oznaczenie „Nieznany dokument” (wynikowy JSON to `{}`). Pobierzesz tu JSON każdego pliku albo wszystkie naraz (ZIP).
4. **Sprawdź dane** — po lewej pola pogrupowane jak w JSON, po prawej dokument PDF. Wybierz pole (kliknięciem albo klawiszem Tab), a podgląd przewinie się do fragmentu źródłowego i podświetli go (obramowanie + etykieta pola). Kliknięcie podświetlenia zaznacza pole. Na wąskim ekranie przełączasz widok przyciskami „Pola / Dokument”.
5. **Popraw wartość (opcjonalnie)** — „Zmień” przy polu otwiera edycję (Enter zapisuje, Esc anuluje, puste pole = `null`). Zmienione pole ma oznaczenie „Zmieniono ręcznie” i przycisk „Przywróć wartość z dokumentu”. Liczby zostają liczbami („7 500,50” → `7500.5`).
6. **Pobierz JSON** — wynik dokumentu jako plik `.json` o nazwie jak PDF, razem z Twoimi zmianami.

## Skąd się bierze podświetlenie

Każde pole ma w `trace` stronę (`page`, liczona od 0) i fragment tekstu (`source_snippet`). GUI szuka fragmentu w warstwie tekstowej PDF.js (`web/static/js/match.js`): porównuje tekst bez białych znaków, z ujednoliconymi cudzysłowami i myślnikami i z pominięciem dzielenia wyrazów na końcu wiersza. Jeśli w znalezionym fragmencie jest wartość pola, podświetlana jest sama wartość. Jeśli cały fragment się nie znajdzie, GUI szuka jego najdłuższej części (najpierw zawierającej wartość).

Przy każdym polu czytnik ekranu odczyta „Źródło: strona N, „…fragment…””.

Lista pól powstaje z `data`, a nie z `trace`, więc widać też pola bez wartości („Nie podano”). Etykiety pól są w `web/static/js/fields.js`; pole nowego typu dokumentu bez etykiety w słowniku dostaje ją automatycznie z nazwy klucza (`numer_umowy` → „Numer umowy”), więc nowy typ działa w GUI bez zmian kodu.

## Ograniczenia

- **Skany bez warstwy tekstowej** (ostrzeżenie „OCR strony N”): PDF nie ma tekstu do wyszukania, więc zamiast podświetlenia jest komunikat „Nie znaleziono tego fragmentu w dokumencie. Ta strona jest skanem bez warstwy tekstowej.”
- **Pola wyliczone** (`method: derived`, np. opis czynności ze słownika) nie mają fragmentu źródłowego — GUI pokazuje komunikat ostrzegawczy z informacją, że wartość wyliczono.
- Gdy `source_snippet` wskazuje inny fragment niż ten z wartością, podświetlany jest fragment (to informacja zwrotna dla ekstrakcji, nie błąd GUI).
- Joby są trzymane w pamięci serwera i w `output/.jobs/`; po restarcie serwera albo po 24 h trzeba wgrać pliki ponownie.
- Zmiany wpisane w GUI trafiają do „Pobierz JSON” na ekranie „Sprawdź dane”. ZIP i „Pobierz JSON” w tabeli wyników zawierają wynik z serwera (bez zmian ręcznych). Zmiany są trzymane w przeglądarce do odświeżenia strony.

## Dostępność

Styl wg Design System Gov.pl (kolory, Open Sans, komunikaty z piktogramem), pełna obsługa klawiaturą, link „Przejdź do treści”, podsumowanie błędów z fokusem i prefiksem „Błąd:” w tytule strony, regiony `role="alert"` / `role="status"`, status nigdy tylko kolorem, przełącznik wysokiego kontrastu i rozmiaru tekstu. Deklaracja dostępności: `/static/deklaracja-dostepnosci.html`.

## Testy

- `tests/test_api.py` — API jobów (upload, walidacja, path traversal, pobieranie PDF/JSON/ZIP).
- `tests/test_gui_static.py` — struktura strony (landmarki, ARIA, teksty Gov.pl, lokalne zasoby), a z Node.js także logika JS: dopasowanie fragmentów na prawdziwym tekście PDF z `przyklad_01` (każde pole z `page` w `tests/fixtures/gui/*.result.json` musi zostać znalezione na właściwej stronie).
- `scripts/smoke_gui.py` — test dymny na uruchomionym serwerze.
