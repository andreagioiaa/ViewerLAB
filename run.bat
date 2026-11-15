@echo off
rem Avvia VistoFlow: prepara Python 3.14, .venv, dipendenze, VLC e mpv se mancano.
rem   run.bat -Console   mostra la console con gli errori
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" %*
if errorlevel 1 pause
