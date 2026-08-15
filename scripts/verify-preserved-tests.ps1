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
$expectedFastApiTestCount = 215
$expectedWpfCoreTestCount = 120
$expectedAndroidUnitTestCount = 39
$stepDisplayNames = @{
    "Check Windows baseline toolchain versions" = "Windows x64 표준 도구 확인"
    "Check .gitignore coverage for known test/build artifact paths" = "테스트·빌드 산출물 Git 제외 규칙 확인"
    "Check current git status before verification" = "검증 전 Git 상태 확인"
    "Collect FastAPI pytest tests" = "FastAPI pytest 테스트 수집"
    "Run FastAPI pytest" = "FastAPI pytest 실행"
    "Run WPF Core tests" = "WPF Core 테스트 실행"
    "Build WPF app" = "WPF 앱 빌드"
    "Check shared WPF SQLite integrity before smoke" = "스모크 전 공통 WPF SQLite 무결성 확인"
    "Run integrated WPF smoke against shared SQLite and production HTTPS API" = "공통 SQLite·운영 HTTPS API 연동 WPF 스모크 실행"
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
$script:currentExpectedValue = "FastAPI ${expectedFastApiTestCount}건, WPF Core ${expectedWpfCoreTestCount}건, Android ${expectedAndroidUnitTestCount}건과 모든 필수 단계 통과"
$script:currentActualValue = "아직 실행하지 않음"
$script:currentNextAction = "Windows x64 표준 도구 확인부터 순서대로 실행합니다."
$script:currentPreservedData = "기존 공통 SQLite와 테스트 산출물은 삭제하거나 초기화하지 않습니다."
$script:stepResults = New-Object System.Collections.Generic.List[object]
$script:isPartialRun = $SkipFastApiPytest -or $SkipWpfBuild -or $SkipWpfSmoke -or $SkipAndroidBuild -or $SkipGitArtifactCheck
$script:sourceCommit = $null
$script:fastApiEvidence = [ordered]@{
    expected = $expectedFastApiTestCount
    collection_exit_code = $null
    collected = $null
    unique_node_ids = $null
    duplicate_node_ids = $null
    pytest_exit_code = $null
    junit_total = $null
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

. (Join-Path $PSScriptRoot "verify-preserved-tests-support.ps1")

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
        (Get-Content -Raw $gradleWrapperScript) -notmatch "GRADLE_VERSION=9\.5\.1") {
        throw "Android Gradle Wrapper 9.5.1이 필요함."
    }
    $androidBuildFile = Join-Path $repoRoot "apps/android/build.gradle"
    if ((Get-Content -Raw $androidBuildFile) -notmatch 'com\.android\.application" version "9\.3\.1"') {
        throw "Android Gradle Plugin 9.3.1이 필요함."
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
        gradle_wrapper = "9.5.1"
        android_gradle_plugin = "9.3.1"
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
            $collectionOutput = @(& $python -m pytest --collect-only -q 2>&1)
            $collectionExitCode = $LASTEXITCODE
            $collectionOutput | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "fastapi-collection.log")
            $collectionOutput | ForEach-Object { Write-Host $_ }
            $nodeIds = @($collectionOutput | Where-Object { $_ -match "::" } | ForEach-Object { $_.ToString().Trim() })
            $nodeIds | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "fastapi-collected-tests.txt")
            $testCount = $nodeIds.Count
            $uniqueTestCount = @($nodeIds | Sort-Object -Unique).Count
            $duplicateNodeIds = @(
                $nodeIds |
                    Group-Object |
                    Where-Object { $_.Count -gt 1 } |
                    ForEach-Object { $_.Name }
            )
            Set-Content `
                -Encoding UTF8 `
                -Path (Join-Path $runArtifactDir "fastapi-duplicate-node-ids.txt") `
                -Value ($duplicateNodeIds -join [Environment]::NewLine)
            $script:fastApiEvidence.collection_exit_code = $collectionExitCode
            $script:fastApiEvidence.collected = $testCount
            $script:fastApiEvidence.unique_node_ids = $uniqueTestCount
            $script:fastApiEvidence.duplicate_node_ids = $duplicateNodeIds.Count
            Assert-FastApiCollectionCounts `
                -Expected $expectedFastApiTestCount `
                -Collected $testCount `
                -Unique $uniqueTestCount `
                -Duplicates $duplicateNodeIds.Count `
                -ExitCode $collectionExitCode
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
            $script:fastApiEvidence.pytest_exit_code = $pytestExitCode
            if (-not (Test-Path $junitPath -PathType Leaf)) {
                throw "FastAPI JUnit이 생성되지 않음: exit_code=$pytestExitCode, path=$junitPath."
            }
            $junitCounts = Get-JUnitCounts $junitPath
            $script:fastApiEvidence.junit_total = $junitCounts.Tests
            $script:fastApiEvidence.passed = $junitCounts.Tests - $junitCounts.Failures - $junitCounts.Errors - $junitCounts.Skipped
            $script:fastApiEvidence.failures = $junitCounts.Failures
            $script:fastApiEvidence.errors = $junitCounts.Errors
            $script:fastApiEvidence.skipped = $junitCounts.Skipped
            $script:fastApiEvidence.collection_matches_junit = (
                $null -ne $script:fastApiEvidence.collected -and
                $junitCounts.Tests -eq $script:fastApiEvidence.collected
            )
            Assert-FastApiJUnitCounts `
                -Expected $expectedFastApiTestCount `
                -Total $junitCounts.Tests `
                -Passed $script:fastApiEvidence.passed `
                -Failures $junitCounts.Failures `
                -Errors $junitCounts.Errors `
                -Skipped $junitCounts.Skipped `
                -ExitCode $pytestExitCode `
                -CollectionMatchesJunit $script:fastApiEvidence.collection_matches_junit
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

    Invoke-Step "Run integrated WPF smoke against shared SQLite and production HTTPS API" {
        $expectedDatabasePath = Join-Path $repoRoot "data/local/flownote.local.sqlite"
        $previousLocalDataDir = $env:FLOWNOTE_LOCAL_DATA_DIR
        $previousLocalDatabasePath = $env:FLOWNOTE_LOCAL_DATABASE_PATH
        $previousApiBaseUrl = $env:FLOWNOTE_API_BASE_URL
        $previousSmokeArtifactDir = $env:FLOWNOTE_SMOKE_ARTIFACT_DIR

        try {
            $env:FLOWNOTE_LOCAL_DATA_DIR = $null
            $env:FLOWNOTE_LOCAL_DATABASE_PATH = $null
            if ([string]::IsNullOrWhiteSpace($env:FLOWNOTE_API_BASE_URL) -or
                $env:FLOWNOTE_API_BASE_URL.TrimEnd('/') -eq "https://flownote.example") {
                throw "FLOWNOTE_API_BASE_URL must be set to an approved HTTPS server before WPF smoke testing."
            }
            $env:FLOWNOTE_SMOKE_ARTIFACT_DIR = $runArtifactDir

            $apiUri = $null
            if (-not [Uri]::TryCreate($env:FLOWNOTE_API_BASE_URL, [UriKind]::Absolute, [ref]$apiUri) -or
                $apiUri.Scheme -ne "https") {
                throw "WPF 서버 연동 스모크에는 HTTPS FLOWNOTE_API_BASE_URL이 필요합니다. 로컬 FastAPI와 HTTP 주소는 허용하지 않습니다."
            }
            if ([string]::IsNullOrWhiteSpace($env:FLOWNOTE_SMOKE_ADMIN_USERNAME) -or
                [string]::IsNullOrWhiteSpace($env:FLOWNOTE_SMOKE_ADMIN_PASSWORD)) {
                throw "운영 서버 연동 스모크 전용 계정은 실행 환경에 주입해야 합니다. 자격 증명은 파일이나 저장소에 기록하지 마세요."
            }

            $healthUri = [Uri]::new($apiUri, "api/v1/health")
            $health = Invoke-WebRequest -UseBasicParsing -Uri $healthUri -TimeoutSec 10
            if ($health.StatusCode -ne 200) {
                throw "운영 HTTPS API health 확인에 실패했습니다: status=$($health.StatusCode)"
            }

            Write-Host "Expected WPF smoke SQLite DB: $expectedDatabasePath"
            Write-Host "운영 서버 테스트로 이관: $($apiUri.GetLeftPart([UriPartial]::Authority))"
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
            $env:FLOWNOTE_LOCAL_DATA_DIR = $previousLocalDataDir
            $env:FLOWNOTE_LOCAL_DATABASE_PATH = $previousLocalDatabasePath
            $env:FLOWNOTE_API_BASE_URL = $previousApiBaseUrl
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
