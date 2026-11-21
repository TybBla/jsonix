@echo off
cd /d "%~dp0"
python -m odw2json run %*
