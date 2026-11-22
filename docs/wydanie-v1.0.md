# jsonix v1.0.0 — notatki wydania (szkic do GitHub Release)

**jsonix** zamienia dokumenty PDF spraw odwoławczych KIO na dane JSON zgodne ze schematami UZP. Rozpoznaje
odwołanie, pełnomocnictwo i potwierdzenie przelewu z treści, wyodrębnia pola i dla każdej wartości pokazuje, skąd
pochodzi. Dokument spoza tych typów daje `{}`. Zgłoszenie do zadania „Odwołania2json” (HackNation 2026, UZP).

## Uruchomienie
- **Windows:** dokumenty do `input\<sprawa>\`, potem `.\start.bat`. Wyniki są w `output\<sprawa>\`. Przy pierwszym
  uruchomieniu skrypt sam tworzy środowisko (Python 3.13 lub 3.14).
- **GUI:** `.\start-gui.bat`, potem http://127.0.0.1:8000.
- **Docker:** `docker compose up --build` (GUI) albo `docker compose run --rm app python -m odw2json run` (wsad).
  Plik `.env` jest opcjonalny.

## Najważniejsze
- **Jakość (F1 wg reguł UZP):** dokumenty z tekstem 0,999 dev / 0,997 holdout, skany z OCR 0,992 / 0,967,
  klasyfikacja bez błędów, dokumenty spoza typów rozpoznane 15/15 (dev) i 13/13 (holdout), w tym skany. Szczegóły: `docs/raport-jakosci.md`.
- **Bez LLM, z wyboru:** 20/20 pkt za moc modelu, bez kosztów i bez wysyłania danych. Uzasadnienie:
  `docs/decyzje/E6-bez-llm.md`.
- **Konfiguracja zamiast kodu:** typy dokumentów i pola są w `config/doctypes/*.yaml`. Przykład 4. typu dodanego
  wyłącznie konfiguracją: `examples/nowy-typ/orzeczenie_kio`.
- **Transparentność:** trace (metoda, strona, fragment) dla każdej wartości, a w GUI podświetlenie źródła w PDF
  w obie strony i „Dlaczego ten typ?”.
- **GUI dla urzędnika:** wiele plików naraz, PDF obok danych, ręczne poprawki z przywracaniem, ZIP; styl Gov.pl,
  klawiatura, wysoki kontrast, działa offline.
- **Gotowe do uruchomienia:** działa na CPU (i7 / 16 GB, bez GPU) i offline. Przypięte wersje zależności, Docker
  z healthcheckiem. Przy limicie czasu przerwany przebieg zostawia częściowe wyniki.

## Dokumentacja
README, `docs/architektura.md`, `docs/nowy-typ-dokumentu.md`, `docs/gui.md`, `docs/zgloszenie.md` (zgodność
z regulaminem i licencje), `docs/kryteria-uzp.md`, `docs/decyzje/`.

## Znane ograniczenia
- Na Pythonie 3.15+ OCR skanów jest niedostępny (brak paczek `onnxruntime`), a skan dostaje ostrzeżenie. Pełny wynik
  daje Python 3.13 lub 3.14 albo Docker.
- Skan OCR trwa ok. 2 s na stronę na CPU (`docs/decyzje/E11-wydajnosc.md`).
- Spacje w numerze rachunku: UZP nie rozstrzygnęło wprost; zapisujemy bez spacji, z „PL”, gdy jest w dokumencie (kryteria, pkt 5a).
