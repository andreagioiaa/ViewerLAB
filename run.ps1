# Avvia VistoFlow Pro senza attivare manualmente l'ambiente virtuale.
# Esecuzione consigliata:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[VistoFlow] Creo l'ambiente virtuale in .venv..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Creazione dell'ambiente virtuale non riuscita." }
}

& $python -c "import PyQt6, vlc, httpx, pydantic, bs4, yaml, tenacity, dotenv, lxml.etree, certifi" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[VistoFlow] Installo le dipendenze..."
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Installazione delle dipendenze non riuscita." }
}

& $python (Join-Path $PSScriptRoot "main.py")
exit $LASTEXITCODE
