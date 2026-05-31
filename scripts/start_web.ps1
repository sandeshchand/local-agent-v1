param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
$LogDir = Join-Path $Root "var\logs"
$OutLog = Join-Path $LogDir "web.out.log"
$ErrLog = Join-Path $LogDir "web.err.log"

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment Python was not found at $VenvPython"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Output "Stopping existing app.web uvicorn processes..."
$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match "^(python|uvicorn)(\.exe)?$" -and
        ($_.CommandLine -like "*uvicorn app.web:app*" -or $_.CommandLine -like "*uvicorn local_agent.app.web:app*")
    }

foreach ($process in $existing) {
    Write-Output "Stopping PID $($process.ProcessId): $($process.CommandLine)"
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1

Write-Output "Starting Local Agent web UI from venv..."
$server = Start-Process `
    -FilePath $VenvPython `
    -ArgumentList @("-m", "uvicorn", "local_agent.app.web:app", "--host", $HostAddress, "--port", "$Port") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

$healthUrl = "http://${HostAddress}:${Port}/health"
$deadline = (Get-Date).AddSeconds(40)
$healthy = $false

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing $healthUrl -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $healthy) {
    Write-Output "Server did not become healthy. Error log:"
    if (Test-Path $ErrLog) {
        Get-Content $ErrLog
    }
    throw "Web server failed to start."
}

$owners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($owner in $owners) {
    $ownerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($owner.OwningProcess)"
    Write-Output "Port $Port owner PID $($owner.OwningProcess): $($ownerProcess.ExecutablePath)"
    Write-Output "Command: $($ownerProcess.CommandLine)"
}

Write-Output "Web UI is ready: http://${HostAddress}:${Port}"
Write-Output "Logs:"
Write-Output "  $OutLog"
Write-Output "  $ErrLog"
