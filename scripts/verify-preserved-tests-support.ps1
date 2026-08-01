#requires -Version 5.1

function Get-StepOwner {
    param([string]$Name)

    switch -Wildcard ($Name) {
        "Check Windows baseline toolchain versions" { return "Windows 검증 환경 담당자" }
        "Collect FastAPI pytest tests" { return "FastAPI 담당자" }
        "Run FastAPI pytest" { return "FastAPI·SQLite 담당자" }
        "Run WPF Core tests" { return "Windows WPF 담당자" }
        "Build WPF app" { return "Windows WPF 담당자" }
        "Check shared WPF SQLite integrity*" { return "Windows WPF·SQLite 담당자" }
        "Run integrated WPF smoke*" { return "Windows WPF·SQLite 담당자" }
        "Run Android*" { return "Android 담당자" }
        "Check *git*" { return "변경 작성자·검증 담당자" }
        default { return "해당 단계 담당자" }
    }
}

function Write-RunSummary {
    param(
        [string]$Status,
        [string]$Failure = "",
        [string]$FailureStep = "",
        [string]$ExpectedValue = "",
        [string]$ActualValue = "",
        [string]$NextAction = "",
        [string]$PreservedData = "",
        [string]$EvidencePath = "",
        [string]$Owner = "",
        [string]$RerunCommand = ""
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
    if ([string]::IsNullOrWhiteSpace($PreservedData)) {
        $PreservedData = $script:currentPreservedData
    }
    if ([string]::IsNullOrWhiteSpace($EvidencePath)) {
        $EvidencePath = $runArtifactDir
    }
    $failureExpectedValue = ""
    $failureActualValue = ""
    $failureNextAction = ""
    $failurePreservedData = ""
    $failureEvidencePath = ""
    $failureOwner = ""
    $failureRerunCommand = ""
    if (-not [string]::IsNullOrWhiteSpace($Failure)) {
        $failureExpectedValue = $ExpectedValue
        $failureActualValue = $ActualValue
        $failureNextAction = $NextAction
        $failurePreservedData = $PreservedData
        $failureEvidencePath = $EvidencePath
        $failureOwner = $Owner
        $failureRerunCommand = $RerunCommand
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
            "보존된 데이터" = $PreservedData
            "보존된 증거 경로" = $EvidencePath
            "담당자" = $Owner
            "새 RunId 재실행" = $RerunCommand
            "중단 원인" = $Failure
            "다음 조치" = $NextAction
            "재실행 전 조치" = $NextAction
        }
        failure_context = [ordered]@{
            "실패 단계" = $FailureStep
            "기대값" = $failureExpectedValue
            "실제값" = $failureActualValue
            "보존된 데이터" = $failurePreservedData
            "보존된 증거 경로" = $failureEvidencePath
            "담당자" = $failureOwner
            "새 RunId 재실행" = $failureRerunCommand
            "중단 원인" = $Failure
            "다음 조치" = $failureNextAction
            "재실행 전 조치" = $failureNextAction
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
            return "FastAPI node ID 총 ${expectedFastApiTestCount}건, 고유 ${expectedFastApiTestCount}건, 중복 0건"
        }
        "Run FastAPI pytest" {
            return "FastAPI JUnit total/passed $expectedFastApiTestCount/$expectedFastApiTestCount, 실패·오류·건너뜀 0건"
        }
        "Run WPF Core tests" {
            return "WPF Core 수집/고유 87/87, TRX total/passed 87/87, 실패·오류·건너뜀 0건"
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
            return "Android JUnit total/passed 28/28, 실패·오류·건너뜀 0건, debug build PASSED"
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

    $failureSuffix = if ([string]::IsNullOrWhiteSpace($Failure)) {
        ""
    } else {
        "; 중단 원인=$Failure"
    }

    switch ($Name) {
        "Check Windows baseline toolchain versions" {
            return "운영체제=$([Environment]::OSVersion.VersionString), 플랫폼=$([Environment]::OSVersion.Platform), PowerShell=$($PSVersionTable.PSVersion); 검사 결과=$Failure"
        }
        "Collect FastAPI pytest tests" {
            return "기대 총/고유/중복=$expectedFastApiTestCount/$expectedFastApiTestCount/0, 실제 총/고유/중복=$($script:fastApiEvidence.collected)/$($script:fastApiEvidence.unique_node_ids)/$($script:fastApiEvidence.duplicate_node_ids), exit_code=$($script:fastApiEvidence.collection_exit_code)$failureSuffix"
        }
        "Run FastAPI pytest" {
            return "기대 JUnit total/passed/failures/errors/skipped=$expectedFastApiTestCount/$expectedFastApiTestCount/0/0/0, 실제=$($script:fastApiEvidence.junit_total)/$($script:fastApiEvidence.passed)/$($script:fastApiEvidence.failures)/$($script:fastApiEvidence.errors)/$($script:fastApiEvidence.skipped), pytest exit_code=$($script:fastApiEvidence.pytest_exit_code), 수집-JUnit 일치=$($script:fastApiEvidence.collection_matches_junit)$failureSuffix"
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
            return "누락됐거나 버전이 다른 도구를 Windows x64 표준 기대값에 맞추세요. 기존 RunId와 증거 폴더를 재사용하거나 삭제하지 말고, .\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>로 다시 실행하세요."
        }
        "Check *git*" {
            return "Git 상태와 금지 산출물 목록을 확인해 소스만 clean 상태로 만드세요. 기존 RunId와 로컬 증거는 재사용하거나 삭제하지 말고, .\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>로 다시 실행하세요."
        }
        "Collect FastAPI pytest tests" {
            return "보존된 수집 원본·node ID·중복 목록에서 추가·삭제·중복 이력을 대조해 기대값 또는 테스트 구성을 바로잡으세요. 기존 RunId와 증거 폴더를 재사용하거나 삭제하지 말고, .\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>로 다시 실행하세요."
        }
        "Run FastAPI pytest" {
            return "보존된 FastAPI JUnit과 단계 로그에서 실패·오류·건너뜀 또는 수집 불일치를 확인해 원인을 바로잡으세요. SQLite 잠금이면 실행 중인 FlowNote API·검증·보존 작업이 끝났는지 확인하세요. 누적 DB를 삭제하거나 초기화하지 말고 그대로 보존하세요. 기존 RunId와 증거 폴더를 재사용하거나 삭제하지 말고, .\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>로 다시 실행하세요."
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

function Get-StepPreservedData {
    param([string]$Name)

    switch -Wildcard ($Name) {
        "Collect FastAPI pytest tests" {
            return "FastAPI 수집 원본·node ID·중복 목록과 이전 단계 증거를 같은 실행 ID 폴더에 보존했으며, 기존 공통 SQLite와 테스트 산출물을 삭제하거나 초기화하지 않았습니다."
        }
        "Run FastAPI pytest" {
            return "FastAPI JUnit·단계 로그·수집 증거와 이전 단계 증거를 같은 실행 ID 폴더에 보존했으며, 기존 공통 SQLite와 테스트 산출물을 삭제하거나 초기화하지 않았습니다."
        }
        "Run WPF Core tests" {
            return "WPF Core 수집 목록·원본 수집 로그·생성된 TRX와 이전 단계 증거, 기존 공통 SQLite를 삭제하거나 초기화하지 않았습니다."
        }
        "Run integrated WPF smoke*" {
            return "공통 SQLite와 이번 스모크가 만든 문서·버전·로그·증거를 삭제하거나 초기화하지 않았습니다."
        }
        "Check shared WPF SQLite integrity*" {
            return "공통 SQLite와 무결성 증거, 이전 단계 로그를 삭제하거나 초기화하지 않았습니다."
        }
        default {
            return "기존 공통 SQLite와 테스트 산출물을 삭제하거나 초기화하지 않았고, 완료된 단계와 현재 실패의 로그·증거를 같은 실행 ID 폴더에 보존했습니다."
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
    $script:currentPreservedData = Get-StepPreservedData $Name

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
        $preservedData = Get-StepPreservedData $Name
        $owner = Get-StepOwner $Name
        $rerunCommand = ".\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>"
        $script:currentStepStatus = "FAILED"
        $script:currentExpectedValue = $expectedValue
        $script:currentActualValue = $actualValue
        $script:currentNextAction = $nextAction
        $script:currentPreservedData = $preservedData
        "FAILED: $failure" | Add-Content -Encoding UTF8 $logPath
        "현재 단계: $failureStep" | Add-Content -Encoding UTF8 $logPath
        "실패 단계: $failureStep" | Add-Content -Encoding UTF8 $logPath
        "기대값: $expectedValue" | Add-Content -Encoding UTF8 $logPath
        "실제값: $actualValue" | Add-Content -Encoding UTF8 $logPath
        "보존된 데이터: $preservedData" | Add-Content -Encoding UTF8 $logPath
        "보존된 증거 경로: $runArtifactDir" | Add-Content -Encoding UTF8 $logPath
        "담당자: $owner" | Add-Content -Encoding UTF8 $logPath
        "새 RunId 재실행: $rerunCommand" | Add-Content -Encoding UTF8 $logPath
        "중단 원인: $failure" | Add-Content -Encoding UTF8 $logPath
        "재실행 전 조치: $nextAction" | Add-Content -Encoding UTF8 $logPath
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
            -NextAction $nextAction -PreservedData $preservedData -EvidencePath $runArtifactDir `
            -Owner $owner -RerunCommand $rerunCommand
        Write-Host ""
        Write-Host "검증 실패"
        Write-Host "현재 단계: $failureStep"
        Write-Host "실패 단계: $failureStep"
        Write-Host "기대값: $expectedValue"
        Write-Host "실제값: $actualValue"
        Write-Host "보존된 데이터: $preservedData"
        Write-Host "보존된 증거 경로: $runArtifactDir"
        Write-Host "담당자: $owner"
        Write-Host "새 RunId 재실행: $rerunCommand"
        Write-Host "중단 원인: $failure"
        Write-Host "재실행 전 조치: $nextAction"
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

function Assert-FastApiCollectionCounts {
    param(
        [int]$Expected,
        [int]$Collected,
        [int]$Unique,
        [int]$Duplicates,
        [int]$ExitCode
    )

    if ($ExitCode -ne 0 -or
        $Collected -ne $Expected -or
        $Unique -ne $Expected -or
        $Duplicates -ne 0) {
        throw "FastAPI 수집 불일치: exit_code=$ExitCode, 기대 총/고유/중복=$Expected/$Expected/0, 실제 총/고유/중복=$Collected/$Unique/$Duplicates."
    }
}

function Assert-FastApiJUnitCounts {
    param(
        [int]$Expected,
        [int]$Total,
        [int]$Passed,
        [int]$Failures,
        [int]$Errors,
        [int]$Skipped,
        [int]$ExitCode,
        [bool]$CollectionMatchesJunit
    )

    if ($ExitCode -ne 0 -or
        -not $CollectionMatchesJunit -or
        $Total -ne $Expected -or
        $Passed -ne $Expected -or
        $Failures -ne 0 -or
        $Errors -ne 0 -or
        $Skipped -ne 0) {
        throw "FastAPI JUnit 불일치: pytest_exit_code=$ExitCode, 수집-JUnit 일치=$CollectionMatchesJunit, 기대 total/passed/failures/errors/skipped=$Expected/$Expected/0/0/0, 실제=$Total/$Passed/$Failures/$Errors/$Skipped."
    }
}
