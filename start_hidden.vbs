' XAUUSD-SCALPER-X10 — Silent background launcher
' Runs start.bat without a visible console window
' Place shortcut to THIS file in shell:startup for auto-boot

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run Chr(34) & Replace(WScript.ScriptFullName, "start_hidden.vbs", "start.bat") & Chr(34), 0, False
