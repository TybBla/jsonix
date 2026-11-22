@echo off
rem Uruchamia jsonix: API + GUI (http://127.0.0.1:8000) i otwiera przegladarke.
rem Przy pierwszym uruchomieniu tworzy .venv i instaluje zaleznosci (scripts\setup-env.bat).
cd /d "%~dp0"
set PORT=8000
if not "%~1"=="" set PORT=%~1
call "%~dp0scripts\setup-env.bat" || exit /b 1
echo jsonix - uruchamianie GUI na http://127.0.0.1:%PORT%/
echo Przegladarka otworzy sie za kilka sekund. Zamknij to okno (Ctrl+C), aby zatrzymac jsonix.
rem ping zamiast timeout: timeout nie dziala bez interaktywnej konsoli (np. uruchomienie z innego programu)
start "" /b cmd /c "ping -n 4 127.0.0.1 >nul & start "" http://127.0.0.1:%PORT%/"
"%JSONIX_PY%" -m odw2json serve --port %PORT%
if errorlevel 1 echo jsonix - serwer zakonczyl sie bledem. Uruchom start-gui.bat ponownie albo zobacz README (sekcja Instalacja).
