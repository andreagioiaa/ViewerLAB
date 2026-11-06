$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python -m viewerlab @args
exit $LASTEXITCODE
