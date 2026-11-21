@echo off
rem Uruchamia API + GUI (http://127.0.0.1:8000) i otwiera przegladarke.
cd /d "%~dp0"
set PORT=8000
if not "%~1"=="" set PORT=%~1
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:%PORT%/"
python -m odw2json serve --port %PORT%
