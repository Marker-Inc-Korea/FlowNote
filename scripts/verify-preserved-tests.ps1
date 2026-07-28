#requires -Version 5.1

param(
    [string]$RunId = ("integrated-smoke-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")),
    [switch]$SkipFastApiPytest,
    [switch]$SkipWpfBuild,
    [switch]$SkipWpfSmoke,
    [switch]$SkipAndroidBuild,
    [switch]$RunAndroidDeviceSmoke,
    [switch]$SkipGitArtifactCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot
$RunId = ($RunId -replace "[^A-Za-z0-9._-]", "-").Trim([char[]]".-_")
if ([string]::IsNullOrWhiteSpace($RunId)) {
    throw "RunId must contain at least one letter or number."
}
if ($RunId.Length -gt 96) {
    $RunId = $RunId.Substring(0, 96)
}
$runArtifactDir = Join-Path $repoRoot ("data/local/integrated-smoke/{0}" -f $RunId)
if ((Test-Path $runArtifactDir -PathType Container) -and
    @(Get-ChildItem -Force $runArtifactDir).Count -gt 0) {
    throw "Run artifact directory already contains preserved evidence. Use a new RunId: $runArtifactDir"
}
New-Item -ItemType Directory -Force -Path $runArtifactDir | Out-Null
$env:FLOWNOTE_SMOKE_RUN_ID = $RunId
$env:FLOWNOTE_SMOKE_ARTIFACT_DIR = $runArtifactDir
$expectedFastApiTestCount = 154
$expectedWpfCoreTestCount = 74
$expectedAndroidUnitTestCount = 16
$stepDisplayNames = @{
    "Check Windows baseline toolchain versions" = "Windows x64 표준 도구 확인"
    "Check .gitignore coverage for known test/build artifact paths" = "테스트·빌드 산출물 Git 제외 규칙 확인"
    "Check current git status before verification" = "검증 전 Git 상태 확인"
    "Collect FastAPI pytest tests" = "FastAPI pytest 테스트 수집"
    "Run FastAPI pytest" = "FastAPI pytest 실행"
    "Run WPF Core tests" = "WPF Core 테스트 실행"
    "Build WPF app" = "WPF 앱 빌드"
    "Check shared WPF SQLite integrity before smoke" = "스모크 전 공통 WPF SQLite 무결성 확인"
    "Run integrated WPF smoke against shared SQLite and preserved FastAPI" = "공통 SQLite·보존 FastAPI 연동 WPF 스모크 실행"
    "Check shared WPF SQLite integrity after smoke" = "스모크 후 공통 WPF SQLite 무결성 확인"
    "Run Android unit tests and debug build" = "Android 단위 테스트·debug 빌드"
    "Run approved Android physical-device instrumentation smoke" = "승인 Android 실단말 계측 스모크"
    "Check git status after verification" = "검증 후 Git 상태 확인"
}
$script:stepNumber = 0
$script:plannedStepCount = 1
if (-not $SkipGitArtifactCheck) {
    $script:plannedStepCount += 3
}
if (-not $SkipFastApiPytest) {
    $script:plannedStepCount += 2
}
if (-not $SkipWpfBuild) {
    $script:plannedStepCount += 2
}
if (-not $SkipWpfSmoke) {
    $script:plannedStepCount += 3
}
if (-not $SkipAndroidBuild) {
    $script:plannedStepCount++
}
if ($RunAndroidDeviceSmoke) {
    $script:plannedStepCount++
}
$script:currentStepDisplayName = "검증 준비"
$script:currentStepStatus = "RUNNING"
$script:currentExpectedValue = "FastAPI 154건, WPF Core 74건, Android 16건과 모든 필수 단계 통과"
$script:currentActualValue = "아직 실행하지 않음"
$script:currentNextAction = "Windows x64 표준 도구 확인부터 순서대로 실행합니다."
$script:stepResults = New-Object System.Collections.Generic.List[object]
$script:isPartialRun = $SkipFastApiPytest -or $SkipWpfBuild -or $SkipWpfSmoke -or $SkipAndroidBuild -or $SkipGitArtifactCheck
$script:sourceCommit = $null
$script:fastApiEvidence = [ordered]@{
    expected = $expectedFastApiTestCount
    collected = $null
    unique_node_ids = $null
    passed = $null
    failures = $null
    errors = $null
    skipped = $null
    collection_matches_junit = $null
}
$script:wpfEvidence = [ordered]@{
    core_tests = [ordered]@{
        expected = $expectedWpfCoreTestCount
        collected = $null
        unique_node_ids = $null
        total = $null
        passed = $null
        failed = $null
        errors = $null
        skipped = $null
        collection_matches_trx = $null
    }
    app_build = [ordered]@{
        status = "NOT_RUN"
        compiler_warnings = $null
        errors = $null
        warnings_as_errors = $true
    }
    database_before = [ordered]@{
        quick_check = $null
        foreign_key_violations = $null
        evidence = $null
    }
    smoke = [ordered]@{
        status = "NOT_RUN"
        evidence = $null
        today_registered_and_listed = $null
        today_sql_verified_rows = $null
        past_document_id = $null
        past_previous_version = $null
        past_new_version = $null
        past_sql_verified_rows = $null
        quick_check = $null
        foreign_key_violations = $null
        mapping_duplicates = $null
        idempotency_duplicates = $null
    }
    database_after = [ordered]@{
        quick_check = $null
        foreign_key_violations = $null
        evidence = $null
    }
}
$script:androidEvidence = [ordered]@{
    unit_tests = [ordered]@{
        expected = $expectedAndroidUnitTestCount
        total = $null
        passed = $null
        failures = $null
        errors = $null
        skipped = $null
    }
    debug_build = [ordered]@{
        status = "NOT_RUN"
        compiler_warnings = $null
        warnings_as_errors = $true
    }
}
$script:gitArtifactEvidence = [ordered]@{
    source_commit = $null
    worktree_clean_before = $null
    worktree_clean_after = $null
    new_forbidden_tracked_files = $null
    staged_forbidden_artifacts = $null
    staged_personal_paths = $null
}
$script:trackedFilesBefore = @()
Write-Host "FlowNote 통합 검증 시작"
Write-Host "실행 ID: $RunId"
Write-Host "현재 단계: $($script:currentStepDisplayName) (0/$($script:plannedStepCount))"
Write-Host "기대값: $($script:currentExpectedValue)"
Write-Host "실제값: $($script:currentActualValue)"
Write-Host "다음 조치: $($script:currentNextAction)"
Write-Host "보존된 증거 경로: $runArtifactDir"

function Write-RunSummary {
    param(
        [string]$Status,
        [string]$Failure = "",
        [string]$FailureStep = "",
        [string]$ExpectedValue = "",
        [string]$ActualValue = "",
        [string]$NextAction = "",
        [string]$EvidencePath = ""
    )

    if ([string]::IsNullOrWhiteSpace($ExpectedValue)) {
        $ExpectedValue = $script:currentExpectedValue
    }
    if ([string]::IsNullOrWhiteSpace($ActualValue)) {
        $ActualValue = $script:currentActualValue
    }
    if ([string]::IsNullOrWhiteSpace($NextAction)) {
        $NextAction = $script:currentNextAction
    }
    if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
        $EvidencePath = $runArtifactDir
    }
    $failureExpectedValue = ""
    $failureActualValue = ""
    $failureNextAction = ""
    $failureEvidencePath = ""
    if (-not [string]::IsNullOrWhiteSpace($Failure)) {
        $failureExpectedValue = $ExpectedValue
        $failureActualValue = $ActualValue
        $failureNextAction = $NextAction
        $failureEvidencePath = $EvidencePath
    }

    $summary = [ordered]@{
        run_id = $RunId
        status = $Status
        source_commit = $script:sourceCommit
        started_from = $repoRoot.Path
        artifact_directory = $runArtifactDir
        generated_at = (Get-Date).ToString("O")
        failure = $Failure
        progress = [ordered]@{
            "현재 단계" = $script:currentStepDisplayName
            "단계 상태" = $script:currentStepStatus
            "단계 번호" = $script:stepNumber
            "전체 단계" = $script:plannedStepCount
            "기대값" = $ExpectedValue
            "실제값" = $ActualValue
            "중단 원인" = $Failure
            "다음 조치" = $NextAction
            "보존된 증거 경로" = $EvidencePath
        }
        failure_context = [ordered]@{
            "실패 단계" = $FailureStep
            "기대값" = $failureExpectedValue
            "실제값" = $failureActualValue
            "중단 원인" = $Failure
            "다음 조치" = $failureNextAction
            "보존된 증거 경로" = $failureEvidencePath
        }
        partial_run = $script:isPartialRun
        options = [ordered]@{
            skip_fastapi_pytest = $SkipFastApiPytest.IsPresent
            skip_wpf_build = $SkipWpfBuild.IsPresent
            skip_wpf_smoke = $SkipWpfSmoke.IsPresent
            skip_android_build = $SkipAndroidBuild.IsPresent
            run_android_device_smoke = $RunAndroidDeviceSmoke.IsPresent
            skip_git_artifact_check = $SkipGitArtifactCheck.IsPresent
        }
        fastapi = $script:fastApiEvidence
        wpf = $script:wpfEvidence
        android = $script:androidEvidence
        git_artifacts = $script:gitArtifactEvidence
        steps = @($script:stepResults | ForEach-Object { $_ })
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "verification-summary.json")
}

function Get-StepExpectedValue {
    param([string]$Name)

    switch ($Name) {
        "Check Windows baseline toolchain versions" {
            return "Windows x64, PowerShell 5.1 이상, .NET/Windows Desktop 10.x, Python 3.11 이상, x64 JDK 17, Android SDK 35"
        }
        "Check .gitignore coverage for known test/build artifact paths" {
            return "알려진 테스트·빌드 산출물 경로가 모두 Git 제외 대상"
        }
        "Check current git status before verification" {
            return "검증 전 Git clean, 금지 추적·스테이징·개인 경로 0건"
        }
        "Collect FastAPI pytest tests" {
            return "FastAPI node ID 총 154건, 고유 154건, 중복 0건"
        }
        "Run FastAPI pytest" {
            return "FastAPI JUnit total/passed 154/154, 실패·오류·건너뜀 0건"
        }
        "Run WPF Core tests" {
            return "WPF Core 수집/고유 74/74, TRX total/passed 74/74, 실패·오류·건너뜀 0건"
        }
        "Build WPF app" {
            return "WPF 앱 빌드 PASSED, compiler warning 0건, error 0건"
        }
        "Check shared WPF SQLite integrity before smoke" {
            return "스모크 전 공통 SQLite quick_check=ok, FK 위반 0건"
        }
        "Run integrated WPF smoke against shared SQLite and preserved FastAPI" {
            return "오늘 사진·인수인계 2건 등록·목록 조회, 기존 과거 문서 version +1, quick_check=ok, FK·중복 0건"
        }
        "Check shared WPF SQLite integrity after smoke" {
            return "스모크 후 공통 SQLite quick_check=ok, FK 위반 0건"
        }
        "Run Android unit tests and debug build" {
            return "Android JUnit total/passed 16/16, 실패·오류·건너뜀 0건, debug build PASSED"
        }
        "Run approved Android physical-device instrumentation smoke" {
            return "승인 Android 실단말 1대에서 계측 스모크 통과"
        }
        "Check git status after verification" {
            return "검증 후 Git clean, 신규 금지 추적·스테이징·개인 경로 0건"
        }
        default {
            return "해당 단계의 모든 검증 조건 통과"
        }
    }
}

function Get-StepActualValue {
    param(
        [string]$Name,
        [string]$Failure = ""
    )

    switch ($Name) {
        "Check Windows baseline toolchain versions" {
            return "운영체제=$([Environment]::OSVersion.VersionString), 플랫폼=$([Environment]::OSVersion.Platform), PowerShell=$($PSVersionTable.PSVersion); 검사 결과=$Failure"
        }
        "Collect FastAPI pytest tests" {
            return "수집=$($script:fastApiEvidence.collected), 고유=$($script:fastApiEvidence.unique_node_ids)"
        }
        "Run FastAPI pytest" {
            return "passed=$($script:fastApiEvidence.passed), failures=$($script:fastApiEvidence.failures), errors=$($script:fastApiEvidence.errors), skipped=$($script:fastApiEvidence.skipped)"
        }
        "Run WPF Core tests" {
            return "수집=$($script:wpfEvidence.core_tests.collected), 고유=$($script:wpfEvidence.core_tests.unique_node_ids), total=$($script:wpfEvidence.core_tests.total), passed=$($script:wpfEvidence.core_tests.passed), failed=$($script:wpfEvidence.core_tests.failed), errors=$($script:wpfEvidence.core_tests.errors), skipped=$($script:wpfEvidence.core_tests.skipped), 수집-TRX 일치=$($script:wpfEvidence.core_tests.collection_matches_trx)"
        }
        "Build WPF app" {
            return "status=$($script:wpfEvidence.app_build.status), compiler_warnings=$($script:wpfEvidence.app_build.compiler_warnings), errors=$($script:wpfEvidence.app_build.errors)"
        }
        "Check shared WPF SQLite integrity before smoke" {
            return "quick_check=$($script:wpfEvidence.database_before.quick_check), FK 위반=$($script:wpfEvidence.database_before.foreign_key_violations)"
        }
        "Run integrated WPF smoke against shared SQLite and preserved FastAPI" {
            return "status=$($script:wpfEvidence.smoke.status), 오늘 SQL 행=$($script:wpfEvidence.smoke.today_sql_verified_rows), 과거 version=$($script:wpfEvidence.smoke.past_previous_version)->$($script:wpfEvidence.smoke.past_new_version), quick_check=$($script:wpfEvidence.smoke.quick_check), FK 위반=$($script:wpfEvidence.smoke.foreign_key_violations), mapping 중복=$($script:wpfEvidence.smoke.mapping_duplicates), idempotency 중복=$($script:wpfEvidence.smoke.idempotency_duplicates)"
        }
        "Check shared WPF SQLite integrity after smoke" {
            return "quick_check=$($script:wpfEvidence.database_after.quick_check), FK 위반=$($script:wpfEvidence.database_after.foreign_key_violations)"
        }
        "Run Android unit tests and debug build" {
            return "total=$($script:androidEvidence.unit_tests.total), passed=$($script:androidEvidence.unit_tests.passed), failures=$($script:androidEvidence.unit_tests.failures), errors=$($script:androidEvidence.unit_tests.errors), skipped=$($script:androidEvidence.unit_tests.skipped), build=$($script:androidEvidence.debug_build.status)"
        }
        "Check current git status before verification" {
            return "worktree_clean=$($script:gitArtifactEvidence.worktree_clean_before); 중단 원인=$Failure"
        }
        "Check git status after verification" {
            return "worktree_clean=$($script:gitArtifactEvidence.worktree_clean_after), 신규 금지 추적=$($script:gitArtifactEvidence.new_forbidden_tracked_files), 금지 스테이징=$($script:gitArtifactEvidence.staged_forbidden_artifacts), 개인 경로=$($script:gitArtifactEvidence.staged_personal_paths)"
        }
        default {
            if ([string]::IsNullOrWhiteSpace($Failure)) {
                return "단계 통과"
            }
            return $Failure
        }
    }
}

function Get-StepNextAction {
    param([string]$Name)

    switch -Wildcard ($Name) {
        "Check Windows baseline toolchain versions" {
            return "표시된 실제 환경을 Windows x64 표준 도구 기대값에 맞춘 뒤, 보존 증거를 유지하고 새 RunId로 다시 실행하세요."
        }
        "Check *git*" {
            return "Git 상태와 금지 산출물 목록을 확인해 소스만 clean 상태로 만든 뒤, 로컬 증거는 보존하고 새 RunId로 다시 실행하세요."
        }
        "Collect FastAPI pytest tests" {
            return "보존된 node ID 목록에서 추가·삭제·중복 이력을 대조한 뒤 기대값 또는 테스트 구성을 바로잡고 새 RunId로 다시 실행하세요."
        }
        "Run FastAPI pytest" {
            return "FastAPI JUnit과 단계 로그에서 실패·오류·건너뜀 또는 수집 불일치를 확인한 뒤 새 RunId로 다시 실행하세요."
        }
        "Run WPF Core tests" {
            return "WPF TRX의 total/passed와 테스트 추가·삭제 이력을 대조한 뒤 guard 또는 테스트를 바로잡고 새 RunId로 다시 실행하세요."
        }
        "Build WPF app" {
            return "WPF 빌드 로그의 첫 warning/error를 수정한 뒤 새 RunId로 다시 실행하세요."
        }
        "Check shared WPF SQLite integrity*" {
            return "보존된 SQLite 무결성 증거에서 quick_check와 FK 위반을 확인해 복구한 뒤, DB를 삭제하지 말고 새 RunId로 다시 실행하세요."
        }
        "Run integrated WPF smoke*" {
            return "WPF 스모크 로그와 DB 증거에서 오늘 문서, 과거 version, 무결성 실제값을 확인한 뒤 새 RunId로 다시 실행하세요."
        }
        "Run Android unit tests and debug build" {
            return "Android JUnit과 빌드 로그의 첫 실패·warning을 수정한 뒤 새 RunId로 다시 실행하세요."
        }
        default {
            return "해당 단계 로그와 verification-summary.json을 확인해 원인을 수정한 뒤, 보존된 증거는 유지하고 새 RunId로 다시 실행하세요."
        }
    }
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    $script:stepNumber++
    $safeName = ($Name.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim([char[]]"-")
    $logPath = Join-Path $runArtifactDir ("{0:D2}-{1}.log" -f $script:stepNumber, $safeName)
    $startedAt = Get-Date
    $script:currentStepDisplayName = if ($stepDisplayNames.ContainsKey($Name)) {
        $stepDisplayNames[$Name]
    } else {
        $Name
    }
    $script:currentStepStatus = "RUNNING"
    $script:currentExpectedValue = Get-StepExpectedValue $Name
    $script:currentActualValue = "실행 중"
    $script:currentNextAction = "이 단계가 끝나면 결과를 요약에 기록하고 다음 단계로 진행합니다."

    Write-Host ""
    Write-Host "[$($script:stepNumber)/$($script:plannedStepCount)] 현재 단계: $($script:currentStepDisplayName)"
    Write-Host "기대값: $($script:currentExpectedValue)"
    Write-Host "실제값: $($script:currentActualValue)"
    Write-Host "보존된 증거 경로: $runArtifactDir"
    Write-RunSummary -Status "RUNNING"
    try {
        & $Action *>&1 | Tee-Object -FilePath $logPath
        $script:currentStepStatus = "PASSED"
        $script:currentActualValue = Get-StepActualValue $Name
        $script:currentNextAction = "다음 검증 단계로 진행합니다."
        $script:stepResults.Add([pscustomobject]@{
            number = $script:stepNumber
            name = $Name
            status = "PASSED"
            started_at = $startedAt.ToString("O")
            finished_at = (Get-Date).ToString("O")
            log = [IO.Path]::GetFileName($logPath)
            failure = ""
        })
        Write-RunSummary -Status "RUNNING"
    }
    catch {
        $failure = $_.Exception.Message
        $failureStep = $script:currentStepDisplayName
        $expectedValue = Get-StepExpectedValue $Name
        $actualValue = Get-StepActualValue $Name $failure
        $nextAction = Get-StepNextAction $Name
        $script:currentStepStatus = "FAILED"
        $script:currentExpectedValue = $expectedValue
        $script:currentActualValue = $actualValue
        $script:currentNextAction = $nextAction
        "FAILED: $failure" | Add-Content -Encoding UTF8 $logPath
        "실패 단계: $failureStep" | Add-Content -Encoding UTF8 $logPath
        "기대값: $expectedValue" | Add-Content -Encoding UTF8 $logPath
        "실제값: $actualValue" | Add-Content -Encoding UTF8 $logPath
        "중단 원인: $failure" | Add-Content -Encoding UTF8 $logPath
        "다음 조치: $nextAction" | Add-Content -Encoding UTF8 $logPath
        "보존된 증거 경로: $runArtifactDir" | Add-Content -Encoding UTF8 $logPath
        $script:stepResults.Add([pscustomobject]@{
            number = $script:stepNumber
            name = $Name
            status = "FAILED"
            started_at = $startedAt.ToString("O")
            finished_at = (Get-Date).ToString("O")
            log = [IO.Path]::GetFileName($logPath)
            failure = $failure
        })
        Write-RunSummary -Status "FAILED" -Failure $failure -FailureStep $failureStep `
            -ExpectedValue $expectedValue -ActualValue $actualValue `
            -NextAction $nextAction -EvidencePath $runArtifactDir
        Write-Host ""
        Write-Host "검증 실패"
        Write-Host "실패 단계: $failureStep"
        Write-Host "기대값: $expectedValue"
        Write-Host "실제값: $actualValue"
        Write-Host "중단 원인: $failure"
        Write-Host "다음 조치: $nextAction"
        Write-Host "보존된 증거 경로: $runArtifactDir"
        throw
    }
}

function Assert-CommandAvailable {
    param([string]$Name)

    if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "필수 명령을 찾을 수 없음: $Name"
    }
}

function Get-JUnitCounts {
    param([string]$Path)

    [xml]$document = Get-Content -Raw $Path
    $testSuites = @($document.SelectNodes("//*[local-name()='testsuite']"))
    if ($testSuites.Count -eq 0) {
        throw "JUnit file contains no testsuite: $Path"
    }

    $leafSuites = @($testSuites | Where-Object {
        $_.SelectNodes("./*[local-name()='testsuite']").Count -eq 0
    })
    return [pscustomobject]@{
        Tests = [int](($leafSuites | Measure-Object -Property tests -Sum).Sum)
        Failures = [int](($leafSuites | Measure-Object -Property failures -Sum).Sum)
        Errors = [int](($leafSuites | Measure-Object -Property errors -Sum).Sum)
        Skipped = [int](($leafSuites | Measure-Object -Property skipped -Sum).Sum)
    }
}

function Assert-StandardToolchain {
    Write-Host "OS: $([Environment]::OSVersion.VersionString)"
    Write-Host "PowerShell: $($PSVersionTable.PSVersion) ($($PSVersionTable.PSEdition))"
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw "표준 통합 기준선은 Windows x64에서 실행해야 함. 감지 플랫폼=$([Environment]::OSVersion.Platform)."
    }
    if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
        throw "표준 통합 기준선에는 64비트 Windows와 64비트 PowerShell 프로세스가 필요함."
    }

    $minimumPowerShell = [Version]"5.1"
    if ($PSVersionTable.PSVersion -lt $minimumPowerShell) {
        throw "PowerShell 5.1 이상이 필요함. 감지 버전=$($PSVersionTable.PSVersion)."
    }

    Assert-CommandAvailable "git"
    Assert-CommandAvailable "dotnet"
    Assert-CommandAvailable "java"
    Assert-CommandAvailable "javac"

    $dotnetSdkVersion = (& dotnet --version).Trim()
    Write-Host ".NET SDK: $dotnetSdkVersion"
    if ($LASTEXITCODE -ne 0 -or $dotnetSdkVersion -notmatch "^10\.") {
        throw ".NET SDK 10.x가 필요함. 감지 버전=$dotnetSdkVersion."
    }
    $dotnetRuntimes = @(& dotnet --list-runtimes)
    Write-Host (".NET runtimes: {0}" -f ($dotnetRuntimes -join "; "))
    if ($LASTEXITCODE -ne 0 -or -not ($dotnetRuntimes -match "^Microsoft\.WindowsDesktop\.App 10\.")) {
        throw ".NET Windows Desktop Runtime 10.x가 필요함."
    }

    $javaExecutable = (Get-Command java).Source
    $javaVersionLog = Join-Path $runArtifactDir "java-version.log"
    $javaVersionProcess = Start-Process -FilePath $javaExecutable `
        -ArgumentList @("-version") -NoNewWindow -Wait -PassThru `
        -RedirectStandardError $javaVersionLog
    $javaVersionExitCode = $javaVersionProcess.ExitCode
    $javaVersionLines = @(Get-Content $javaVersionLog)
    if ($javaVersionExitCode -ne 0) {
        throw "Unable to execute java -version."
    }
    $javaVersionText = $javaVersionLines -join "`n"
    Write-Host ("Java: {0}" -f ($javaVersionLines -join "; "))
    if ($javaVersionText -notmatch 'version "17(?:\.|\")') {
        throw "Android 기준선에는 JDK 17이 필요함. 감지 값=$javaVersionText."
    }
    $javacVersion = (& javac -version 2>&1) -join " "
    Write-Host "Javac: $javacVersion"
    if ($LASTEXITCODE -ne 0 -or $javacVersion -notmatch "javac 17(?:\.|$)") {
        throw "JDK 17 compiler가 필요함. 감지 값=$javacVersion."
    }
    if ([string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        throw "JAVA_HOME은 JDK 17 설치 경로를 가리켜야 함."
    }
    $javaHomeExecutable = Join-Path $env:JAVA_HOME "bin/java.exe"
    $pathJavaExecutable = (Get-Command java).Source
    if (-not (Test-Path $javaHomeExecutable -PathType Leaf) -or
        (Resolve-Path $javaHomeExecutable).Path -ne (Resolve-Path $pathJavaExecutable).Path) {
        throw "JAVA_HOME과 PATH의 java는 같은 JDK 17 설치 경로를 가리켜야 함."
    }
    $javaSettingsLog = Join-Path $runArtifactDir "java-settings.log"
    $javaSettingsProcess = Start-Process -FilePath $javaExecutable `
        -ArgumentList @("-XshowSettings:properties", "-version") -NoNewWindow -Wait -PassThru `
        -RedirectStandardError $javaSettingsLog
    $javaSettingsExitCode = $javaSettingsProcess.ExitCode
    $javaSettings = @(Get-Content $javaSettingsLog) -join "`n"
    if ($javaSettingsExitCode -ne 0) {
        throw "Unable to inspect Java runtime properties."
    }
    if ($javaSettings -notmatch "(?m)^\s*os\.arch\s*=\s*amd64\s*$") {
        throw "x64 JDK 17이 필요하며 java os.arch는 amd64여야 함."
    }

    $androidSdkRoot = $env:ANDROID_SDK_ROOT
    if ([string]::IsNullOrWhiteSpace($androidSdkRoot)) {
        $androidSdkRoot = $env:ANDROID_HOME
    }
    if ([string]::IsNullOrWhiteSpace($androidSdkRoot) -or -not (Test-Path $androidSdkRoot -PathType Container)) {
        throw "ANDROID_SDK_ROOT 또는 ANDROID_HOME은 설치된 Android SDK 경로를 가리켜야 함."
    }
    Write-Host "Android SDK root: $androidSdkRoot"
    foreach ($relativePath in @("platforms/android-35", "build-tools/35.0.0", "platform-tools")) {
        $requiredPath = Join-Path $androidSdkRoot $relativePath
        if (-not (Test-Path $requiredPath -PathType Container)) {
            throw "필수 Android SDK 구성요소가 없음: $requiredPath"
        }
    }

    $gradleWrapperScript = Join-Path $repoRoot "apps/android/gradlew.bat"
    if (-not (Test-Path $gradleWrapperScript -PathType Leaf) -or
        (Get-Content -Raw $gradleWrapperScript) -notmatch "GRADLE_VERSION=8\.10\.2") {
        throw "Android Gradle Wrapper 8.10.2가 필요함."
    }
    $androidBuildFile = Join-Path $repoRoot "apps/android/build.gradle"
    if ((Get-Content -Raw $androidBuildFile) -notmatch 'com\.android\.application" version "8\.7\.3"') {
        throw "Android Gradle Plugin 8.7.3이 필요함."
    }

    $apiPython = Join-Path $repoRoot "services/api/.venv/Scripts/python.exe"
    if (-not (Test-Path $apiPython -PathType Leaf)) {
        throw "FastAPI 가상환경 Python을 찾을 수 없음: $apiPython"
    }
    $pythonVersion = (& $apiPython --version 2>&1) -join " "
    Write-Host "Python: $pythonVersion"
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch "Python 3\.(1[1-9]|[2-9][0-9])\.") {
        throw "Python 3.11 이상이 필요함. 감지 값=$pythonVersion."
    }

    $script:sourceCommit = (& git rev-parse HEAD).Trim()
    $script:gitArtifactEvidence.source_commit = $script:sourceCommit
    $environment = [ordered]@{
        run_id = $RunId
        source_commit = $script:sourceCommit
        os = [Environment]::OSVersion.VersionString
        powershell = $PSVersionTable.PSVersion.ToString()
        powershell_edition = $PSVersionTable.PSEdition
        dotnet_sdk = $dotnetSdkVersion
        dotnet_runtimes = $dotnetRuntimes
        java = $javaVersionLines
        javac = $javacVersion
        android_sdk_root = $androidSdkRoot
        android_platform = "35"
        android_build_tools = "35.0.0"
        gradle_wrapper = "8.10.2"
        python = $pythonVersion
        git = (& git --version).Trim()
    }
    $environment | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "environment.json")
    $environment.GetEnumerator() | ForEach-Object { Write-Host ("{0}: {1}" -f $_.Key, ($_.Value -join "; ")) }
}

function ConvertTo-GitPath {
    param([string]$Path)

    return $Path.Replace("\", "/").TrimStart("/")
}

function Assert-GitIgnoreRule {
    param([string]$ProbePath)

    $probe = ConvertTo-GitPath $ProbePath
    & git check-ignore --quiet -- $probe
    if ($LASTEXITCODE -ne 0) {
        throw "Git ignore rule is missing for test/build artifact path: $probe"
    }
}

function Test-ForbiddenArtifactPath {
    param([string]$Path)

    $normalized = ConvertTo-GitPath $Path

    if ($normalized.EndsWith("/.gitkeep", [StringComparison]::Ordinal)) {
        return $false
    }

    $forbiddenPatterns = @(
        "^data/local/",
        "^tmp/",
        "^temp/",
        "^smoke-output/",
        "^smoke-results/",
        "^test-output/",
        "^test-results/",
        "^services/api/storage/",
        "^services/api/data/",
        "^services/api/\.venv/",
        "^services/api/\.pytest_cache/",
        "^services/api/\.ruff_cache/",
        "^data/local/Files/",
        "^apps/windows/src/FlowNote\.Windows\.App/Data/",
        "^apps/windows/src/.+/bin/",
        "^apps/windows/src/.+/obj/",
        "^apps/android/\.gradle/",
        "^apps/android/.+/build/",
        "/bin/",
        "/obj/",
        "\.(log|trace|dmp|pdf|jpg|jpeg|png|gif|bmp|tif|tiff|webp|xlsx|xls|doc|docx|ppt|pptx|hwp|dwg|zip|7z|rar|tmp|bak|orig|trx|coverage|coveragexml|nupkg|snupkg|msi|msix|appx|appxbundle|apk|aab|wixpdb)$",
        "\.(sqlite3|db)(-shm|-wal)?$",
        "\.sqlite(-shm|-wal)$"
    )

    foreach ($pattern in $forbiddenPatterns) {
        if ($normalized -match $pattern) {
            return $true
        }
    }

    return $false
}

function Assert-NoForbiddenGitArtifacts {
    $statusLines = @(& git status --porcelain=v1 --untracked-files=all)
    $badStatus = New-Object System.Collections.Generic.List[string]
    foreach ($line in $statusLines) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.Length -lt 4) {
            continue
        }

        $path = $line.Substring(3)
        if ($path.Contains(" -> ")) {
            $path = $path.Split(" -> ")[-1]
        }

        if (Test-ForbiddenArtifactPath $path) {
            $badStatus.Add($line)
        }
    }

    $trackedFiles = @(& git ls-files)
    $badTracked = @($trackedFiles | Where-Object { Test-ForbiddenArtifactPath $_ })

    $personalPathPatterns = @(
        ("[A-Za-z]:\\" + "Users\\"),
        ("[A-Za-z]:/" + "Users/"),
        ("/" + "Users/"),
        ([regex]::Escape("C:") + "[\\/]" + [regex]::Escape("Projects") + "[\\/]")
    )

    $stagedDiff = @(& git diff --cached --)
    $personalPathLines = @($stagedDiff | Where-Object {
        $line = $_
        @($personalPathPatterns | Where-Object { $line -match $_ }).Count -gt 0
    })

    if ($badStatus.Count -gt 0 -or $badTracked.Count -gt 0 -or $personalPathLines.Count -gt 0) {
        Write-Host ""
        Write-Host "Forbidden artifact check failed."

        if ($badStatus.Count -gt 0) {
            Write-Host ""
            Write-Host "git status contains test/build artifacts that must not be committed:"
            $badStatus | ForEach-Object { Write-Host "  $_" }
        }

        if ($badTracked.Count -gt 0) {
            Write-Host ""
            Write-Host "git already tracks files that match artifact deny rules:"
            $badTracked | ForEach-Object { Write-Host "  $_" }
        }

        if ($personalPathLines.Count -gt 0) {
            Write-Host ""
            Write-Host "staged diff contains local machine paths:"
            $personalPathLines | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        }

        throw "Git artifact check failed. Preserve files locally; update .gitignore or untrack artifacts with git rm --cached."
    }
}

function Write-GitEvidence {
    param([ValidateSet("before", "after")][string]$Phase)

    $statusLines = @(& git status --short --untracked-files=all)
    $trackedFiles = @(& git ls-files)
    $stagedFiles = @(& git diff --cached --name-only)
    Set-Content -Encoding UTF8 -Path (Join-Path $runArtifactDir "git-status-$Phase.txt") `
        -Value ($statusLines -join [Environment]::NewLine)
    Set-Content -Encoding UTF8 -Path (Join-Path $runArtifactDir "git-ls-files-$Phase.txt") `
        -Value ($trackedFiles -join [Environment]::NewLine)
    Set-Content -Encoding UTF8 -Path (Join-Path $runArtifactDir "git-staged-$Phase.txt") `
        -Value ($stagedFiles -join [Environment]::NewLine)
}

function Assert-KnownArtifactIgnoreRules {
    $artifactProbes = @(
        "services/api/storage/.artifact-ignore-probe",
        "services/api/.pytest_cache/.artifact-ignore-probe",
        "services/api/.ruff_cache/.artifact-ignore-probe",
        "services/api/.venv/.artifact-ignore-probe",
        "data/local/integrated-smoke/probe/result.txt",
        "data/local/Files/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.App/Data/Files/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.App/bin/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.App/obj/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.SmokeTests/bin/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.SmokeTests/obj/.artifact-ignore-probe",
        "apps/android/.gradle/.artifact-ignore-probe",
        "apps/android/app/build/test-results/result.xml",
        "apps/android/app/build/outputs/apk/debug/app-debug.apk",
        "artifacts/wpf-msi/.artifact-ignore-probe",
        "installer-output/.artifact-ignore-probe",
        "tmp/.artifact-ignore-probe",
        "smoke-output/.artifact-ignore-probe",
        "smoke-results/.artifact-ignore-probe",
        "test-output/.artifact-ignore-probe",
        "test-results/.artifact-ignore-probe"
    )

    foreach ($probe in $artifactProbes) {
        Assert-GitIgnoreRule $probe
    }
}

Invoke-Step "Check Windows baseline toolchain versions" {
    Assert-StandardToolchain
}

if (-not $SkipGitArtifactCheck) {
    Invoke-Step "Check .gitignore coverage for known test/build artifact paths" {
        Assert-KnownArtifactIgnoreRules
    }

    Invoke-Step "Check current git status before verification" {
        Write-GitEvidence -Phase "before"
        $script:trackedFilesBefore = @(& git ls-files)
        $statusBefore = @(& git status --porcelain=v1 --untracked-files=all)
        $script:gitArtifactEvidence.worktree_clean_before = $statusBefore.Count -eq 0
        Assert-NoForbiddenGitArtifacts
        if ($statusBefore.Count -ne 0) {
            throw "The integrated baseline must start from a clean worktree tied to source commit $($script:sourceCommit)."
        }
    }
}

if (-not $SkipFastApiPytest) {
    Invoke-Step "Collect FastAPI pytest tests" {
        $apiDir = Join-Path $repoRoot "services/api"
        $python = Join-Path $apiDir ".venv/Scripts/python.exe"
        if (-not (Test-Path $python)) {
            throw "FastAPI virtualenv python not found: $python"
        }

        Push-Location $apiDir
        try {
            $collected = @(& $python -m pytest --collect-only -q)
            $nodeIds = @($collected | Where-Object { $_ -match "::" } | ForEach-Object { $_.Trim() })
            $nodeIds | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "fastapi-collected-tests.txt")
            $testCount = $nodeIds.Count
            $uniqueTestCount = @($nodeIds | Sort-Object -Unique).Count
            $script:fastApiEvidence.collected = $testCount
            $script:fastApiEvidence.unique_node_ids = $uniqueTestCount
            if ($testCount -ne $expectedFastApiTestCount) {
                throw "Expected $expectedFastApiTestCount FastAPI pytest tests, collected $testCount."
            }
            if ($uniqueTestCount -ne $testCount) {
                throw "FastAPI collection contains duplicate node IDs: total=$testCount, unique=$uniqueTestCount."
            }
            Write-Host "Collected FastAPI pytest tests: $testCount (unique node IDs: $uniqueTestCount)"
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Run FastAPI pytest" {
        $apiDir = Join-Path $repoRoot "services/api"
        $python = Join-Path $apiDir ".venv/Scripts/python.exe"
        Push-Location $apiDir
        try {
            $junitPath = Join-Path $runArtifactDir "fastapi-pytest.xml"
            & $python -m pytest --junitxml $junitPath
            $pytestExitCode = $LASTEXITCODE
            if (-not (Test-Path $junitPath -PathType Leaf)) {
                throw "FastAPI JUnit이 생성되지 않음: exit_code=$pytestExitCode, path=$junitPath."
            }
            $junitCounts = Get-JUnitCounts $junitPath
            $script:fastApiEvidence.passed = $junitCounts.Tests - $junitCounts.Failures - $junitCounts.Errors - $junitCounts.Skipped
            $script:fastApiEvidence.failures = $junitCounts.Failures
            $script:fastApiEvidence.errors = $junitCounts.Errors
            $script:fastApiEvidence.skipped = $junitCounts.Skipped
            $script:fastApiEvidence.collection_matches_junit = (
                $null -ne $script:fastApiEvidence.collected -and
                $junitCounts.Tests -eq $script:fastApiEvidence.collected
            )
            if ($pytestExitCode -ne 0 -or
                -not $script:fastApiEvidence.collection_matches_junit -or
                $junitCounts.Tests -ne $expectedFastApiTestCount -or
                $junitCounts.Failures -ne 0 -or
                $junitCounts.Errors -ne 0 -or
                $junitCounts.Skipped -ne 0) {
                throw "FastAPI JUnit 불일치: exit_code=$pytestExitCode, 기대=$expectedFastApiTestCount, tests=$($junitCounts.Tests), passed=$($script:fastApiEvidence.passed), failures=$($junitCounts.Failures), errors=$($junitCounts.Errors), skipped=$($junitCounts.Skipped)."
            }
            Write-Host "FastAPI collection/JUnit match: collected=$($script:fastApiEvidence.collected), unique=$($script:fastApiEvidence.unique_node_ids), tests=$($junitCounts.Tests)"
            Write-Host "FastAPI JUnit: passed=$($script:fastApiEvidence.passed), failures=0, errors=0, skipped=0"
        }
        finally {
            Pop-Location
        }
    }
}

if (-not $SkipWpfBuild) {
    Invoke-Step "Run WPF Core tests" {
        $collectionLogPath = Join-Path $runArtifactDir "wpf-core-collection.log"
        $collectionOutput = @(& dotnet test ".\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj" `
            --list-tests `
            -p:TreatWarningsAsErrors=true 2>&1)
        $collectionExitCode = $LASTEXITCODE
        $collectionOutput | Set-Content -Encoding UTF8 $collectionLogPath
        $collectionOutput | ForEach-Object { Write-Host $_ }
        if ($collectionExitCode -ne 0) {
            throw "WPF Core 테스트 수집 실패: exit_code=$collectionExitCode."
        }
        $wpfNodeIds = @($collectionOutput | Where-Object {
            $_ -match "^\s+FlowNote\.Windows\.Core\.Tests\."
        } | ForEach-Object { $_.Trim() })
        $wpfUniqueNodeIds = @($wpfNodeIds | Sort-Object -Unique)
        $wpfNodeIds | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "wpf-core-collected-tests.txt")
        $script:wpfEvidence.core_tests.collected = $wpfNodeIds.Count
        $script:wpfEvidence.core_tests.unique_node_ids = $wpfUniqueNodeIds.Count
        if ($wpfNodeIds.Count -ne $expectedWpfCoreTestCount -or
            $wpfUniqueNodeIds.Count -ne $expectedWpfCoreTestCount) {
            throw "WPF Core 수집 불일치: 기대=$expectedWpfCoreTestCount, 수집=$($wpfNodeIds.Count), 고유=$($wpfUniqueNodeIds.Count)."
        }
        Write-Host "WPF Core 수집: total=$($wpfNodeIds.Count), unique=$($wpfUniqueNodeIds.Count)"

        $trxPath = Join-Path $runArtifactDir "wpf-core-tests.trx"
        & dotnet test ".\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj" `
            --logger ("trx;LogFileName={0}" -f [IO.Path]::GetFileName($trxPath)) `
            --results-directory $runArtifactDir `
            -p:TreatWarningsAsErrors=true
        $wpfTestExitCode = $LASTEXITCODE
        if (-not (Test-Path $trxPath -PathType Leaf)) {
            throw "WPF Core TRX가 생성되지 않음: exit_code=$wpfTestExitCode, path=$trxPath."
        }
        [xml]$trx = Get-Content -Raw $trxPath
        $counters = $trx.SelectSingleNode("//*[local-name()='Counters']")
        if ($null -eq $counters) {
            throw "WPF Core TRX counters are missing."
        }
        $wpfTotal = [int]$counters.GetAttribute("total")
        $wpfPassed = [int]$counters.GetAttribute("passed")
        $wpfFailed = [int]$counters.GetAttribute("failed")
        $wpfErrors = [int]$counters.GetAttribute("error")
        $wpfSkipped = [int]$counters.GetAttribute("notExecuted")
        $script:wpfEvidence.core_tests.total = $wpfTotal
        $script:wpfEvidence.core_tests.passed = $wpfPassed
        $script:wpfEvidence.core_tests.failed = $wpfFailed
        $script:wpfEvidence.core_tests.errors = $wpfErrors
        $script:wpfEvidence.core_tests.skipped = $wpfSkipped
        $script:wpfEvidence.core_tests.collection_matches_trx = (
            $wpfTotal -eq $script:wpfEvidence.core_tests.collected
        )
        if ($wpfTestExitCode -ne 0 -or
            $wpfTotal -ne $expectedWpfCoreTestCount -or
            $wpfPassed -ne $expectedWpfCoreTestCount -or
            $wpfFailed -ne 0 -or
            $wpfErrors -ne 0 -or
            $wpfSkipped -ne 0 -or
            -not $script:wpfEvidence.core_tests.collection_matches_trx) {
            throw "WPF Core TRX 불일치: exit_code=$wpfTestExitCode, 기대=$expectedWpfCoreTestCount, 수집=$($script:wpfEvidence.core_tests.collected), total=$wpfTotal, passed=$wpfPassed, failed=$wpfFailed, errors=$wpfErrors, skipped=$wpfSkipped."
        }
        Write-Host "WPF Core 수집/TRX 일치: collected=$($script:wpfEvidence.core_tests.collected), total=$wpfTotal"
        Write-Host "WPF Core TRX: total=$wpfTotal, passed=$wpfPassed, failed=0, errors=0, skipped=0"
    }

    Invoke-Step "Build WPF app" {
        & dotnet build ".\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj" `
            -p:TreatWarningsAsErrors=true
        if ($LASTEXITCODE -ne 0) {
            throw "WPF build failed with exit code $LASTEXITCODE."
        }
        $script:wpfEvidence.app_build.status = "PASSED"
        $script:wpfEvidence.app_build.compiler_warnings = 0
        $script:wpfEvidence.app_build.errors = 0
    }
}

if (-not $SkipWpfSmoke) {
    Invoke-Step "Check shared WPF SQLite integrity before smoke" {
        $apiPython = Join-Path $repoRoot "services/api/.venv/Scripts/python.exe"
        $wpfDatabase = Join-Path $repoRoot "data/local/flownote.local.sqlite"
        & $apiPython ".\scripts\repair-wpf-controlled-copy-schema.py" `
            --database $wpfDatabase `
            --run-id "wpf-integrity-preflight" `
            --evidence-root $runArtifactDir `
            --check-only
        if ($LASTEXITCODE -ne 0) {
            throw "Shared WPF SQLite preflight integrity check failed with exit code $LASTEXITCODE."
        }
        $preflightEvidencePath = Join-Path $runArtifactDir "wpf-integrity-preflight/before-evidence.json"
        $preflightEvidence = Get-Content -Raw $preflightEvidencePath | ConvertFrom-Json
        $script:wpfEvidence.database_before.quick_check = @($preflightEvidence.quick_check) -join ","
        $script:wpfEvidence.database_before.foreign_key_violations = @($preflightEvidence.foreign_key_check).Count
        $script:wpfEvidence.database_before.evidence = "wpf-integrity-preflight/before-evidence.json"
        if ($script:wpfEvidence.database_before.quick_check -ne "ok" -or
            $script:wpfEvidence.database_before.foreign_key_violations -ne 0) {
            throw "Shared WPF SQLite preflight evidence does not report quick_check=ok and zero foreign-key violations."
        }
    }

    Invoke-Step "Run integrated WPF smoke against shared SQLite and preserved FastAPI" {
        $expectedDatabasePath = Join-Path $repoRoot "data/local/flownote.local.sqlite"
        $previousLocalDataDir = $env:FLOWNOTE_LOCAL_DATA_DIR
        $previousLocalDatabasePath = $env:FLOWNOTE_LOCAL_DATABASE_PATH
        $previousApiBaseUrl = $env:FLOWNOTE_API_BASE_URL
        $previousEnvironment = $env:FLOWNOTE_ENVIRONMENT
        $previousDatabaseUrl = $env:FLOWNOTE_DATABASE_URL
        $previousStorageRoot = $env:FLOWNOTE_STORAGE_ROOT
        $previousSmokeServerDatabasePath = $env:FLOWNOTE_SMOKE_SERVER_DATABASE_PATH
        $previousAiEnabled = $env:FLOWNOTE_AI_EXTERNAL_CALL_ENABLED
        $previousSmokeArtifactDir = $env:FLOWNOTE_SMOKE_ARTIFACT_DIR
        $managedApiProcess = $null

        try {
            $env:FLOWNOTE_LOCAL_DATA_DIR = $null
            $env:FLOWNOTE_LOCAL_DATABASE_PATH = $null
            $env:FLOWNOTE_API_BASE_URL = "http://127.0.0.1:5184"
            $env:FLOWNOTE_SMOKE_ARTIFACT_DIR = $runArtifactDir

            $apiAlreadyRunning = $false
            try {
                $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5184/api/v1/health" -TimeoutSec 2
                $apiAlreadyRunning = $health.StatusCode -eq 200
            }
            catch {
                $apiAlreadyRunning = $false
            }

            if (-not $apiAlreadyRunning) {
                $apiDir = Join-Path $repoRoot "services/api"
                $python = Join-Path $apiDir ".venv/Scripts/python.exe"
                if (-not (Test-Path $python)) {
                    throw "FastAPI virtualenv python not found: $python"
                }
                $env:FLOWNOTE_ENVIRONMENT = "test"
                $env:FLOWNOTE_DATABASE_URL = "sqlite:///./data/flownote.windows-smoke.sqlite3"
                $env:FLOWNOTE_STORAGE_ROOT = "./storage/windows-smoke"
                $env:FLOWNOTE_SMOKE_SERVER_DATABASE_PATH = Join-Path $apiDir "data/flownote.windows-smoke.sqlite3"
                $env:FLOWNOTE_AI_EXTERNAL_CALL_ENABLED = "false"
                $apiOutLog = Join-Path $runArtifactDir "fastapi-server.out.log"
                $apiErrLog = Join-Path $runArtifactDir "fastapi-server.err.log"
                $managedApiProcess = Start-Process -FilePath $python `
                    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "5184") `
                    -WorkingDirectory $apiDir -PassThru `
                    -RedirectStandardOutput $apiOutLog -RedirectStandardError $apiErrLog

                $started = $false
                for ($attempt = 0; $attempt -lt 30; $attempt++) {
                    Start-Sleep -Seconds 1
                    if ($managedApiProcess.HasExited) {
                        throw "Managed FastAPI exited before health check. Preserve and inspect: $apiErrLog"
                    }
                    try {
                        $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5184/api/v1/health" -TimeoutSec 2
                        if ($health.StatusCode -eq 200) {
                            $started = $true
                            break
                        }
                    }
                    catch {
                    }
                }
                if (-not $started) {
                    throw "Managed FastAPI did not become healthy. Preserve and inspect: $apiErrLog"
                }
            }
            else {
                throw "Port 5184 already has a healthy FastAPI process. Stop it so this run can start and preserve its own managed test server."
            }

            Write-Host "Expected WPF smoke SQLite DB: $expectedDatabasePath"
            $wpfLog = Join-Path $runArtifactDir "wpf-smoke.log"
            & dotnet run --project ".\apps\windows\src\FlowNote.Windows.SmokeTests\FlowNote.Windows.SmokeTests.csproj" *>&1 |
                Tee-Object -FilePath $wpfLog
            if ($LASTEXITCODE -ne 0) {
                throw "WPF smoke failed with exit code $LASTEXITCODE."
            }

            if (-not (Test-Path $expectedDatabasePath)) {
                throw "WPF smoke did not leave the shared SQLite DB at: $expectedDatabasePath"
            }
            $smokeEvidencePath = Join-Path $runArtifactDir "wpf-smoke-database-evidence.json"
            if (-not (Test-Path $smokeEvidencePath -PathType Leaf)) {
                throw "WPF smoke database evidence was not created: $smokeEvidencePath"
            }
            $smokeEvidence = Get-Content -Raw $smokeEvidencePath | ConvertFrom-Json
            $script:wpfEvidence.smoke.evidence = "wpf-smoke-database-evidence.json"
            $script:wpfEvidence.smoke.today_registered_and_listed = [bool]$smokeEvidence.today.registered_and_listed
            $script:wpfEvidence.smoke.today_sql_verified_rows = [int]$smokeEvidence.today.sql_verified_rows
            $script:wpfEvidence.smoke.past_document_id = $smokeEvidence.past_existing_document.document_id
            $script:wpfEvidence.smoke.past_previous_version = [int]$smokeEvidence.past_existing_document.previous_version
            $script:wpfEvidence.smoke.past_new_version = [int]$smokeEvidence.past_existing_document.new_version
            $script:wpfEvidence.smoke.past_sql_verified_rows = [int]$smokeEvidence.past_existing_document.sql_verified_rows
            $script:wpfEvidence.smoke.quick_check = $smokeEvidence.integrity.quick_check
            $script:wpfEvidence.smoke.foreign_key_violations = [int]$smokeEvidence.integrity.foreign_key_violations
            $script:wpfEvidence.smoke.mapping_duplicates = [int]$smokeEvidence.integrity.mapping_duplicates
            $script:wpfEvidence.smoke.idempotency_duplicates = [int]$smokeEvidence.integrity.idempotency_duplicates
            if ($smokeEvidence.run_id -ne $RunId -or
                -not $script:wpfEvidence.smoke.today_registered_and_listed -or
                $script:wpfEvidence.smoke.today_sql_verified_rows -ne 2 -or
                $script:wpfEvidence.smoke.past_new_version -ne ($script:wpfEvidence.smoke.past_previous_version + 1) -or
                $script:wpfEvidence.smoke.past_sql_verified_rows -ne 1 -or
                $script:wpfEvidence.smoke.quick_check -ne "ok" -or
                $script:wpfEvidence.smoke.foreign_key_violations -ne 0 -or
                $script:wpfEvidence.smoke.mapping_duplicates -ne 0 -or
                $script:wpfEvidence.smoke.idempotency_duplicates -ne 0) {
                throw "WPF smoke database evidence does not satisfy the integrated baseline contract."
            }
            $script:wpfEvidence.smoke.status = "PASSED"
        }
        finally {
            if ($null -ne $managedApiProcess -and -not $managedApiProcess.HasExited) {
                Stop-Process -Id $managedApiProcess.Id
                $managedApiProcess.WaitForExit()
            }
            $env:FLOWNOTE_LOCAL_DATA_DIR = $previousLocalDataDir
            $env:FLOWNOTE_LOCAL_DATABASE_PATH = $previousLocalDatabasePath
            $env:FLOWNOTE_API_BASE_URL = $previousApiBaseUrl
            $env:FLOWNOTE_ENVIRONMENT = $previousEnvironment
            $env:FLOWNOTE_DATABASE_URL = $previousDatabaseUrl
            $env:FLOWNOTE_STORAGE_ROOT = $previousStorageRoot
            $env:FLOWNOTE_SMOKE_SERVER_DATABASE_PATH = $previousSmokeServerDatabasePath
            $env:FLOWNOTE_AI_EXTERNAL_CALL_ENABLED = $previousAiEnabled
            $env:FLOWNOTE_SMOKE_ARTIFACT_DIR = $previousSmokeArtifactDir
        }
    }

    Invoke-Step "Check shared WPF SQLite integrity after smoke" {
        $apiPython = Join-Path $repoRoot "services/api/.venv/Scripts/python.exe"
        $wpfDatabase = Join-Path $repoRoot "data/local/flownote.local.sqlite"
        & $apiPython ".\scripts\repair-wpf-controlled-copy-schema.py" `
            --database $wpfDatabase `
            --run-id "wpf-integrity-postflight" `
            --evidence-root $runArtifactDir `
            --check-only
        if ($LASTEXITCODE -ne 0) {
            throw "Shared WPF SQLite postflight integrity check failed with exit code $LASTEXITCODE."
        }
        $postflightEvidencePath = Join-Path $runArtifactDir "wpf-integrity-postflight/before-evidence.json"
        $postflightEvidence = Get-Content -Raw $postflightEvidencePath | ConvertFrom-Json
        $script:wpfEvidence.database_after.quick_check = @($postflightEvidence.quick_check) -join ","
        $script:wpfEvidence.database_after.foreign_key_violations = @($postflightEvidence.foreign_key_check).Count
        $script:wpfEvidence.database_after.evidence = "wpf-integrity-postflight/before-evidence.json"
        if ($script:wpfEvidence.database_after.quick_check -ne "ok" -or
            $script:wpfEvidence.database_after.foreign_key_violations -ne 0) {
            throw "Shared WPF SQLite postflight evidence does not report quick_check=ok and zero foreign-key violations."
        }
    }
}

if (-not $SkipAndroidBuild) {
    Invoke-Step "Run Android unit tests and debug build" {
        $androidDir = Join-Path $repoRoot "apps/android"
        $androidLog = Join-Path $runArtifactDir "android-unit-build.log"
        Push-Location $androidDir
        try {
            & .\gradlew.bat testDebugUnitTest assembleDebug --stacktrace --warning-mode=fail *>&1 |
                Tee-Object -FilePath $androidLog
            if ($LASTEXITCODE -ne 0) {
                throw "Android unit test or debug build failed with exit code $LASTEXITCODE."
            }
            $androidResults = Join-Path $androidDir "app/build/test-results/testDebugUnitTest"
            if (-not (Test-Path $androidResults -PathType Container)) {
                throw "Android JUnit result directory was not created: $androidResults"
            }
            $preservedAndroidResults = Join-Path $runArtifactDir "android-test-results"
            New-Item -ItemType Directory -Force -Path $preservedAndroidResults | Out-Null
            Copy-Item -Recurse -Force (Join-Path $androidResults "*") $preservedAndroidResults
            $androidXmlFiles = @(Get-ChildItem -Path $androidResults -Filter "*.xml" -File -Recurse)
            if ($androidXmlFiles.Count -eq 0) {
                throw "Android JUnit XML files were not created."
            }
            $androidTests = 0
            $androidFailures = 0
            $androidErrors = 0
            $androidSkipped = 0
            foreach ($androidXmlFile in $androidXmlFiles) {
                $counts = Get-JUnitCounts $androidXmlFile.FullName
                $androidTests += $counts.Tests
                $androidFailures += $counts.Failures
                $androidErrors += $counts.Errors
                $androidSkipped += $counts.Skipped
            }
            $script:androidEvidence.unit_tests.total = $androidTests
            $script:androidEvidence.unit_tests.passed = $androidTests - $androidFailures - $androidErrors - $androidSkipped
            $script:androidEvidence.unit_tests.failures = $androidFailures
            $script:androidEvidence.unit_tests.errors = $androidErrors
            $script:androidEvidence.unit_tests.skipped = $androidSkipped
            if ($androidTests -ne $expectedAndroidUnitTestCount -or
                $script:androidEvidence.unit_tests.passed -ne $expectedAndroidUnitTestCount -or
                $androidFailures -ne 0 -or
                $androidErrors -ne 0 -or
                $androidSkipped -ne 0) {
                throw "Android JUnit mismatch: expected=$expectedAndroidUnitTestCount, tests=$androidTests, passed=$($script:androidEvidence.unit_tests.passed), failures=$androidFailures, errors=$androidErrors, skipped=$androidSkipped."
            }
            $script:androidEvidence.debug_build.status = "PASSED"
            $script:androidEvidence.debug_build.compiler_warnings = 0
            Write-Host "Android JUnit: tests=$androidTests, passed=$androidTests, failures=0, errors=0, skipped=0"
        }
        finally {
            Pop-Location
        }
    }
}

if ($RunAndroidDeviceSmoke) {
    Invoke-Step "Run approved Android physical-device instrumentation smoke" {
        if ($null -eq (Get-Command adb -ErrorAction SilentlyContinue)) {
            throw "adb is required for the approved Android physical-device smoke."
        }
        $connectedDevices = @(& adb devices | Select-Object -Skip 1 | Where-Object { $_ -match "\sdevice$" })
        if ($connectedDevices.Count -ne 1) {
            throw "Exactly one approved Android physical device must be connected; found $($connectedDevices.Count)."
        }
        $androidDir = Join-Path $repoRoot "apps/android"
        $deviceLog = Join-Path $runArtifactDir "android-device.log"
        Push-Location $androidDir
        try {
            & .\gradlew.bat connectedDebugAndroidTest --stacktrace *>&1 | Tee-Object -FilePath $deviceLog
            if ($LASTEXITCODE -ne 0) {
                throw "Android physical-device instrumentation smoke failed with exit code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }
}

if (-not $SkipGitArtifactCheck) {
    Invoke-Step "Check git status after verification" {
        Write-GitEvidence -Phase "after"
        $trackedFilesAfter = @(& git ls-files)
        $newTrackedFiles = @($trackedFilesAfter | Where-Object { $_ -notin $script:trackedFilesBefore })
        $newForbiddenTrackedFiles = @($newTrackedFiles | Where-Object { Test-ForbiddenArtifactPath $_ })
        $stagedFiles = @(& git diff --cached --name-only)
        $stagedForbiddenArtifacts = @($stagedFiles | Where-Object { Test-ForbiddenArtifactPath $_ })
        $stagedDiff = @(& git diff --cached --)
        $personalPathPatterns = @(
            ("[A-Za-z]:\\" + "Users\\"),
            ("[A-Za-z]:/" + "Users/"),
            ("/" + "Users/"),
            ([regex]::Escape("C:") + "[\\/]" + [regex]::Escape("Projects") + "[\\/]")
        )
        $stagedPersonalPaths = @($stagedDiff | Where-Object {
            $line = $_
            @($personalPathPatterns | Where-Object { $line -match $_ }).Count -gt 0
        })
        $script:gitArtifactEvidence.new_forbidden_tracked_files = $newForbiddenTrackedFiles.Count
        $script:gitArtifactEvidence.staged_forbidden_artifacts = $stagedForbiddenArtifacts.Count
        $script:gitArtifactEvidence.staged_personal_paths = $stagedPersonalPaths.Count
        $statusAfter = @(& git status --porcelain=v1 --untracked-files=all)
        $script:gitArtifactEvidence.worktree_clean_after = $statusAfter.Count -eq 0
        Assert-NoForbiddenGitArtifacts
        if ($newForbiddenTrackedFiles.Count -ne 0) {
            throw "Verification newly added forbidden tracked artifacts: $($newForbiddenTrackedFiles -join ', ')."
        }
        if ($statusAfter.Count -ne 0) {
            throw "The integrated baseline changed tracked or untracked source files. Inspect git-status-after.txt."
        }
        Write-Host "git status --short --untracked-files=all"
        & git status --short --untracked-files=all
        Write-Host "git ls-files"
        & git ls-files
    }
}

Write-Host ""
$finalStatus = if ($script:isPartialRun) { "PASSED_PARTIAL" } else { "PASSED" }
$script:currentStepDisplayName = "검증 완료"
$script:currentStepStatus = $finalStatus
$script:currentExpectedValue = "모든 계획 단계 통과"
$script:currentActualValue = "$($script:stepResults.Count)/$($script:plannedStepCount)단계 통과, partial_run=$($script:isPartialRun)"
$script:currentNextAction = if ($script:isPartialRun) {
    "생략한 단계를 포함해 새 RunId로 무생략 검증을 실행하세요."
} else {
    "원시 증거와 verification-summary.json을 대조해 기준선으로 기록하세요."
}
Write-RunSummary -Status $finalStatus
Write-Host "검증 완료: status=$finalStatus, run_id=$RunId"
Write-Host "실제값: $($script:currentActualValue)"
Write-Host "다음 조치: $($script:currentNextAction)"
Write-Host "테스트 DB, 로그, 산출물은 삭제하지 않았습니다."
