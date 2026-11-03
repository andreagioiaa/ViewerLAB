@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [VistoFlow] Creo l'ambiente virtuale in .venv...
    python -m venv .venv
    if errorlevel 1 goto :error
)

"%VENV_PY%" -c "import PyQt6, vlc, httpx, pydantic, bs4, yaml, tenacity, dotenv, lxml.etree, certifi" >nul 2>&1
if errorlevel 1 (
    echo [VistoFlow] Installo le dipendenze...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 goto :error
)

"%VENV_PY%" main.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo [VistoFlow] Avvio non riuscito.
echo Controlla i messaggi sopra oppure esegui setup.bat.
pause
exit /b 1
