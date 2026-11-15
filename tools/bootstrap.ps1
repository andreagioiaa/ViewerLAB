# VistoFlow - prepara l'ambiente e avvia l'app su Windows 10/11.
# Richiamato da run.bat, run.ps1 e setup.bat. Funziona con Windows PowerShell 5.1.
#
#   -SetupOnly   prepara tutto senza avviare l'app (setup.bat)
#   -Console     avvia con python.exe e la console visibile (per vedere gli errori)
#   -Yes         risponde "si" a ogni proposta di installazione (winget)
#   altri argomenti: passati a main.py
param(
    [switch]$SetupOnly,
    [switch]$Console,
    [switch]$Yes,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$AppArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

# Versione testata: le librerie in constraints.txt sono bloccate per questa.
# Python 3.15 in particolare rompe alcune dipendenze ("'lazy_import' object is not callable").
$PyVersion = "3.14"

function Say([string]$Text) { Write-Host "[VistoFlow] $Text" }

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "[VistoFlow] $Text" -ForegroundColor Red
    exit 1
}

function Ask([string]$Question) {
    if ($Yes) { return $true }
    $answer = Read-Host "[VistoFlow] $Question [S/n]"
    return ($answer -eq "" -or $answer -match "^[sSyY]")
}

function Has-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }

function Winget-Install([string]$Id, [string]$Name, [string[]]$Extra = @()) {
    if (-not (Has-Winget)) {
        Say "winget non e' disponibile: installa $Name a mano."
        return $false
    }
    Say "Installo $Name con winget..."
    & winget install --id $Id -e --accept-source-agreements --accept-package-agreements --disable-interactivity @Extra
    return ($LASTEXITCODE -eq 0)
}

function Python-Version([string]$Exe) {
    try {
        $out = & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0) { return ($out | Select-Object -First 1).Trim() }
    } catch { }
    return ""
}

function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $exe = & py "-$PyVersion" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { $candidates += ($exe | Select-Object -First 1).Trim() }
        } catch { }
    }
    $tag = $PyVersion -replace "\.", ""
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$tag\python.exe"),
        (Join-Path $env:ProgramFiles "Python$tag\python.exe")
    )
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    foreach ($exe in $candidates) {
        # WindowsApps\python.exe e' solo il collegamento allo Store: lo salta.
        if ($exe -and (Test-Path -LiteralPath $exe) -and $exe -notmatch "WindowsApps") {
            if ((Python-Version $exe) -eq $PyVersion) { return $exe }
        }
    }
    return $null
}

function Find-Vlc {
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base "VideoLAN\VLC\libvlc.dll"))) { return $true }
    }
    return $false
}

# PySide6 contiene file con percorsi di ~165 caratteri sotto site-packages: con il
# progetto in una cartella profonda si supera il limite di 260 di Windows e pip
# fallisce. In quel caso l'ambiente va nella cartella dati, dal percorso corto.
$DataDir = if ($env:VISTOFLOW_DATA) { $env:VISTOFLOW_DATA } else { Join-Path $env:LOCALAPPDATA "VistoFlow" }
if ($Root.Length -le 70) {
    $Venv = Join-Path $Root ".venv"
} else {
    $Venv = Join-Path $DataDir "venv"
    if ((Join-Path $Venv "x").Length -gt 75) { Fail "Percorso troppo lungo per Python: sposta il progetto in una cartella piu' corta (es. C:\VistoFlow)." }
}
$VenvPy = Join-Path $Venv "Scripts\python.exe"
$VenvPyw = Join-Path $Venv "Scripts\pythonw.exe"
$Stamp = Join-Path $Venv ".vistoflow-deps"

# --- 1. Python 3.14 -----------------------------------------------------------
$Python = Find-Python
if (-not $Python) {
    Say "Serve Python $PyVersion (64 bit) e non l'ho trovato."
    if ((Ask "Lo installo adesso con winget (solo per il tuo utente)?") -and
        (Winget-Install "Python.Python.$PyVersion" "Python $PyVersion" @("--scope", "user"))) {
        $Python = Find-Python
    }
    if (-not $Python) {
        Fail "Installa Python $PyVersion da https://www.python.org/downloads/ e rilancia."
    }
}

# --- 2. Ambiente virtuale con la versione giusta ------------------------------
if ((Test-Path -LiteralPath $VenvPy) -and ((Python-Version $VenvPy) -ne $PyVersion)) {
    Say "Il .venv esistente usa un'altra versione di Python: lo ricreo con $PyVersion."
    Remove-Item -LiteralPath $Venv -Recurse -Force
}
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Say "Creo l'ambiente virtuale in .venv con $Python ..."
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Fail "Creazione di .venv non riuscita." }
}

# --- 3. Dipendenze, alle versioni testate -------------------------------------
# Reinstalla solo quando requirements.txt o constraints.txt cambiano.
$wanted = ((Get-FileHash requirements.txt).Hash + (Get-FileHash constraints.txt).Hash)
$have = if (Test-Path -LiteralPath $Stamp) { (Get-Content -LiteralPath $Stamp -Raw).Trim() } else { "" }
if ($have -ne $wanted) {
    Say "Installo le dipendenze (la prima volta servono alcuni minuti)..."
    & $VenvPy -m pip install --disable-pip-version-check -q -r requirements.txt -c constraints.txt
    if ($LASTEXITCODE -ne 0) { Fail "Installazione delle dipendenze non riuscita (serve internet)." }
    Set-Content -LiteralPath $Stamp -Value $wanted -Encoding ASCII
}

# --- 4. VLC (obbligatorio) e mpv (consigliato) --------------------------------
if (-not (Find-Vlc)) {
    Say "VLC non e' installato: serve per il player della Libreria."
    if ((Ask "Lo installo adesso con winget?") -and (Winget-Install "VideoLAN.VLC" "VLC")) { }
    if (-not (Find-Vlc)) { Fail "Installa VLC 64 bit da https://www.videolan.org/ e rilancia." }
}
$mpv = ""
try { $mpv = & $VenvPy -c "from vistoflow.player import resolve_mpv; print(resolve_mpv() or '')" 2>$null } catch { }
if (-not $mpv) {
    Say "mpv non e' installato: serve per il Player delle fonti online (Guarda usa VLC se manca)."
    if (Ask "Lo installo adesso con winget?") { [void](Winget-Install "shinchiro.mpv" "mpv") }
}

if ($SetupOnly) {
    Say "Ambiente pronto. Avvia VistoFlow con run.bat."
    exit 0
}

# --- 5. Avvio -----------------------------------------------------------------
if ($Console) {
    & $VenvPy main.py @AppArgs
    exit $LASTEXITCODE
}
# Senza console. Se l'app si chiude subito, mostra l'errore invece di sparire.
$started = Get-Date
$argList = @("main.py")
if ($AppArgs) { $argList += $AppArgs }
$app = Start-Process -FilePath $VenvPyw -ArgumentList $argList -WorkingDirectory $Root -PassThru
if (-not $app.WaitForExit(8000)) { exit 0 }
if ($app.ExitCode -eq 0) { exit 0 }
Say "VistoFlow si e' chiuso con un errore (codice $($app.ExitCode))."
$log = Join-Path $env:LOCALAPPDATA "VistoFlow\vistoflow.log"
if ((Test-Path -LiteralPath $log) -and ((Get-Item -LiteralPath $log).LastWriteTime -ge $started)) {
    Say "Ultime righe di $log :"
    Get-Content -LiteralPath $log -Tail 25
}
Say "Per vedere l'errore completo: run.bat -Console"
exit 1
