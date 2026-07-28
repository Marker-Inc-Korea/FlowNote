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
$apiRoot = Join-Path $serverRootPath "api"
$pythonPath = Join-Path $apiRoot ".venv\Scripts\python.exe"

function Stop-WithGuidance {
    param(
        [string]$MissingItem,
        [string]$NextAction
    )

    Write-Host "[누락 항목] $MissingItem"
    Write-Host "[보존된 데이터] 기존 서버 DB, storage, 로그와 고객 파일은 변경하거나 삭제하지 않았습니다."
    Write-Host "[담당자] 서버 설치 담당자 또는 서버 운영 담당자"
    Write-Host "[다음 조치] $NextAction"
    throw "FlowNote 서버 작업 스케줄러 설치 전제조건을 충족하지 못했습니다."
}

if (-not (Test-Path $sourceRunner)) {
    Stop-WithGuidance `
        -MissingItem "FlowNote 서버 실행 스크립트" `
        -NextAction "승인된 서버 배포본에 scripts\run-flownote-server.ps1이 있는지 확인한 뒤 다시 설치하세요."
}
if (-not (Test-Path -LiteralPath $apiRoot -PathType Container)) {
    Stop-WithGuidance `
        -MissingItem "FlowNote FastAPI 설치 폴더" `
        -NextAction "승인된 서버 패키지를 $apiRoot 경로에 배치한 뒤 다시 설치하세요."
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Stop-WithGuidance `
        -MissingItem "서버 전용 Python 가상환경" `
        -NextAction "$apiRoot 에서 승인 Python 버전으로 .venv를 만들고 의존성을 설치한 뒤 다시 설치하세요."
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
    -Force `
    -ErrorAction Stop | Out-Null

$registeredTask = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction Stop
$registeredActions = @($registeredTask.Actions)
$registeredTriggers = @($registeredTask.Triggers)
$actionMatches = (
    $registeredActions.Count -eq 1 -and
    [string]$registeredActions[0].Execute -eq $powerShellPath -and
    [string]$registeredActions[0].Arguments -like "*$runnerPath*" -and
    [string]$registeredActions[0].Arguments -like "*$serverRootPath*"
)
$startupTriggerMatches = @(
    $registeredTriggers |
        Where-Object { $_.CimClass.CimClassName -eq "MSFT_TaskBootTrigger" }
).Count -eq 1
$principalMatches = (
    [string]$registeredTask.Principal.UserId -eq "SYSTEM" -and
    [string]$registeredTask.Principal.RunLevel -eq "Highest"
)
if (-not ($actionMatches -and $startupTriggerMatches -and $principalMatches)) {
    Stop-WithGuidance `
        -MissingItem "승인된 SYSTEM 권한·부팅 트리거·서버 실행 경로 중 하나" `
        -NextAction "작업 스케줄러의 실행 사용자, 부팅 시 트리거, PowerShell 실행 경로와 ServerRoot 인자를 확인한 뒤 다시 등록하세요."
}

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction Stop
}

Write-Host "Registered scheduled task $TaskPath$TaskName"
Write-Host "Runner: $runnerPath"
Write-Host "Logs: $(Join-Path $serverRootPath 'logs')"
Write-Host "[PASS] SYSTEM 권한, 부팅 시 자동 시작, 승인된 실행 경로를 다시 조회해 확인했습니다."
