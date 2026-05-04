param(
    [int]$BackendPort = 9527,
    [int]$FrontendPort = 5173
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logsDir = Join-Path $repoRoot "logs"
$backendLog = Join-Path $logsDir "dev-backend.log"
$backendErrLog = Join-Path $logsDir "dev-backend.err.log"
$frontendLog = Join-Path $logsDir "dev-frontend.log"
$frontendErrLog = Join-Path $logsDir "dev-frontend.err.log"
$frontendDir = Join-Path $repoRoot "frontend"
$frontendPackageJson = Join-Path $frontendDir "package.json"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

& (Join-Path $repoRoot "dev-stop.ps1") -BackendPort $BackendPort -FrontendPort $FrontendPort

$backendProcess = Start-Process `
    -FilePath "python" `
    -ArgumentList "main.py" `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErrLog `
    -PassThru

Write-Host "[backend] started PID $($backendProcess.Id), logs: $backendLog"

$backendReady = $false
for ($attempt = 0; $attempt -lt 10; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$BackendPort/health" -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    }
    catch {
        continue
    }
}

if ($backendReady) {
    Write-Host "[backend] health check ok on http://127.0.0.1:$BackendPort/health"
}
else {
    Write-Warning "[backend] health check did not succeed within timeout. Check $backendErrLog"
}

$frontendStarted = $false
try {
    if (Test-Path $frontendPackageJson) {
        $frontendProcess = Start-Process `
            -FilePath "npm.cmd" `
            -ArgumentList "--prefix", $frontendDir, "run", "dev" `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $frontendLog `
            -RedirectStandardError $frontendErrLog `
            -PassThru
        $frontendStarted = $true
        Write-Host "[frontend] started PID $($frontendProcess.Id), logs: $frontendLog"
        Write-Host "[frontend] expected dev url: http://127.0.0.1:${FrontendPort} or http://localhost:${FrontendPort}"
    }
    else {
        Write-Warning "[frontend] package.json not found at $frontendPackageJson"
    }
}
catch {
    Write-Warning "[frontend] failed to start: $($_.Exception.Message)"
    if (Test-Path $frontendErrLog) {
        Write-Warning "[frontend] check error log: $frontendErrLog"
    }
}

if (-not $frontendStarted) {
    Write-Host "[frontend] skipped"
}
