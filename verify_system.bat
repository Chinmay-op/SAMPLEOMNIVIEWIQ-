@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" "scripts\verify_system.py"
pause
