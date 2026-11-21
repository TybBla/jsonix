@echo off
rem jsonix - wsad: python -m odw2json run [input] [output] (domyslnie input\ i output\).
rem Przy pierwszym uruchomieniu tworzy .venv i instaluje zaleznosci (scripts\setup-env.bat).
cd /d "%~dp0"
call "%~dp0scripts\setup-env.bat" || exit /b 1
"%JSONIX_PY%" -m odw2json run %*
