@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [VistoFlow] Creo l'ambiente virtuale in .venv...
    python -m venv .venv
    if errorlevel 1 goto :error
)

echo [VistoFlow] Aggiorno pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

echo [VistoFlow] Installo le dipendenze...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [VistoFlow] Installo gli strumenti di sviluppo opzionali...
".venv\Scripts\python.exe" -m pip install "pytest>=8.2" "pytest-asyncio>=0.23" "respx>=0.21" "ruff>=0.5"

echo.
echo [VistoFlow] Ambiente pronto. Avvia con run.bat oppure run.ps1.
echo Non serve attivare l'ambiente: i launcher usano direttamente .venv\Scripts\python.exe
pause
exit /b 0

:error
echo.
echo [VistoFlow] Setup non riuscito.
pause
exit /b 1
