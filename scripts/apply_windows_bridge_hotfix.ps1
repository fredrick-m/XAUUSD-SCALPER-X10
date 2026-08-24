$ErrorActionPreference = 'Stop'
$ProjectDir = 'C:\XAUUSD-MT5-Bridge'
$TaskName = 'XAUUSD-MT5-Bridge-H24'
$HotfixUrl = 'https://raw.githubusercontent.com/fredrick-m/XAUUSD-SCALPER-X10/audit/x10-500/scripts/windows_mt5_bridge_hotfix.py'
$HotfixPath = Join-Path $ProjectDir 'scripts\windows_mt5_bridge_hotfix.py'
$Runner = Join-Path $ProjectDir 'run_bridge.cmd'
$Python = Join-Path $ProjectDir '.venv\Scripts\python.exe'
$LogDir = Join-Path $ProjectDir 'logs'

if (-not (Test-Path $Python)) { throw "Bridge Python missing: $Python" }
if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) { throw "Scheduled task missing: $TaskName" }

Write-Host 'Downloading symbol-resolution hotfix...' -ForegroundColor Cyan
Invoke-WebRequest -UseBasicParsing -Uri $HotfixUrl -OutFile $HotfixPath
& $Python -m py_compile $HotfixPath

$runnerContent = @"
@echo off
cd /d "$ProjectDir"
"$Python" -m scripts.windows_mt5_bridge_hotfix run >> "$LogDir\windows_bridge.log" 2>&1
"@
Set-Content -Path $Runner -Value $runnerContent -Encoding ASCII

Write-Host 'Restarting H24 bridge task...' -ForegroundColor Cyan
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Task state: $($task.State)" -ForegroundColor Green
Write-Host "Last task result: $($info.LastTaskResult)"
Write-Host "Log: $LogDir\windows_bridge.log"
Write-Host 'Hotfix applied. Trading remains controlled by the Linux manifest.' -ForegroundColor Yellow
