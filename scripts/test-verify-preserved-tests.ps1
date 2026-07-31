#requires -Version 5.1

param(
    [string]$ScriptPath = (Join-Path $PSScriptRoot "verify-preserved-tests.ps1"),
    [string]$RunId = "powershell-unit-test"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Contains {
    param(
        [string]$Actual,
        [string]$ExpectedFragment,
        [string]$Label
    )

    if ($Actual.IndexOf($ExpectedFragment, [StringComparison]::Ordinal) -lt 0) {
        throw "$Label 불일치: '$ExpectedFragment' 문구가 없음. 실제='$Actual'"
    }
}

function Invoke-IsolatedExpectedFailure {
    param(
        [string]$FunctionText,
        [string]$Invocation,
        [string]$Label
    )

    $powerShell = [PowerShell]::Create()
    try {
        [void]$powerShell.AddScript(
            "$FunctionText`ntry { $Invocation; '__NO_ERROR__' } catch { `$_.Exception.Message }"
        )
        $result = @($powerShell.Invoke())
        if ($result.Count -eq 0 -or $result[-1].ToString() -eq "__NO_ERROR__") {
            throw "$Label 검증이 예상대로 실패하지 않음."
        }
        return $result[-1].ToString()
    }
    finally {
        $powerShell.Dispose()
    }
}

$resolvedScriptPath = (Resolve-Path $ScriptPath).Path
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $resolvedScriptPath,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -ne 0) {
    $details = @($parseErrors | ForEach-Object {
        "$($_.Extent.StartLineNumber):$($_.Extent.StartColumnNumber) $($_.ErrorId) $($_.Message)"
    }) -join [Environment]::NewLine
    throw "PowerShell 구문 오류 $($parseErrors.Count)건:`n$details"
}

$requiredFunctionNames = @(
    "Get-StepExpectedValue",
    "Get-StepActualValue",
    "Get-StepNextAction",
    "Get-StepPreservedData",
    "Assert-FastApiCollectionCounts",
    "Assert-FastApiJUnitCounts"
)
$functionAsts = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $requiredFunctionNames -contains $node.Name
}, $true))
if ($functionAsts.Count -ne $requiredFunctionNames.Count) {
    throw "검증 대상 함수 수 불일치: 기대=$($requiredFunctionNames.Count), 실제=$($functionAsts.Count)"
}
foreach ($functionAst in $functionAsts) {
    Invoke-Expression $functionAst.Extent.Text
}

$expectedFastApiTestCount = 164
$script:fastApiEvidence = [ordered]@{
    expected = 164
    collection_exit_code = 0
    collected = 163
    unique_node_ids = 163
    duplicate_node_ids = 0
    pytest_exit_code = 1
    junit_total = 163
    passed = 162
    failures = 1
    errors = 0
    skipped = 0
    collection_matches_junit = $false
}

$collectionExpected = Get-StepExpectedValue "Collect FastAPI pytest tests"
Assert-Contains $collectionExpected "총 164건, 고유 164건, 중복 0건" "수집 기대값"

$collectionFunctionText = @($functionAsts | Where-Object {
    $_.Name -eq "Assert-FastApiCollectionCounts"
})[0].Extent.Text
$collectionMismatch = Invoke-IsolatedExpectedFailure `
    -FunctionText $collectionFunctionText `
    -Invocation "Assert-FastApiCollectionCounts -Expected 164 -Collected 163 -Unique 163 -Duplicates 0 -ExitCode 0" `
    -Label "의도적 수집 불일치"
Assert-Contains $collectionMismatch "FastAPI 수집 불일치" "의도적 수집 불일치"
Assert-Contains $collectionMismatch "기대 총/고유/중복=164/164/0" "수집 기대 수치"
Assert-Contains $collectionMismatch "실제 총/고유/중복=163/163/0" "수집 실제 수치"

$collectionActual = Get-StepActualValue "Collect FastAPI pytest tests" $collectionMismatch
Assert-Contains $collectionActual "기대 총/고유/중복=164/164/0" "수집 실패 실제값"
Assert-Contains $collectionActual "실제 총/고유/중복=163/163/0" "수집 실패 실제값"

$junitFunctionText = @($functionAsts | Where-Object {
    $_.Name -eq "Assert-FastApiJUnitCounts"
})[0].Extent.Text
$junitMismatch = Invoke-IsolatedExpectedFailure `
    -FunctionText $junitFunctionText `
    -Invocation "Assert-FastApiJUnitCounts -Expected 164 -Total 163 -Passed 162 -Failures 1 -Errors 0 -Skipped 0 -ExitCode 1 -CollectionMatchesJunit `$false" `
    -Label "의도적 JUnit 불일치"
Assert-Contains $junitMismatch "FastAPI JUnit 불일치" "의도적 JUnit 불일치"
Assert-Contains $junitMismatch "기대 total/passed/failures/errors/skipped=164/164/0/0/0" "JUnit 기대 수치"
Assert-Contains $junitMismatch "실제=163/162/1/0/0" "JUnit 실제 수치"

foreach ($stepName in @(
    "Check Windows baseline toolchain versions",
    "Collect FastAPI pytest tests",
    "Run FastAPI pytest"
)) {
    $nextAction = Get-StepNextAction $stepName
    Assert-Contains $nextAction ".\scripts\verify-preserved-tests.ps1 -RunId <새-run-id>" "$stepName 다음 조치"
    Assert-Contains $nextAction "재사용하거나 삭제하지 말고" "$stepName 증거 보존"
}

$toolFailure = "필수 명령을 찾을 수 없음: dotnet"
$toolExpected = Get-StepExpectedValue "Check Windows baseline toolchain versions"
$toolActual = Get-StepActualValue "Check Windows baseline toolchain versions" $toolFailure
$toolPreserved = Get-StepPreservedData "Check Windows baseline toolchain versions"
Assert-Contains $toolExpected "Windows x64" "도구 부족 기대값"
Assert-Contains $toolActual $toolFailure "도구 부족 실제값"
Assert-Contains $toolPreserved "삭제하거나 초기화하지 않았고" "도구 부족 보존 데이터"

foreach ($stepName in @("Collect FastAPI pytest tests", "Run FastAPI pytest")) {
    $preservedData = Get-StepPreservedData $stepName
    Assert-Contains $preservedData "같은 실행 ID 폴더에 보존" "$stepName 보존 데이터"
    Assert-Contains $preservedData "삭제하거나 초기화하지 않았습니다" "$stepName 보존 데이터"
}

$source = Get-Content -Raw $resolvedScriptPath
if ($source -match 'FastAPI 155건' -or $source -match '\$expectedFastApiTestCount\s*=\s*155') {
    throw "현재 FastAPI 기대값에 역사값 155가 남아 있음."
}
Assert-Contains $source '$expectedFastApiTestCount = 164' "FastAPI 단일 기준값"
Assert-Contains `
    $source `
    '$script:currentExpectedValue = "FastAPI ${expectedFastApiTestCount}건' `
    "시작 화면 FastAPI 기대값"

Write-Host "PowerShell 구문 검사 통과: parse_errors=0"
Write-Host "의도적 수집 불일치 확인: $collectionMismatch"
Write-Host "의도적 JUnit 불일치 확인: $junitMismatch"
Write-Host "새 실행 안내 확인: $(Get-StepNextAction 'Collect FastAPI pytest tests')"
Write-Host "FastAPI 기준값·의도적 수집/JUnit 불일치·도구 부족 다음 조치 UX 단위 검증 통과"
Write-Host "테스트 run_id: $RunId"
