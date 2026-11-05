<#
.SYNOPSIS
    OmniView IQ - Feature 2 Live System Shutdown Script
.DESCRIPTION
    Cleanly stops background sensor bots, MQTT subscriber, and the Streamlit dashboard.
    Optionally stops Docker containers with -StopDocker.
#>

param(
    [switch]$StopDocker = $false
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

Write-Host "`nStopping OmniView IQ Live System..." -ForegroundColor Cyan

# --- 1. Terminate Background Services ---
if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $ScriptDir "scripts\stop_services.py")
}

# --- 2. Stop Docker Containers (Optional) ---
if ($StopDocker) {
    Write-Host "Stopping Docker containers (docker-compose stop)..." -ForegroundColor Yellow
    docker-compose stop
}

Write-Host "[OK] All Live System components stopped successfully.`n" -ForegroundColor Green
