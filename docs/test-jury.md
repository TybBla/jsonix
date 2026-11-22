# „Test jury” — świeży klon i instalacja według README (22.11.2026)

Cel: sprawdzić krok po kroku, czy osoba bez wiedzy o projekcie uruchomi go z README na czystym Windowsie.

## Warunki
- Windows 11, **tylko Python 3.15** (najnowszy; brak 3.13/3.14) i Docker Desktop.
- Świeży `git clone` gałęzi z instalatorem do folderu ze spacją i polskimi znakami: `%TEMP%\test jury ąę\jsonix`.
- Brak `.venv` i brak `.env`.

## Przebieg i wyniki

| Krok wg README | Wynik |
|---|---|
| Dokumenty do `input\sprawa1\` (3 typy z `przyklad_01` i postanowienie KIO spoza typów) | ok |
| `start.bat` w PowerShellu | ❌ „not recognized” — **PowerShell wymaga `.\start.bat`**. Poprawione w README (`.\start.bat`, `.\start-gui.bat` i uwaga o `cmd.exe`) |
| `.\start.bat` | ✅ exit 0, 67 s (w tym jednorazowa instalacja `.venv`): 4 pliki JSON, postanowienie KIO → `{}`. Ostrzeżenie o OCR na Pythonie 3.15 |
| komunikat o tworzeniu `.venv` | ścieżka `…\scripts\..\.venv` — poprawione na pełną ścieżkę |
| `.\start-gui.bat` | ✅ GUI i API działają. `timeout` w skrypcie zgłasza błąd bez interaktywnej konsoli — zamienione na `ping` |
| `docker compose up --build` (bez `.env`) | ✅ `healthy`, GUI pod adresem z `JSONIX_PORT` |
| `docker compose run --rm app python -m odw2json run` | ✅ 4 pliki JSON w `output\sprawa1\` |

## Wnioski dodane do README
- Sekcja **Wymagania**: Windows 10/11, **Python 3.13 lub 3.14** (z „Add python.exe to PATH”), internet przy pierwszym uruchomieniu, albo Docker Desktop.
- Kroki 1–2–3: gdzie położyć PDF-y, co uruchomić, gdzie są wyniki.
- Na Pythonie 3.15 wszystko działa poza OCR skanów: skan bez tekstu dostaje ostrzeżenie. Do pełnego wyniku potrzebny jest Python 3.13/3.14 albo Docker.

## Czego nie sprawdzono
- Komputer bez żadnego Pythona i bez Dockera: tę ścieżkę pokrywa komunikat `setup-env.bat` z linkiem do python.org (sprawdzony wcześniej przy pustym `PATH`).
- Pełny test na Pythonie 3.13 bez Dockera. Ten sam zestaw paczek działa w obrazie (3.13) i w `python:3.14-slim`.
