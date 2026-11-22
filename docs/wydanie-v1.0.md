# jsonix v1.0.0 — notatki wydania (szkic do GitHub Release)

**jsonix** zamienia dokumenty PDF spraw odwoławczych KIO na dane JSON zgodne ze schematami UZP. Rozpoznaje
odwołanie, pełnomocnictwo i potwierdzenie przelewu z treści, wyodrębnia pola i dla każdej wartości pokazuje, skąd
pochodzi. Dokument spoza tych typów daje `{}`. Zgłoszenie do zadania „Odwołania2json” (HackNation 2026, UZP).

> **v1.0.1** (bieżąca wersja) zmienia tylko wygląd GUI: źródło wartości w dymku przy ikonce „i”, ostrzeżenia jako
> trójkąt z „!”, nagłówek bez logo, stopka z wersją i linkami. Ekstrakcja i wyniki F1 są takie same jak w v1.0.0.
> Szczegóły: [CHANGELOG.md](../CHANGELOG.md).

## Uruchomienie
- **Windows:** dokumenty do `input\<sprawa>\`, potem `.\start.bat`. Wyniki są w `output\<sprawa>\`. Przy pierwszym
  uruchomieniu skrypt sam tworzy środowisko (Python 3.13 lub 3.14).
- **GUI:** `.\start-gui.bat`, potem http://127.0.0.1:8000.
- **Docker:** `docker compose up --build` (GUI) albo `docker compose run --rm app python -m odw2json run` (wsad).
  Plik `.env` jest opcjonalny.

## Najważniejsze
- **Jakość (F1 wg reguł UZP):** razem 0,998 dev / 0,994 holdout; dokumenty z tekstem 0,999 / 0,997, skany z OCR
  0,992 / 0,967, klasyfikacja bez błędów, dokumenty spoza typów rozpoznane 15/15 (dev) i 13/13 (holdout), w tym skany.
  Szczegóły: [raport-jakosci.md](raport-jakosci.md).
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
[README](../README.md), [RUN.md](../RUN.md) (komenda dla jury), [architektura.md](architektura.md),
[nowy-typ-dokumentu.md](nowy-typ-dokumentu.md), [gui.md](gui.md), [raport-jakosci.md](raport-jakosci.md),
[vm-jury.md](vm-jury.md), [zgloszenie.md](zgloszenie.md) (zgodność z regulaminem i licencje),
[kryteria-uzp.md](kryteria-uzp.md), `docs/decyzje/`.

## Znane ograniczenia
- Na Pythonie 3.15+ OCR skanów jest niedostępny (brak paczek `onnxruntime`), a skan dostaje ostrzeżenie. Pełny wynik
  daje Python 3.13 lub 3.14 albo Docker.
- Skan OCR trwa ok. 2 s na stronę na CPU: 3–8 s na skan na laptopie, średnio ok. 12 s na VM UZP z 2 vCPU
  ([decyzje/E11-wydajnosc.md](decyzje/E11-wydajnosc.md), [vm-jury.md](vm-jury.md)).
- Spacje w numerze rachunku: UZP nie rozstrzygnęło wprost; zapisujemy bez spacji, z „PL”, gdy jest w dokumencie (kryteria, pkt 5a).
