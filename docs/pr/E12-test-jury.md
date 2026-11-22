## Test „jak u jury” na Pythonie 3.13 i 3.14 (plan do v1.0, pkt 14)

Tylko dokumentacja: nowa sekcja w `docs/test-jury.md`.

- Świeże klony `main` (v0.4.0) w folderze ze spacją i polskimi znakami, bez `.venv` i `.env`.
- `start.bat` na Pythonie 3.13 (tylko launcher `py`) i 3.14 (tylko `python` w `PATH`): exit 0 za pierwszym i drugim razem, OCR skanów działa, wyniki z obu wersji identyczne.
- `scripts/smoke_docker.py`: exit 0 (compose, healthcheck, GUI/API, wsad z OCR = CLI na hoście).
- Bez zmian w kodzie: nic nie wymagało poprawki.

### Bramka
Zmiany tylko w `docs/`. `ruff`: czysto.
