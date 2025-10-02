param(
    [switch]$NoGui,
    [switch]$NoSimulator
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $here '..')
Set-Location $root

if (-not (Test-Path '.venv/Scripts/Activate.ps1')) {
    Write-Host 'Creating virtual environment (.venv)...' -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host 'Activating virtual environment' -ForegroundColor Cyan
. .\.venv\Scripts\Activate.ps1

Write-Host 'Installing dependencies (pip install -r requirements.txt)' -ForegroundColor Cyan
pip install -r requirements.txt | Out-Host

$backendCmd = "cd `"$root`"; .\.venv\Scripts\Activate.ps1; python -m uvicorn backend.app.main:app --reload"
Write-Host 'Launching backend API in a new terminal' -ForegroundColor Green
Start-Process powershell -ArgumentList '-NoExit','-Command', $backendCmd | Out-Null

if (-not $NoGui) {
    $guiCmd = "cd `"$root`"; .\.venv\Scripts\Activate.ps1; python tools/gui_app.py"
    Write-Host 'Launching desktop GUI in a new terminal' -ForegroundColor Green
    Start-Process powershell -ArgumentList '-NoExit','-Command', $guiCmd | Out-Null
}

if (-not $NoSimulator) {
    $simCmd = "cd `"$root`"; .\.venv\Scripts\Activate.ps1; python -m tools.simulators.rf"
    Write-Host 'Launching RF simulator in a new terminal' -ForegroundColor Green
    Start-Process powershell -ArgumentList '-NoExit','-Command', $simCmd | Out-Null
}

Write-Host ''
Write-Host 'Stack startup commands dispatched. Use -NoGui or -NoSimulator to skip components.' -ForegroundColor Yellow
