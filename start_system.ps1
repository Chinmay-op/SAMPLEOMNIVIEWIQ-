<#
.SYNOPSIS
    OmniView IQ - Feature 2 Live System & Dashboard Startup Script
.DESCRIPTION
    Fully automated repeatability script for cold startups or reboot:
    1. Checks & starts Docker Desktop / Docker daemon if stopped.
    2. Brings up Mosquitto (:1883) and TimescaleDB (:5432) via docker-compose.
    3. Runs database migrations to ensure hypertables exist.
    4. Verifies NTP clock synchronization.
    5. Starts background sensor bots (7 families) + MQTT subscriber.
    6. Starts Streamlit Live Tester Dashboard on port 8501.
    7. Automatically verifies health and opens the browser.
#>

param(
    [switch]$NoBrowser = $false,
    [int]$DashboardPort = 8501
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Write-Step {
    param([string]$Message)
    Write-Host "`n[STEP] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

Write-Host "=================================================================" -ForegroundColor DarkCyan
Write-Host "    OmniView IQ - Feature 2 Proof of Work Live System Runner    " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor DarkCyan

# --- 1. Locate Virtual Environment Python ---
Write-Step "Checking Python environment..."
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Err "Virtual environment not found at $VenvPython. Run: python -m venv .venv; pip install -e ."
    exit 1
}
Write-Success "Using Python: $VenvPython"

# --- 2. Ensure Docker Desktop & Daemon are Running ---
Write-Step "Verifying Docker engine..."
$dockerAvailable = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) { $dockerAvailable = $true }
} catch {}

if (-not $dockerAvailable) {
    Write-Warn "Docker daemon is not responding. Attempting to start Docker Desktop..."
    $DockerExePaths = @(
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    )
    $FoundDockerExe = $DockerExePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($FoundDockerExe) {
        Write-Host "Launching Docker Desktop from: $FoundDockerExe" -ForegroundColor Yellow
        Start-Process $FoundDockerExe
        
        $timeout = 60
        $elapsed = 0
        while ($elapsed -lt $timeout) {
            Start-Sleep -Seconds 3
            $elapsed += 3
            try {
                $null = docker info 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $dockerAvailable = $true
                    break
                }
            } catch {}
            Write-Host "  Waiting for Docker daemon to initialize... ($elapsed s / $timeout s)" -ForegroundColor Gray
        }
    }

    if (-not $dockerAvailable) {
        Write-Err "Could not connect to Docker daemon. Please start Docker Desktop manually and re-run this script."
        exit 1
    }
}
Write-Success "Docker engine is running and responsive."

# --- 3. Bring Up Mosquitto & TimescaleDB ---
Write-Step "Starting containers via docker-compose..."
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Err "docker-compose up -d failed."
    exit 1
}

$tsdbHealthy = $false
for ($i = 0; $i -lt 15; $i++) {
    $psOut = docker ps --filter "name=omniview-tsdb" --format "{{.Status}}"
    if ($psOut -match "healthy|Up") {
        $tsdbHealthy = $true
        break
    }
    Start-Sleep -Seconds 1
}
Write-Success "Containers are online: Mosquitto (:1883) & TimescaleDB (:5432)."

# --- 4. Verify Database Migrations ---
Write-Step "Ensuring TimescaleDB hypertables and migrations..."
& $VenvPython -m omniview.ingest.migrations
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to apply migrations to TimescaleDB."
    exit 1
}
Write-Success "Hypertables and scenario columns verified."

# --- 5. Check NTP Clock Drift ---
Write-Step "Checking gateway NTP clock drift..."
try {
    $ntpCheckScript = "import json; from omniview.edge.ntp_guard import check_drift; s = check_drift(); print(json.dumps({'offset': s.offset_seconds, 'synced': s.is_synced, 'server': s.ntp_server}))"
    $ntpJson = & $VenvPython -c $ntpCheckScript
    $ntp = $ntpJson | ConvertFrom-Json
    if ($ntp.synced) {
        Write-Success "NTP Clock Synced: $($ntp.offset)s offset via $($ntp.server) (limit <5.0s)."
    } else {
        Write-Warn "NTP Clock Out of Sync: $($ntp.offset)s offset. Telemetry will still flow."
    }
} catch {
    Write-Warn "Could not check NTP server drift. Continuing..."
}

# --- 6. Clean Up Prior Instances ---
Write-Step "Stopping any existing background runner instances..."
& $VenvPython (Join-Path $ScriptDir "scripts\stop_services.py")

# --- 7. Launch Background Bots & Streamlit via Detached Launcher ---
Write-Step "Launching 7 Sensor Bots + MQTT Ingest + Streamlit Dashboard..."
$env:PYTHONIOENCODING = "utf-8"
& $VenvPython (Join-Path $ScriptDir "scripts\launch_services.py") $DashboardPort
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to launch services."
    exit 1
}

# --- 8. Verify Dashboard Health & Launch Browser ---
Write-Step "Verifying Dashboard HTTP endpoint..."
$dashReady = $false
$healthUrl = "http://localhost:$DashboardPort/_stcore/health"
for ($i = 0; $i -lt 15; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 200) {
            $dashReady = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}

$DashUrl = "http://localhost:$DashboardPort"
if ($dashReady) {
    Write-Success "Dashboard is live and healthy at: $DashUrl"
    if (-not $NoBrowser) {
        Write-Host "Opening $DashUrl in your browser..." -ForegroundColor Cyan
        Start-Process $DashUrl
    }
} else {
    Write-Warn "Dashboard is taking longer to start. You can open $DashUrl manually."
}

Write-Host "`n=================================================================" -ForegroundColor DarkCyan
Write-Host "       LIVE SYSTEM ACTIVE - TELEMETRY FLOWING TO DASHBOARD       " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor DarkCyan
Write-Host "  Dashboard URL : $DashUrl" -ForegroundColor Yellow
Write-Host "  TimescaleDB   : localhost:5432 (omniview/omniview)"
Write-Host "  MQTT Broker   : localhost:1883"
Write-Host "  Stop System   : .\stop_system.ps1  (or double-click stop_system.bat)`n"
