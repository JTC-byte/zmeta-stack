param(
    [switch]$NoGui,
    [switch]$NoSimulator,
    [switch]$CheckHealth,
    [string]$HealthBaseUrl = 'http://127.0.0.1:8000',
    [string]$HealthEndpoint = '/api/v1/healthz',
    [double]$HealthTimeout = 5,
    [int]$HealthRetries = 15,
    [double]$HealthDelay = 1,
    [ValidateSet('pretty','json','status')]
    [string]$HealthOutput = 'pretty'
)

$ErrorActionPreference = 'Stop'

$healthParamsProvided = $PSBoundParameters.Keys | Where-Object { $_ -like 'Health*' }
if (-not $CheckHealth -and $healthParamsProvided) {
    $CheckHealth = $true
}

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

if ($CheckHealth) {
    Write-Host "Running API health check (up to $HealthRetries attempts)" -ForegroundColor Cyan
    $python = Resolve-Path '.\.venv\Scripts\python.exe'
    $healthScript = Resolve-Path 'scripts/run_health_check.py'
    $args = @('--timeout', $HealthTimeout.ToString(), '--output', $HealthOutput)

    if ($PSBoundParameters.ContainsKey('HealthBaseUrl')) {
        $args += @('--base-url', $HealthBaseUrl)
    }
    if ($PSBoundParameters.ContainsKey('HealthEndpoint')) {
        $args += @('--endpoint', $HealthEndpoint)
    }

    $attempt = 1
    while ($true) {
        $output = & $python $healthScript @args 2>&1
        if ($LASTEXITCODE -eq 0) {
            $output | ForEach-Object { Write-Host $_ }
            Write-Host 'Health check succeeded.' -ForegroundColor Green
            break
        }

        if ($attempt -ge $HealthRetries) {
            Write-Error "Health check failed after $HealthRetries attempts.`n$output"
            exit 1
        }

        $attempt += 1
        Write-Host "Health check not ready yet (attempt $attempt/$HealthRetries); retrying in $HealthDelay s..." -ForegroundColor Yellow
        Start-Sleep -Seconds $HealthDelay
    }
}

Write-Host ''
Write-Host 'Stack startup commands dispatched. Use -NoGui or -NoSimulator to skip components.' -ForegroundColor Yellow
if ($CheckHealth) {
    Write-Host 'Health check completed via scripts/run_health_check.py.' -ForegroundColor Yellow
}
