param(
    [int]$BackendPort = 9527,
    [int]$FrontendPort = 5173
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-ListeningProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (-not $connections -or $connections.Count -eq 0) {
        Write-Host "[$Label] no listening process on port $Port"
        return
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        try {
            $process = Get-Process -Id $processId -ErrorAction Stop
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Write-Host "[$Label] stopped PID $processId ($($process.ProcessName)) on port $Port"
        }
        catch {
            Write-Warning "[$Label] failed to stop PID $processId on port ${Port}: $($_.Exception.Message)"
        }
    }
}

Stop-ListeningProcesses -Port $BackendPort -Label "backend"
Stop-ListeningProcesses -Port $FrontendPort -Label "frontend"
