@echo off
rem Uruchamia jsonix: API + GUI (http://127.0.0.1:8000) i otwiera przegladarke.
cd /d "%~dp0"
set PORT=8000
if not "%~1"=="" set PORT=%~1
echo jsonix - uruchamianie GUI na http://127.0.0.1:%PORT%/
echo Przegladarka otworzy sie za kilka sekund. Zamknij to okno (Ctrl+C), aby zatrzymac jsonix.
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:%PORT%/"
python -m odw2json serve --port %PORT%
if errorlevel 1 echo jsonix - serwer zakonczyl sie bledem. Sprawdz, czy zainstalowano zaleznosci: pip install -r requirements.txt
