@echo off
:: XAUUSD-SCALPER-X10 — Auto-start script
:: Place a shortcut to this file in shell:startup for auto-boot
:: Or register via Task Scheduler for true persistence

title XAUUSD-SCALPER-X10 Orchestrator
cd /d "%~dp0"

echo ============================================================
echo   XAUUSD-SCALPER-X10 Autonomous System
echo   Starting at %date% %time%
echo ============================================================

:loop
echo.
echo [%time%] Starting orchestrator...
python start.py

echo.
echo [%time%] Orchestrator exited. Restarting in 10 seconds...
echo   Press Ctrl+C to stop permanently.
timeout /t 10 /nobreak >nul
goto loop
