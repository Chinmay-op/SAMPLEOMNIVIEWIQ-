@echo off
title OmniView IQ - Start Live System
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_system.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Startup encountered an error. Press any key to exit.
    pause >nul
)
