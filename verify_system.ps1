$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[ERROR] Virtual environment not found at $VenvPython" -ForegroundColor Red
    exit 1
}

$env:PYTHONIOENCODING = "utf-8"
& $VenvPython (Join-Path $ScriptDir "scripts\verify_system.py")
exit $LASTEXITCODE
