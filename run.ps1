# Avvia VistoFlow (vedi tools\bootstrap.ps1). Uso:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1 [-Console]
& (Join-Path $PSScriptRoot "tools\bootstrap.ps1") @args
exit $LASTEXITCODE
