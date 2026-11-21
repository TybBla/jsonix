@echo off
rem Przygotowuje interpreter Pythona dla jsonix i ustawia zmienna JSONIX_PY (wolane przez start.bat i start-gui.bat).
rem Kolejnosc:
rem   1. "python" z PATH, jesli to Python 3.13+ i ma juz zainstalowane zaleznosci (np. aktywny venv, CI),
rem   2. srodowisko .venv w katalogu repo (albo JSONIX_VENV), jesli ma zaleznosci,
rem   3. nowe .venv na Pythonie 3.13 lub 3.14 (launcher "py"), potem dowolny Python 3.13+,
rem      i instalacja requirements.txt.
rem OCR skanow (rapidocr + onnxruntime) ma paczki dla Pythona 3.13 i 3.14. Na nowszym Pythonie aplikacja dziala,
rem ale skany bez warstwy tekstowej nie zostana odczytane (ostrzezenie ponizej i w wynikach).

set "JSONIX_PY="
set "JSONIX_ROOT=%~dp0.."
if not defined JSONIX_VENV set "JSONIX_VENV=%JSONIX_ROOT%\.venv"
set "JSONIX_DEPS=import fastapi, pypdfium2, yaml, rapidfuzz, uvicorn"

rem --- 1. gotowe srodowisko w PATH ---
call :usable python
if defined JSONIX_PY goto :ready

rem --- 2. istniejace .venv ---
if exist "%JSONIX_VENV%\Scripts\python.exe" call :usable "%JSONIX_VENV%\Scripts\python.exe"
if defined JSONIX_PY goto :ready

rem --- 3. nowe .venv ---
set "JSONIX_BASE="
for %%V in (3.13 3.14) do if not defined JSONIX_BASE call :version_ok py -%%V
if not defined JSONIX_BASE call :version_ok python
if not defined JSONIX_BASE call :version_ok py -3
if not defined JSONIX_BASE (
  echo.
  echo [jsonix] Nie znaleziono Pythona 3.13 lub nowszego.
  echo [jsonix] Zainstaluj Python 3.13 albo 3.14 ze strony https://www.python.org/downloads/
  echo [jsonix] i zaznacz "Add python.exe to PATH". Potem uruchom ten plik ponownie.
  exit /b 1
)
echo [jsonix] Tworze srodowisko w "%JSONIX_VENV%" (jednorazowo, kilka minut)...
%JSONIX_BASE% -m venv "%JSONIX_VENV%" || (echo [jsonix] Nie udalo sie utworzyc srodowiska .venv. & exit /b 1)
"%JSONIX_VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "%JSONIX_ROOT%\requirements.txt" -c "%JSONIX_ROOT%\requirements-lock.txt"
if errorlevel 1 (
  echo [jsonix] Instalacja zaleznosci nie powiodla sie. Sprawdz polaczenie z internetem i uruchom ponownie.
  exit /b 1
)
set "JSONIX_PY=%JSONIX_VENV%\Scripts\python.exe"

:ready
"%JSONIX_PY%" -c "import sys; sys.exit(0 if sys.version_info[:2] < (3, 15) else 1)" 2>nul
if errorlevel 1 (
  echo [jsonix] UWAGA: Python nowszy niz 3.14 - OCR skanow jest niedostepny ^(brak paczek onnxruntime^).
  echo [jsonix] Dokumenty z warstwa tekstowa beda przetworzone; do skanow zainstaluj Python 3.13 lub 3.14.
)
exit /b 0

rem --- podprogramy ---
:version_ok
rem Ustawia JSONIX_BASE, gdy polecenie %* to Python 3.13+.
%* -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 13) else 1)" >nul 2>nul
if not errorlevel 1 set "JSONIX_BASE=%*"
exit /b 0

:usable
rem Ustawia JSONIX_PY, gdy %1 to Python 3.13+ z zainstalowanymi zaleznosciami jsonix.
%1 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 13) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
%1 -c "%JSONIX_DEPS%" >nul 2>nul
if errorlevel 1 exit /b 0
set "JSONIX_PY=%~1"
exit /b 0
