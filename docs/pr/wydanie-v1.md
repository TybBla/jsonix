## Szkic CHANGELOG v1.0.0 i notatek wydania

Gałąź `etap/wydanie-v1` → `main`. **Dla właściciela repo przy wydaniu.** Scal na końcu, po pozostałych PR-ach.

- **`CHANGELOG.md`:** szkic sekcji v1.0.0 pogrupowanej według etapów (E4–E12, GUI, dane), z odwołaniem do gałęzi każdej zmiany i tabelą bramki (pomiar 21.11 na gałęzi E4).
- **`docs/wydanie-v1.0.md`:** tekst do GitHub Release (uruchomienie, najważniejsze, dokumentacja, znane ograniczenia). Miejsca ⟨…⟩ czekają na liczby po scaleniu E4 i na odpowiedź UZP o spacje.

Przy wydaniu:
1. Popraw listę według faktycznie scalonych PR-ów.
2. Wygeneruj `docs/raport-jakosci.md` (`python scripts/quality_report.py` na maszynie z OCR) i przepisz liczby.
3. Usuń notkę „SZKIC”, otaguj `v1.0.0` i wklej `docs/wydanie-v1.0.md` do GitHub Release.
