@echo off
setlocal
cd /d "%~dp0"

echo Stopping OmniView IQ Background Services...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "scripts\stop_services.py"
) else (
    echo [WARN] Virtual environment not found. Stopping via PowerShell taskkill...
    powershell -ExecutionPolicy Bypass -File .\stop_system.ps1
)

echo [OK] Background services stopped.
pause
