param(
    [Parameter(Mandatory=$true)][string]$Path,
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

if (-not (Test-Path $Path)) {
    Write-Error "File not found: $Path"
    exit 1
}

$secret = $env:ZMETA_SHARED_SECRET
$headers = @{ 'Content-Type' = 'application/json' }
if ($secret) {
    $headerName = $env:ZMETA_AUTH_HEADER
    if (-not $headerName) { $headerName = 'x-zmeta-secret' }
    $headers[$headerName] = $secret
}

Get-Content -Path $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not [string]::IsNullOrWhiteSpace($line)) {
        Invoke-RestMethod -Uri "$BaseUrl/ingest" -Method POST -Headers $headers -Body $line
        Start-Sleep -Milliseconds 100
    }
}
