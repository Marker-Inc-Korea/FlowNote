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
$expectedFastApiTestCount = 145
$script:stepNumber = 0
$script:stepResults = New-Object System.Collections.Generic.List[object]
$script:isPartialRun = $SkipFastApiPytest -or $SkipWpfBuild -or $SkipWpfSmoke -or $SkipAndroidBuild -or $SkipGitArtifactCheck
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
$script:gitArtifactEvidence = [ordered]@{
    new_forbidden_tracked_files = $null
    staged_forbidden_artifacts = $null
    staged_personal_paths = $null
}
$script:trackedFilesBefore = @()
Write-Host "Integrated verification run ID: $RunId"
Write-Host "Preserved run artifacts: $runArtifactDir"

function Write-RunSummary {
    param(
        [string]$Status,
        [string]$Failure = ""
    )

    $summary = [ordered]@{
        run_id = $RunId
        status = $Status
        started_from = $repoRoot.Path
        artifact_directory = $runArtifactDir
        generated_at = (Get-Date).ToString("O")
        failure = $Failure
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
        git_artifacts = $script:gitArtifactEvidence
        steps = @($script:stepResults)
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $runArtifactDir "verification-summary.json")
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

    Write-Host ""
    Write-Host "==> $Name"
    try {
        & $Action *>&1 | Tee-Object -FilePath $logPath
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
        "FAILED: $failure" | Add-Content -Encoding UTF8 $logPath
        $script:stepResults.Add([pscustomobject]@{
            number = $script:stepNumber
            name = $Name
            status = "FAILED"
            started_at = $startedAt.ToString("O")
            finished_at = (Get-Date).ToString("O")
            log = [IO.Path]::GetFileName($logPath)
            failure = $failure
        })
        Write-RunSummary -Status "FAILED" -Failure $failure
        throw
    }
}

function Assert-CommandAvailable {
    param([string]$Name)

    if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is not available: $Name"
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
        throw "The standard integrated baseline must run on Windows. Detected: $([Environment]::OSVersion.Platform)"
    }
    if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
        throw "The standard integrated baseline requires a 64-bit Windows OS and 64-bit PowerShell process."
    }

    $minimumPowerShell = [Version]"5.1"
    if ($PSVersionTable.PSVersion -lt $minimumPowerShell) {
        throw "PowerShell 5.1 or newer is required. Detected: $($PSVersionTable.PSVersion)"
    }

    Assert-CommandAvailable "git"
    Assert-CommandAvailable "dotnet"
    Assert-CommandAvailable "java"
    Assert-CommandAvailable "javac"

    $dotnetSdkVersion = (& dotnet --version).Trim()
    Write-Host ".NET SDK: $dotnetSdkVersion"
    if ($LASTEXITCODE -ne 0 -or $dotnetSdkVersion -notmatch "^10\.") {
        throw ".NET SDK 10.x is required. Detected: $dotnetSdkVersion"
    }
    $dotnetRuntimes = @(& dotnet --list-runtimes)
    Write-Host (".NET runtimes: {0}" -f ($dotnetRuntimes -join "; "))
    if ($LASTEXITCODE -ne 0 -or -not ($dotnetRuntimes -match "^Microsoft\.WindowsDesktop\.App 10\.")) {
        throw ".NET Windows Desktop Runtime 10.x is required."
    }

    $javaVersionLines = @(& java -version 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to execute java -version."
    }
    $javaVersionText = $javaVersionLines -join "`n"
    Write-Host ("Java: {0}" -f ($javaVersionLines -join "; "))
    if ($javaVersionText -notmatch 'version "17(?:\.|\")') {
        throw "JDK 17 is required for the Android baseline. Detected: $javaVersionText"
    }
    $javacVersion = (& javac -version 2>&1) -join " "
    Write-Host "Javac: $javacVersion"
    if ($LASTEXITCODE -ne 0 -or $javacVersion -notmatch "javac 17(?:\.|$)") {
        throw "JDK 17 compiler is required. Detected: $javacVersion"
    }
    if ([string]::IsNullOrWhiteSpace($env:JAVA_HOME)) {
        throw "JAVA_HOME must point to the JDK 17 installation."
    }
    $javaHomeExecutable = Join-Path $env:JAVA_HOME "bin/java.exe"
    $pathJavaExecutable = (Get-Command java).Source
    if (-not (Test-Path $javaHomeExecutable -PathType Leaf) -or
        (Resolve-Path $javaHomeExecutable).Path -ne (Resolve-Path $pathJavaExecutable).Path) {
        throw "JAVA_HOME and PATH java must point to the same JDK 17 installation."
    }
    $javaSettings = @(& java -XshowSettings:properties -version 2>&1) -join "`n"
    if ($javaSettings -notmatch "(?m)^\s*os\.arch\s*=\s*amd64\s*$") {
        throw "An x64 JDK 17 is required; java os.arch must be amd64."
    }

    $androidSdkRoot = $env:ANDROID_SDK_ROOT
    if ([string]::IsNullOrWhiteSpace($androidSdkRoot)) {
        $androidSdkRoot = $env:ANDROID_HOME
    }
    if ([string]::IsNullOrWhiteSpace($androidSdkRoot) -or -not (Test-Path $androidSdkRoot -PathType Container)) {
        throw "ANDROID_SDK_ROOT or ANDROID_HOME must point to an installed Android SDK."
    }
    Write-Host "Android SDK root: $androidSdkRoot"
    foreach ($relativePath in @("platforms/android-35", "build-tools/35.0.0", "platform-tools")) {
        $requiredPath = Join-Path $androidSdkRoot $relativePath
        if (-not (Test-Path $requiredPath -PathType Container)) {
            throw "Required Android SDK component is missing: $requiredPath"
        }
    }

    $gradleWrapperScript = Join-Path $repoRoot "apps/android/gradlew.bat"
    if (-not (Test-Path $gradleWrapperScript -PathType Leaf) -or
        (Get-Content -Raw $gradleWrapperScript) -notmatch "GRADLE_VERSION=8\.10\.2") {
        throw "Android Gradle Wrapper 8.10.2 is required."
    }
    $androidBuildFile = Join-Path $repoRoot "apps/android/build.gradle"
    if ((Get-Content -Raw $androidBuildFile) -notmatch 'com\.android\.application" version "8\.7\.3"') {
        throw "Android Gradle Plugin 8.7.3 is required."
    }

    $apiPython = Join-Path $repoRoot "services/api/.venv/Scripts/python.exe"
    if (-not (Test-Path $apiPython -PathType Leaf)) {
        throw "FastAPI virtualenv python not found: $apiPython"
    }
    $pythonVersion = (& $apiPython --version 2>&1) -join " "
    Write-Host "Python: $pythonVersion"
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch "Python 3\.(1[1-9]|[2-9][0-9])\.") {
        throw "Python 3.11 or newer is required. Detected: $pythonVersion"
    }

    $environment = [ordered]@{
        run_id = $RunId
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
        Assert-NoForbiddenGitArtifacts
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
            if ($LASTEXITCODE -ne 0) {
                throw "FastAPI pytest failed with exit code $LASTEXITCODE."
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
            if (-not $script:fastApiEvidence.collection_matches_junit -or
                $junitCounts.Tests -ne $expectedFastApiTestCount -or
                $junitCounts.Failures -ne 0 -or
                $junitCounts.Errors -ne 0 -or
                $junitCounts.Skipped -ne 0) {
                throw "FastAPI JUnit mismatch: tests=$($junitCounts.Tests), failures=$($junitCounts.Failures), errors=$($junitCounts.Errors), skipped=$($junitCounts.Skipped)."
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
        $trxPath = Join-Path $runArtifactDir "wpf-core-tests.trx"
        & dotnet test ".\apps\windows\src\FlowNote.Windows.Core.Tests\FlowNote.Windows.Core.Tests.csproj" `
            --logger ("trx;LogFileName={0}" -f [IO.Path]::GetFileName($trxPath)) `
            --results-directory $runArtifactDir
        if ($LASTEXITCODE -ne 0) {
            throw "WPF Core tests failed with exit code $LASTEXITCODE."
        }
        if (-not (Test-Path $trxPath -PathType Leaf)) {
            throw "WPF Core test TRX was not created: $trxPath"
        }
        [xml]$trx = Get-Content -Raw $trxPath
        $counters = $trx.SelectSingleNode("//*[local-name()='Counters']")
        if ($null -eq $counters -or [int]$counters.total -le 0 -or [int]$counters.failed -ne 0 -or [int]$counters.error -ne 0) {
            throw "WPF Core TRX counters are missing or contain failures."
        }
        Write-Host "WPF Core TRX: total=$($counters.total), passed=$($counters.passed), failed=0, error=0"
    }

    Invoke-Step "Build WPF app" {
        & dotnet build ".\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj"
        if ($LASTEXITCODE -ne 0) {
            throw "WPF build failed with exit code $LASTEXITCODE."
        }
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
    }

    Invoke-Step "Run integrated WPF smoke against shared SQLite and preserved FastAPI" {
        $expectedDatabasePath = Join-Path $repoRoot "data/local/flownote.local.sqlite"
        $previousLocalDataDir = $env:FLOWNOTE_LOCAL_DATA_DIR
        $previousLocalDatabasePath = $env:FLOWNOTE_LOCAL_DATABASE_PATH
        $previousApiBaseUrl = $env:FLOWNOTE_API_BASE_URL
        $previousEnvironment = $env:FLOWNOTE_ENVIRONMENT
        $previousDatabaseUrl = $env:FLOWNOTE_DATABASE_URL
        $previousStorageRoot = $env:FLOWNOTE_STORAGE_ROOT
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
    }
}

if (-not $SkipAndroidBuild) {
    Invoke-Step "Run Android unit tests and debug build" {
        $androidDir = Join-Path $repoRoot "apps/android"
        $androidLog = Join-Path $runArtifactDir "android-unit-build.log"
        Push-Location $androidDir
        try {
            & .\gradlew.bat testDebugUnitTest assembleDebug --stacktrace *>&1 | Tee-Object -FilePath $androidLog
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
            foreach ($androidXmlFile in $androidXmlFiles) {
                $counts = Get-JUnitCounts $androidXmlFile.FullName
                $androidTests += $counts.Tests
                $androidFailures += $counts.Failures
                $androidErrors += $counts.Errors
            }
            if ($androidTests -le 0 -or $androidFailures -ne 0 -or $androidErrors -ne 0) {
                throw "Android JUnit mismatch: tests=$androidTests, failures=$androidFailures, errors=$androidErrors."
            }
            Write-Host "Android JUnit: tests=$androidTests, failures=0, errors=0"
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
        Assert-NoForbiddenGitArtifacts
        if ($newForbiddenTrackedFiles.Count -ne 0) {
            throw "Verification newly added forbidden tracked artifacts: $($newForbiddenTrackedFiles -join ', ')."
        }
        Write-Host "git status --short --untracked-files=all"
        & git status --short --untracked-files=all
        Write-Host "git ls-files"
        & git ls-files
    }
}

Write-Host ""
$finalStatus = if ($script:isPartialRun) { "PASSED_PARTIAL" } else { "PASSED" }
Write-RunSummary -Status $finalStatus
Write-Host "Verification sequence completed with status $finalStatus for run ID $RunId. Test DBs, logs, and artifacts were not deleted."
