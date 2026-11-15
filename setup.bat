@echo off
rem Prepara l'ambiente di VistoFlow senza avviarlo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -SetupOnly %*
pause
