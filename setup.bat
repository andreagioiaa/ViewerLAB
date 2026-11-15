@echo off
rem Prepara l'ambiente di ViewerLAB senza avviarlo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -SetupOnly %*
pause
