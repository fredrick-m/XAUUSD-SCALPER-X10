# Packages the project for VPS deployment into XAUUSD-SCALPER-X10_vps.zip.
# Includes code, data, knowledge base and the (cleaned) DB; excludes logs,
# caches, git history and unrelated side projects.
# Run with the system STOPPED so the DB is not mid-write.

$projectRoot = Split-Path -Parent $PSScriptRoot
$zipPath = Join-Path (Split-Path -Parent $projectRoot) "XAUUSD-SCALPER-X10_vps.zip"

$running = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*start.py*" }
if ($running) {
    Write-Warning "Le systeme tourne (PID $($running.ProcessId)). Arrete-le avant de zipper (DB en cours d'ecriture)."
    exit 1
}

$include = @(
    "agents", "core", "engine", "dashboard", "scripts", "strategies",
    "data", "knowledge_base", "docs",
    "agent_db.sqlite", "start.bat", "start.py", "start_hidden.vbs",
    "requirements.txt", "MISSION.md", "ROADMAP.md", "process_queue.py"
)

$staging = Join-Path $env:TEMP "xauusd_vps_staging"
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging -Confirm:$false }
New-Item -ItemType Directory -Force $staging | Out-Null

foreach ($item in $include) {
    $src = Join-Path $projectRoot $item
    if (-not (Test-Path $src)) { continue }
    Write-Host "  + $item"
    if (Test-Path $src -PathType Container) {
        # Copy folders without caches
        robocopy $src (Join-Path $staging $item) /E /XD __pycache__ .obsidian /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null
    } else {
        Copy-Item $src (Join-Path $staging $item)
    }
}

if (Test-Path $zipPath) { Remove-Item -Force $zipPath -Confirm:$false }
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath
Remove-Item -Recurse -Force $staging -Confirm:$false

$sizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Package cree: $zipPath ($sizeMB MB)"
Write-Host "Voir docs\VPS_DEPLOYMENT.md pour les etapes d'installation."
