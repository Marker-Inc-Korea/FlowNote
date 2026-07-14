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
New-Item -ItemType Directory -Force -Path $runArtifactDir | Out-Null
$env:FLOWNOTE_SMOKE_RUN_ID = $RunId
Write-Host "Integrated verification run ID: $RunId"
Write-Host "Preserved run artifacts: $runArtifactDir"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Name"
    & $Action
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

function Test-AllowedSqlitePath {
    param([string]$Path)

    $normalized = ConvertTo-GitPath $Path
    return $normalized -match "^(data/local|services/api/data)/.+\.sqlite$"
}

function Test-ForbiddenArtifactPath {
    param([string]$Path)

    $normalized = ConvertTo-GitPath $Path

    if ($normalized.EndsWith("/.gitkeep", [StringComparison]::Ordinal)) {
        return $false
    }

    if (Test-AllowedSqlitePath $normalized) {
        return $false
    }

    $forbiddenPatterns = @(
        "^tmp/",
        "^temp/",
        "^smoke-output/",
        "^smoke-results/",
        "^test-output/",
        "^test-results/",
        "^services/api/storage/",
        "^services/api/\.venv/",
        "^services/api/\.pytest_cache/",
        "^services/api/\.ruff_cache/",
        "^data/local/Files/",
        "^apps/windows/src/FlowNote\.Windows\.App/Data/",
        "^apps/windows/src/.+/bin/",
        "^apps/windows/src/.+/obj/",
        "/bin/",
        "/obj/",
        "\.(log|trace|dmp|pdf|jpg|jpeg|png|gif|bmp|tif|tiff|webp|xlsx|xls|doc|docx|ppt|pptx|hwp|dwg|zip|7z|rar|tmp|bak|orig|trx|coverage|coveragexml|nupkg|snupkg|msi|msix|appx|appxbundle|wixpdb)$",
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

function Assert-KnownArtifactIgnoreRules {
    $artifactProbes = @(
        "services/api/storage/.artifact-ignore-probe",
        "services/api/.pytest_cache/.artifact-ignore-probe",
        "services/api/.ruff_cache/.artifact-ignore-probe",
        "services/api/.venv/.artifact-ignore-probe",
        "data/local/Files/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.App/Data/Files/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.App/bin/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.App/obj/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.SmokeTests/bin/.artifact-ignore-probe",
        "apps/windows/src/FlowNote.Windows.SmokeTests/obj/.artifact-ignore-probe",
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

if (-not $SkipGitArtifactCheck) {
    Invoke-Step "Check .gitignore coverage for known test/build artifact paths" {
        Assert-KnownArtifactIgnoreRules
    }

    Invoke-Step "Check current git status before verification" {
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
            $testCount = @($collected | Where-Object { $_ -match "::" }).Count
            if ($testCount -ne 96) {
                throw "Expected 96 FastAPI pytest tests, collected $testCount."
            }
            Write-Host "Collected FastAPI pytest tests: $testCount"
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
        }
        finally {
            Pop-Location
        }
    }
}

if (-not $SkipWpfBuild) {
    Invoke-Step "Build WPF app" {
        & dotnet build ".\apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj"
        if ($LASTEXITCODE -ne 0) {
            throw "WPF build failed with exit code $LASTEXITCODE."
        }
    }
}

if (-not $SkipWpfSmoke) {
    Invoke-Step "Run integrated WPF smoke against shared SQLite and preserved FastAPI" {
        $expectedDatabasePath = Join-Path $repoRoot "data/local/flownote.local.sqlite"
        $previousLocalDataDir = $env:FLOWNOTE_LOCAL_DATA_DIR
        $previousLocalDatabasePath = $env:FLOWNOTE_LOCAL_DATABASE_PATH
        $previousApiBaseUrl = $env:FLOWNOTE_API_BASE_URL
        $previousEnvironment = $env:FLOWNOTE_ENVIRONMENT
        $previousDatabaseUrl = $env:FLOWNOTE_DATABASE_URL
        $previousStorageRoot = $env:FLOWNOTE_STORAGE_ROOT
        $previousAiEnabled = $env:FLOWNOTE_AI_EXTERNAL_CALL_ENABLED
        $managedApiProcess = $null

        try {
            $env:FLOWNOTE_LOCAL_DATA_DIR = $null
            $env:FLOWNOTE_LOCAL_DATABASE_PATH = $null
            $env:FLOWNOTE_API_BASE_URL = "http://127.0.0.1:5184"

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
                Write-Host "Using the already-running FastAPI at http://127.0.0.1:5184. Its configuration must keep external AI calls disabled."
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
        Assert-NoForbiddenGitArtifacts
        & git status --short
    }
}

Write-Host ""
Write-Host "Verification sequence completed for run ID $RunId. Test DBs, logs, and artifacts were not deleted."
