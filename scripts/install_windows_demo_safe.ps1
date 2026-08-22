# Safe Windows provisioning for the future MT5 DEMO execution node.
# This script installs dependencies and runs readiness checks only.
# It NEVER enables demo execution and NEVER sends an order.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if ($env:OS -ne "Windows_NT") {
    throw "This installer must run on Windows."
}

function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) { return @("py", "-3") }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    throw "Python 3 is required. Install Python 3.11+ and re-run this script."
}

$py = Resolve-Python
$pythonExe = $py[0]
$pythonArgs = @()
if ($py.Count -gt 1) { $pythonArgs = $py[1..($py.Count-1)] }

& $pythonExe @pythonArgs --version

$venv = Join-Path $projectRoot ".venv"
if (-not (Test-Path $venv)) {
    & $pythonExe @pythonArgs -m venv $venv
}

$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { throw "Virtualenv Python not found: $venvPython" }

& $venvPython -m pip install --upgrade pip wheel setuptools
& $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")

Write-Host ""
Write-Host "Reserving safe runtime strategy ID floors..." -ForegroundColor Cyan
& $venvPython -m scripts.ensure_strategy_id_floor

Write-Host ""
Write-Host "Installing backtest metric-version guard..." -ForegroundColor Cyan
& $venvPython -m scripts.ensure_backtest_metric_guard

Write-Host ""
Write-Host "Invalidating evidence whose strategy source changed..." -ForegroundColor Cyan
& $venvPython -m scripts.invalidate_changed_strategy_evidence

Write-Host ""
Write-Host "Forcing execution master switch OFF..." -ForegroundColor Yellow
& $venvPython -m scripts.demo_switch disable
if ($LASTEXITCODE -ne 0) {
    Write-Warning "demo_switch disable returned $LASTEXITCODE; the preflight below remains fail-closed."
}

Write-Host ""
Write-Host "Checking official MetaTrader5 Python package..." -ForegroundColor Cyan
& $venvPython -c "import MetaTrader5 as mt5; print('MetaTrader5 package:', mt5.__version__)"

Write-Host ""
Write-Host "Running DEMO preflight (no order is sent)..." -ForegroundColor Cyan
& $venvPython -m scripts.demo_preflight
$preflightCode = $LASTEXITCODE

Write-Host ""
if ($preflightCode -eq 0) {
    Write-Host "Preflight READY. Execution is STILL OFF." -ForegroundColor Green
    Write-Host "Do not enable it unless a human explicitly decides to proceed with the DEMO account."
} elseif ($preflightCode -eq 2) {
    Write-Host "Preflight BLOCKED as designed. Execution remains OFF." -ForegroundColor Yellow
    Write-Host "Install/open MetaTrader 5, sign into a DEMO account only, enable Algo Trading, and rerun this script/preflight."
} else {
    throw "Preflight failed unexpectedly with exit code $preflightCode"
}

Write-Host ""
Write-Host "Safety status: no order sent; demo execution not enabled."
exit 0
