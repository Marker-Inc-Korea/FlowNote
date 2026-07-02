param(
    [string]$ServerRoot = "C:\FlowNote\Server",
    [string]$TaskName = "FlowNoteApi",
    [string]$TaskPath = "\FlowNote\",
    [switch]$StartNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$serverRootPath = [System.IO.Path]::GetFullPath($ServerRoot)
$serverScriptsPath = Join-Path $serverRootPath "scripts"
$sourceRunner = Join-Path $PSScriptRoot "run-flownote-server.ps1"
$runnerPath = Join-Path $serverScriptsPath "run-flownote-server.ps1"
$powerShellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $sourceRunner)) {
    throw "Runner script was not found: $sourceRunner"
}

foreach ($directory in @($serverRootPath, $serverScriptsPath)) {
    New-Item -ItemType Directory -Force $directory | Out-Null
}
Copy-Item -LiteralPath $sourceRunner -Destination $runnerPath -Force

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`" -ServerRoot `"$serverRootPath`""
$action = New-ScheduledTaskAction -Execute $powerShellPath -Argument $arguments -WorkingDirectory $serverRootPath
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Runs FlowNote FastAPI server from $serverRootPath." `
    -Force | Out-Null

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
}

Write-Host "Registered scheduled task $TaskPath$TaskName"
Write-Host "Runner: $runnerPath"
Write-Host "Logs: $(Join-Path $serverRootPath 'logs')"
