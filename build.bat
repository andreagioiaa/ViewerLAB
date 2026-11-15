@echo off
rem Doppio clic: crea dist\ViewerLAB\ViewerLAB.exe e, se WiX e' installato,
rem anche l'installer dist\ViewerLAB-<versione>.msi.
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\ViewerLAB\venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Ambiente non pronto: esegui prima setup.bat
    pause
    exit /b 1
)

"%PY%" -m pip install --quiet pyinstaller -c constraints.txt || goto :failed

set "MSI="
where wix >nul 2>nul && set "MSI=--msi"
if not defined MSI (
    echo WiX non trovato: creo solo l'exe. Per il .msi installa una volta:
    echo   winget install Microsoft.DotNet.SDK.8
    echo   dotnet tool install --global wix --version 5.0.2
    echo.
)

"%PY%" build_exe.py --clean %MSI% || goto :failed
echo.
echo Fatto: i file sono nella cartella dist\
explorer dist
pause
exit /b 0

:failed
echo.
echo Build non riuscita: leggi gli errori qui sopra.
pause
exit /b 1
