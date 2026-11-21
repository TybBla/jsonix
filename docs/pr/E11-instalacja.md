## E11: instalacja odporna na najnowszego Pythona, `start.bat` przygotowuje środowisko

Gałąź `etap/E11-instalacja` → `main`. **Zbudowana na `etap/E11-docker`**: scal najpierw E11-docker, wtedy ten PR pokaże tylko własne zmiany.

### Problem
Wymóg UZP to „Python 3.13+”, a aktualny Python to 3.15. Dla 3.15 paczki `onnxruntime` i `pyclipper` (zależność `rapidocr`) **nie istnieją na PyPI**, więc `pip install -r requirements.txt` kończył się błędem i **cała aplikacja się nie instalowała**. Na maszynie jury z najnowszym Pythonem oznaczałoby to F1 = 0. Do tego `start.bat` wołał gołe `python`: nie sprawdzał wersji i nie instalował zależności.

### Zmiany
- **`scripts/setup-env.bat`** (wołany przez `start.bat` i `start-gui.bat`). Kolejność:
  1. `python` z `PATH`, jeśli to 3.13+ z zainstalowanymi zależnościami (aktywny venv, CI, ręczna instalacja);
  2. istniejące `.venv` w repo;
  3. nowe `.venv` na **3.13 albo 3.14** (launcher `py`), potem dowolny Python 3.13+, i instalacja `requirements.txt`.
  - Brak Pythona 3.13+ kończy się czytelnym komunikatem z linkiem i exit 1.
  - Na 3.15+ jest ostrzeżenie, że OCR skanów jest niedostępny.
- **`requirements.txt`**: `rapidocr` i `onnxruntime` dostały znacznik `; python_version < "3.15"`. ⚠️ **Do uzgodnienia z właścicielem OCR (E2b, etap kolegi).** Zmieniam tylko te dwie linie i komentarz. Na 3.13 i 3.14 nic się nie zmienia, a na 3.15 aplikacja się instaluje, przetwarza dokumenty z tekstem, a skan dostaje ostrzeżenie „brak OCR” (zachowanie `ingest/ocr.py` bez pakietu).
- **`start.sh`**: wybiera Pythona 3.13+ (najpierw `python3.13` i `python3.14`), a dla 3.15+ wypisuje ostrzeżenie.
- **CI**: macierz Pythona `3.13` i `3.14` (testy i smoke).
- **README**: szybki start przez `start.bat`, zalecana wersja Pythona i instalacja ręczna.
- **`requirements-lock.txt`** (punkt 5 z listy luk): przypięte wersje jako plik ograniczeń pip (`-c`), żeby nowe wydanie biblioteki w dniu oceny niczego nie zepsuło. `requirements.txt` dalej mówi, *co* instalujemy, a lock, *które wersje*. Lock wygenerowałem z działającego obrazu (3.13). Używają go `Dockerfile`, `setup-env.bat`, CI i oba smoke. Sprawdzone na 3.13 (obraz, `smoke_docker` OK), 3.14 (kontener) i 3.15 (Windows).
- **`tests/test_install.py`** sprawdza znaczniki OCR, skrypty startowe, CRLF w `.bat`, `start.sh` i macierz CI oraz to, że każda zależność ma wersję w locku i lock jest używany wszędzie, gdzie instalujemy.

### Sprawdzone
- **Windows, tylko Python 3.15, świeże `.venv`** (`start.bat` z `JSONIX_VENV` w katalogu tymczasowym): instalacja OK (70 s), 3 PDF z tekstem przetworzone, skan → `{}` z ostrzeżeniem.
- **Ponowne uruchomienie:** używa istniejącego `.venv`, bez instalacji (2 s).
- **`python` z zależnościami w `PATH`** (jak `scripts/smoke.ps1` w CI): nie tworzy `.venv`.
- **Brak Pythona 3.13+:** komunikat po polsku i exit 1.
- **Python 3.14 w kontenerze `python:3.14-slim`:** `pip install -r requirements.txt` OK, skan rozpoznany przez OCR (`przelew`, `ocr_used=True`).
- **`python scripts/smoke_docker.py`:** exit 0 (obraz na 3.13 nadal z OCR).
- **Bramka:**
  - `ruff`: czysto. `smoke_gui.py` i `eval.gate --split dev --source tekst`: exit 0.
  - `pytest` lokalnie (3.15): exit 1 przez 5 testów OCR, jak na `main`. Te testy powinny się pomijać, gdy pakiet OCR jest niedostępny (`pytest.importorskip("rapidocr")`), ale to pliki etapów E2b/E3, więc tylko to sygnalizuję.
