$ws = New-Object -ComObject WScript.Shell
$startupPath = [Environment]::GetFolderPath('Startup')
$shortcut = $ws.CreateShortcut("$startupPath\XAUUSD-SCALPER-X10.lnk")
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"C:\Users\hp\XAUUSD-SCALPER-X10\start_hidden.vbs`""
$shortcut.WorkingDirectory = "C:\Users\hp\XAUUSD-SCALPER-X10"
$shortcut.Description = "XAUUSD Scalper Orchestrator"
$shortcut.Save()
Write-Host "Shortcut created in: $startupPath"
Write-Host "The system will auto-start on next login."
