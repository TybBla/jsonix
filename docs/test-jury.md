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

# Powtórka na Pythonie 3.13 i 3.14 (22.11.2026, kod `main` v0.4.0)

Cel (plan do v1.0, pkt 14): to samo, co zrobi jury, na obu zalecanych wersjach Pythona, z OCR skanów.

## Warunki
- Windows 11, Python 3.13.17 i 3.14.10 z python.org (instalacja dla użytkownika), Docker Desktop.
- Dwa świeże klony `main` w folderze ze spacją i polskimi znakami: `%TEMP%\test jury ąę\jsonix313` i `…\jsonix314`. Brak `.venv` i `.env`.
- Dwa warianty instalacji Pythona, żeby sprawdzić obie gałęzie wyszukiwania w `setup-env.bat`:
  - **3.13:** tylko launcher `py` (bez `python` w `PATH`), jak domyślna instalacja z python.org;
  - **3.14:** tylko `python` w `PATH` (opcja „Add python.exe to PATH”), bez launchera.
- Dane w `input\sprawa1\`: 3 dokumenty z `przyklad_01` (tekst) + skan odwołania i skan potwierdzenia przelewu z `data/train/skany` (OCR).

## Wyniki

| Krok | Python 3.13 | Python 3.14 |
|---|---|---|
| `start.bat`, pierwsze uruchomienie (tworzenie `.venv`, instalacja paczek z OCR, przetwarzanie) | ✅ exit 0, 166 s | ✅ exit 0, 138 s |
| w tym samo przetwarzanie 5 PDF (OCR 2 skanów) | 36,6 s | 36,8 s |
| `start.bat`, drugie uruchomienie (gotowe `.venv`, cache OCR) | ✅ exit 0, 5 s | ✅ exit 0, 4 s |
| typy | 2 odwołania, 1 pełnomocnictwo, 2 przelewy, 0 błędów | to samo |
| ostrzeżenie o braku OCR | brak (OCR działa) | brak (OCR działa) |

- Wyniki JSON z obu wersji Pythona są **identyczne** bajt w bajt (`diff -r`).
- Skan potwierdzenia przelewu odczytany przez OCR: data, kwota, oba rachunki i numer transakcji wypełnione.

## Docker
`python scripts/smoke_docker.py --port 8798` w świeżym klonie (budowa obrazu, `docker compose up`, healthcheck, GUI/API, wsad w kontenerze ze skanem OCR, porównanie z CLI na hoście na Pythonie 3.13): ✅ exit 0, `SMOKE DOCKER OK: healthy, GUI/API, wsad w kontenerze (w tym skan OCR) = CLI na hoście`.

## Uwagi
- Uruchamianie `start.bat` z innego programu (nie z Eksploratora ani z konsoli): jeśli w środowisku jest ustawiona zmienna `NoDefaultCurrentDirectoryInExePath`, `cmd /c start.bat` nie znajdzie pliku w bieżącym katalogu. Ręczne uruchomienie (dwuklik, `.\start.bat` w PowerShellu, `start.bat` w `cmd.exe`) tego nie dotyczy. Pełna ścieżka do `start.bat` działa zawsze.
- Czas pierwszego uruchomienia to głównie instalacja paczek (ok. 100–130 s, wymaga internetu); samo przetwarzanie skanów to ok. 15–20 s na wielostronicowy skan odwołania (szczegóły: `docs/decyzje/E11-wydajnosc.md`).
