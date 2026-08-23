# Provision the Exness Windows VPS as an always-on MT5 execution node.
# Research/backtest/validation remain on the Linux VPS.
# This installer never enables trading; the Linux manifest is fail-closed.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = "C:\XAUUSD-MT5-Bridge"
$RepoZip = "https://codeload.github.com/fredrick-m/XAUUSD-SCALPER-X10/zip/refs/heads/audit/x10-500"
$VpsHost = "85.155.191.35"
$VpsHostKey = "SHA256:emxiskNA3d1bKVbhZO+IwRDzFiPB2YHVtVQ6mJUk1so"
$TaskName = "XAUUSD-MT5-Bridge-H24"

function Resolve-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try { & py -3.11 --version | Out-Null; return @("py", "-3.11") } catch {}
        try { & py -3 --version | Out-Null; return @("py", "-3") } catch {}
    }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @("python") }
    return $null
}

function Install-Python311 {
    $installer = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
    Write-Host "Python not found; installing Python 3.11..." -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $installer
    $p = Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Python installer failed with exit code $($p.ExitCode)" }
}

Write-Host "=== XAUUSD MT5 H24 CLOUD NODE ===" -ForegroundColor Cyan
Write-Host "Linux VPS remains the research/validation source of truth."
Write-Host "This Windows VPS is execution-only and DEMO-only."

$py = Resolve-Python
if (-not $py) {
    Install-Python311
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $py = Resolve-Python
    if (-not $py) { throw "Python installation completed but Python is still unavailable." }
}

$pythonExe = $py[0]
$pythonArgs = @()
if ($py.Count -gt 1) { $pythonArgs = $py[1..($py.Count - 1)] }
& $pythonExe @pythonArgs --version

Write-Host "Downloading audited branch..." -ForegroundColor Cyan
$tmpZip = Join-Path $env:TEMP "xauusd-audit-x10-500.zip"
$tmpExtract = Join-Path $env:TEMP "xauusd-audit-x10-500"
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue
Invoke-WebRequest -UseBasicParsing -Uri $RepoZip -OutFile $tmpZip
Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force
$sourceRoot = Get-ChildItem $tmpExtract -Directory | Select-Object -First 1
if (-not $sourceRoot) { throw "Repository archive could not be expanded." }
New-Item -ItemType Directory -Path $ProjectDir -Force | Out-Null
Copy-Item (Join-Path $sourceRoot.FullName "*") $ProjectDir -Recurse -Force

Set-Location $ProjectDir
$venv = Join-Path $ProjectDir ".venv"
if (-not (Test-Path $venv)) {
    & $pythonExe @pythonArgs -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $venvPython)) { throw "Virtualenv Python missing: $venvPython" }
& $venvPython -m pip install --upgrade pip wheel setuptools
& $venvPython -m pip install -r (Join-Path $ProjectDir "requirements-windows-bridge.txt")

Write-Host "Initializing bridge identity and binding current MT5 DEMO account..." -ForegroundColor Cyan
$initOutput = & $venvPython -m scripts.windows_mt5_bridge init --vps-host $VpsHost --host-key $VpsHostKey 2>&1
$initOutput | ForEach-Object { Write-Host $_ }

$runner = Join-Path $ProjectDir "run_bridge.cmd"
$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$runnerContent = @"
@echo off
cd /d "$ProjectDir"
"$venvPython" -m scripts.windows_mt5_bridge run >> "$logDir\windows_bridge.log" 2>&1
"@
Set-Content -Path $runner -Value $runnerContent -Encoding ASCII

Write-Host "Creating H24 scheduled task with automatic restart..." -ForegroundColor Cyan
Write-Host "Windows will ask for the password of THIS VPS user locally. Do not send that password anywhere." -ForegroundColor Yellow
$cred = Get-Credential -UserName "$env:USERDOMAIN\$env:USERNAME" -Message "Enter the Windows VPS account password for unattended H24 restart"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $action = New-ScheduledTaskAction -Execute $runner -WorkingDirectory $ProjectDir
    $startup = New-ScheduledTaskTrigger -AtStartup
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $cred.UserName
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($startup, $logon) -Settings $settings -User $cred.UserName -Password $plainPassword -RunLevel Highest -Force | Out-Null
} finally {
    if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    $plainPassword = $null
}

Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host ""
Write-Host "Task state: $($task.State)" -ForegroundColor Green
Write-Host "Last task result: $($info.LastTaskResult)"
Write-Host "Log: $logDir\windows_bridge.log"
Write-Host ""
Write-Host "IMPORTANT: copy ONLY the public key line printed above (ssh-rsa ... xauusd-mt5-bridge)." -ForegroundColor Yellow
Write-Host "The bridge will remain fail-closed until that public key is authorized on the Linux VPS."
Write-Host "No trading was enabled by this installer."
