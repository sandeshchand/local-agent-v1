param(
    [string]$TaskName = "LocalAgentScheduledBackup",
    [string]$BackupRoot = "D:\local-agent-backups",
    [string]$OffMachineRoot = "",
    [string]$At = "03:00",
    [int]$LocalKeep = 14,
    [int]$OffMachineKeep = 28,
    [switch]$ApplyPrune,
    [switch]$Register,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

function Quote-TaskArg {
    param([string]$Value)
    if ($Value -match '\s') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
$VenvPython = Join-Path $Root "venv\Scripts\python.exe"
$JobLog = Join-Path $Root "var\logs\scheduled_backup.jsonl"

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment Python was not found at $VenvPython"
}

if ($Register -and $Unregister) {
    throw "Use either -Register or -Unregister, not both."
}

if ($Unregister) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Output "Scheduled task '$TaskName' does not exist."
        exit 0
    }

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "Removed scheduled task '$TaskName'."
    exit 0
}

$Arguments = @(
    "scripts\runtime_state.py",
    "--env-file",
    ".env",
    "scheduled-backup",
    "--backup-root",
    (Quote-TaskArg $BackupRoot),
    "--local-keep",
    "$LocalKeep",
    "--off-machine-keep",
    "$OffMachineKeep",
    "--job-log",
    (Quote-TaskArg $JobLog)
)

if ($OffMachineRoot.Trim()) {
    $Arguments += @("--off-machine-root", (Quote-TaskArg $OffMachineRoot))
}

if ($ApplyPrune) {
    $Arguments += "--apply-prune"
}

$ArgumentText = $Arguments -join " "

Write-Output "Scheduled backup task preview"
Write-Output "Task name: $TaskName"
Write-Output "Program:   $VenvPython"
Write-Output "Arguments: $ArgumentText"
Write-Output "Start in:  $Root"
Write-Output "Daily at:  $At"

if (-not $Register) {
    Write-Output ""
    Write-Output "No task was registered. Re-run with -Register to create/update the Windows scheduled task."
    exit 0
}

$trigger = New-ScheduledTaskTrigger -Daily -At $At
$action = New-ScheduledTaskAction -Execute $VenvPython -Argument $ArgumentText -WorkingDirectory $Root
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs the Local Agent scheduled-backup workflow." `
    -Force | Out-Null

Write-Output "Registered scheduled task '$TaskName'."
Write-Output "Check it with: Get-ScheduledTask -TaskName $TaskName"
