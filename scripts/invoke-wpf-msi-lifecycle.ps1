param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^PILOT-\d{8}-\d{4}-[A-Z0-9_-]+-\d{3}$")]
    [string]$RunId,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot,
    [Parameter(Mandatory = $true)]
    [string]$ArtifactRoot,
    [string]$InstallFolder = "C:\Program Files\FlowNote\Client\FlowNote.Windows.App",
    [string]$LocalDataDir = "C:\FlowNote\LocalData",
    [string]$MachineId = $env:COMPUTERNAME
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "MSI 수명주기 리허설은 승인된 Windows PC에서만 실행할 수 있습니다."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "MSI 수명주기 리허설은 관리자 권한 PowerShell에서 실행해야 합니다."
}

if ([string]::IsNullOrWhiteSpace($MachineId)) {
    throw "익명 Windows 장비 ID가 필요합니다."
}

$runRoot = Join-Path ([System.IO.Path]::GetFullPath($EvidenceRoot)) $RunId
$artifactRootPath = [System.IO.Path]::GetFullPath($ArtifactRoot)
$lifecyclePath = Join-Path $runRoot "install\windows-lifecycle.csv"
$packageEvidencePath = Join-Path $runRoot "packages\windows-server-packages.csv"
foreach ($requiredPath in @($lifecyclePath, $packageEvidencePath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "준비된 run_id 원시 판정표가 없습니다: $requiredPath"
    }
}
if (-not (Test-Path -LiteralPath $artifactRootPath -PathType Container)) {
    throw "승인 패키지 폴더가 없습니다: $artifactRootPath"
}
if (-not (Test-Path -LiteralPath $LocalDataDir -PathType Container)) {
    throw "보존 검증용 WPF 로컬 데이터 폴더가 없습니다: $LocalDataDir"
}
if (-not (Test-Path -LiteralPath (Join-Path $LocalDataDir "flownote.local.sqlite") -PathType Leaf)) {
    throw "보존 검증용 WPF SQLite가 없습니다."
}
if (-not (Test-Path -LiteralPath (Join-Path $LocalDataDir "Files") -PathType Container)) {
    throw "보존 검증용 WPF Files 폴더가 없습니다."
}

$running = @(Get-Process -Name "FlowNote.Windows.App" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw "FlowNote WPF가 실행 중입니다. 앱을 정상 종료한 뒤 다시 실행하세요."
}

$packageRows = @(Import-Csv -LiteralPath $packageEvidencePath)
$lifecycleRows = @(Import-Csv -LiteralPath $lifecyclePath)
$wpfCases = @(
    "framework_clean_install",
    "framework_upgrade",
    "framework_remove",
    "framework_reinstall",
    "framework_rollback",
    "self_contained_clean_install",
    "self_contained_upgrade",
    "self_contained_remove",
    "self_contained_reinstall",
    "self_contained_rollback"
)
foreach ($caseId in $wpfCases) {
    $matching = @($lifecycleRows | Where-Object { $_.case_id -eq $caseId })
    if ($matching.Count -ne 1) {
        throw "설치 수명주기 $caseId 행은 정확히 1개여야 합니다."
    }
    if ($matching[0].result -ne "NOT_RUN") {
        throw "기존 설치 수명주기 원시 증거를 덮어쓰지 않습니다: $caseId"
    }
}

function Get-Package {
    param([string]$Role)

    $rows = @($packageRows | Where-Object { $_.artifact_role -eq $Role })
    if ($rows.Count -ne 1) {
        throw "패키지 원시 증거 $Role 행은 정확히 1개여야 합니다."
    }
    $row = $rows[0]
    if (
        $row.result -ne "PASS" -or
        $row.signature_status -ne "PASS" -or
        $row.chain_status -ne "PASS" -or
        $row.timestamp_status -ne "PASS" -or
        $row.sha256 -ne $row.approved_sha256 -or
        $row.signer_sha256 -ne $row.approved_signer_sha256
    ) {
        throw "패키지 $Role 검증 결과가 승인 상태가 아닙니다."
    }
    $matches = @(
        Get-ChildItem -LiteralPath $artifactRootPath -File -Recurse |
            Where-Object { $_.Name -eq $row.artifact_name }
    )
    if ($matches.Count -ne 1) {
        throw "패키지 $Role 파일은 승인 폴더에 정확히 1개 있어야 합니다."
    }
    $actualHash = (Get-FileHash -LiteralPath $matches[0].FullName -Algorithm SHA256).Hash
    if ($actualHash -ne $row.sha256) {
        throw "패키지 $Role hash가 원시 증거와 다릅니다."
    }
    return [pscustomobject]@{
        Role = $Role
        Path = $matches[0].FullName
        Version = $row.version
    }
}

function Get-DataFingerprint {
    $entries = @(
        Get-ChildItem -LiteralPath $LocalDataDir -File -Recurse |
            Sort-Object FullName |
            ForEach-Object {
                $relative = $_.FullName.Substring(
                    [System.IO.Path]::GetFullPath($LocalDataDir).TrimEnd("\").Length
                ).TrimStart("\").Replace("\", "/")
                $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                "$relative|$($_.Length)|$hash"
            }
    )
    $payload = [Text.Encoding]::UTF8.GetBytes([string]::Join("`n", $entries))
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($payload))).Replace(
            "-",
            ""
        ).ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-InstalledVersion {
    $entries = @()
    foreach ($path in @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )) {
        $entries += @(
            Get-ItemProperty -Path $path -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName -eq "FlowNote Windows Client" }
        )
    }
    $versions = @($entries | ForEach-Object { [string]$_.DisplayVersion } | Sort-Object -Unique)
    if ($versions.Count -gt 1) {
        throw "FlowNote Windows Client 설치 버전이 둘 이상 감지되었습니다."
    }
    return $(if ($versions.Count -eq 0) { "NOT_INSTALLED" } else { $versions[0] })
}

function Protect-MsiLog {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $content = Get-Content -LiteralPath $Path -Raw
    $content = $content -replace '(?i)[a-z]:\\users\\[^\s"'';]+', '<사용자 경로>'
    $content = $content -replace '(?i)https?://[^\s"'';]+', '<서버 주소>'
    $content = $content -replace '(?im)^.*(?:password|token|secret|private[_-]?key).*$',
        '[민감 속성 제거]'
    Set-Content -LiteralPath $Path -Value $content -Encoding utf8
}

function Invoke-MsiStep {
    param(
        [ValidateSet("install", "remove")]
        [string]$Action,
        [pscustomobject]$Package,
        [string]$StepId
    )

    $relativeLog = "install/msi-$StepId.log"
    $logPath = Join-Path $runRoot $relativeLog
    if (Test-Path -LiteralPath $logPath) {
        throw "기존 MSI 로그를 덮어쓰지 않습니다: $relativeLog"
    }
    $operation = if ($Action -eq "install") { "/i" } else { "/x" }
    $arguments = @(
        $operation,
        $Package.Path,
        "/qn",
        "/norestart",
        "/liwearucmop!",
        $logPath
    )
    & "$env:SystemRoot\System32\msiexec.exe" @arguments
    $exitCode = $LASTEXITCODE
    Protect-MsiLog -Path $logPath
    if ($exitCode -ne 0) {
        $failure = [InvalidOperationException]::new(
            "MSI $StepId 단계가 종료 코드 $exitCode로 실패했습니다."
        )
        $failure.Data["ExitCode"] = $exitCode
        $failure.Data["Evidence"] = $relativeLog
        throw $failure
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Evidence = $relativeLog
    }
}

function Save-LifecycleRows {
    $lifecycleRows |
        Select-Object pilot_run_id, case_id, machine_id, dependency_mode,
            package_version, exit_code, data_before_sha256, data_after_sha256,
            data_preserved, observed_version, result, evidence |
        Export-Csv -LiteralPath $lifecyclePath -NoTypeInformation -Encoding utf8
}

function Complete-Case {
    param(
        [string]$CaseId,
        [string]$DependencyMode,
        [pscustomobject]$Package,
        [scriptblock]$Operation,
        [string]$ExpectedVersion
    )

    $before = Get-DataFingerprint
    $stepResults = @()
    $operationError = $null
    try {
        $stepResults = @(& $Operation)
    }
    catch {
        $operationError = $_
        if ($null -ne $_.Exception.Data["Evidence"]) {
            $stepResults += [pscustomobject]@{
                ExitCode = [int]$_.Exception.Data["ExitCode"]
                Evidence = [string]$_.Exception.Data["Evidence"]
            }
        }
    }
    $after = Get-DataFingerprint
    $observed = Get-InstalledVersion
    $exitCode = if ($stepResults.Count -eq 0) { -1 } else { $stepResults[-1].ExitCode }
    $summaryRelative = "install/msi-$CaseId-summary.txt"
    $summaryPath = Join-Path $runRoot $summaryRelative
    if (Test-Path -LiteralPath $summaryPath) {
        throw "기존 MSI 수명주기 요약을 덮어쓰지 않습니다: $summaryRelative"
    }
    @(
        "pilot_run_id=$RunId"
        "case_id=$CaseId"
        "machine_id=$MachineId"
        "package_role=$($Package.Role)"
        "package_version=$($Package.Version)"
        "exit_code=$exitCode"
        "data_before_sha256=$before"
        "data_after_sha256=$after"
        "observed_version=$observed"
        "operation_error=$($null -ne $operationError)"
        "step_logs_begin"
        @($stepResults | ForEach-Object { $_.Evidence })
        "step_logs_end"
    ) | Set-Content -LiteralPath $summaryPath -Encoding utf8
    $passed = (
        $null -eq $operationError -and
        $exitCode -eq 0 -and
        $before -eq $after -and
        $observed -eq $ExpectedVersion
    )
    $row = @($lifecycleRows | Where-Object { $_.case_id -eq $CaseId })[0]
    $row.machine_id = $MachineId
    $row.dependency_mode = $DependencyMode
    $row.package_version = $Package.Version
    $row.exit_code = [string]$exitCode
    $row.data_before_sha256 = $before
    $row.data_after_sha256 = $after
    $row.data_preserved = $before -eq $after
    $row.observed_version = $observed
    $row.result = if ($passed) { "PASS" } else { "FAIL" }
    $row.evidence = $summaryRelative
    Save-LifecycleRows
    if (-not $passed) {
        throw "설치 수명주기 $CaseId 검증에 실패했습니다. 로그와 FAIL 행을 보존하고 배포를 중단하세요."
    }
}

function Invoke-Preparation {
    param([scriptblock]$Operation, [string]$ExpectedVersion)

    $before = Get-DataFingerprint
    & $Operation | Out-Null
    $after = Get-DataFingerprint
    if ($before -ne $after -or (Get-InstalledVersion) -ne $ExpectedVersion) {
        throw "MSI 수명주기 준비 단계에서 데이터 또는 설치 상태가 달라졌습니다."
    }
}

$framework = Get-Package -Role "wpf_framework_msi_candidate"
$selfContained = Get-Package -Role "wpf_self_contained_msi_candidate"
$previous = Get-Package -Role "wpf_msi_previous"
if ((Get-InstalledVersion) -ne "NOT_INSTALLED") {
    throw "깨끗한 snapshot이 아닙니다. 기존 FlowNote 설치를 이 스크립트가 임의 제거하지 않습니다."
}

foreach ($mode in @(
    [pscustomobject]@{
        Name = "framework"
        DependencyMode = "framework-dependent"
        Candidate = $framework
    },
    [pscustomobject]@{
        Name = "self_contained"
        DependencyMode = "self-contained"
        Candidate = $selfContained
    }
)) {
    $name = $mode.Name
    $candidate = $mode.Candidate
    Complete-Case -CaseId "${name}_clean_install" -DependencyMode $mode.DependencyMode `
        -Package $candidate -ExpectedVersion $candidate.Version -Operation {
            Invoke-MsiStep -Action install -Package $candidate -StepId "${name}-clean-install"
        }
    Complete-Case -CaseId "${name}_remove" -DependencyMode $mode.DependencyMode `
        -Package $candidate -ExpectedVersion "NOT_INSTALLED" -Operation {
            Invoke-MsiStep -Action remove -Package $candidate -StepId "${name}-remove"
        }
    Invoke-Preparation -ExpectedVersion $previous.Version -Operation {
        Invoke-MsiStep -Action install -Package $previous -StepId "${name}-upgrade-prepare"
    }
    Complete-Case -CaseId "${name}_upgrade" -DependencyMode $mode.DependencyMode `
        -Package $candidate -ExpectedVersion $candidate.Version -Operation {
            Invoke-MsiStep -Action install -Package $candidate -StepId "${name}-upgrade"
        }
    Invoke-Preparation -ExpectedVersion "NOT_INSTALLED" -Operation {
        Invoke-MsiStep -Action remove -Package $candidate -StepId "${name}-reinstall-prepare"
    }
    Complete-Case -CaseId "${name}_reinstall" -DependencyMode $mode.DependencyMode `
        -Package $candidate -ExpectedVersion $candidate.Version -Operation {
            Invoke-MsiStep -Action install -Package $candidate -StepId "${name}-reinstall"
        }
    Complete-Case -CaseId "${name}_rollback" -DependencyMode $mode.DependencyMode `
        -Package $previous -ExpectedVersion $previous.Version -Operation {
            Invoke-MsiStep -Action remove -Package $candidate -StepId "${name}-rollback-remove"
            Invoke-MsiStep -Action install -Package $previous -StepId "${name}-rollback-install"
        }
    if ($name -eq "framework") {
        Invoke-Preparation -ExpectedVersion "NOT_INSTALLED" -Operation {
            Invoke-MsiStep -Action remove -Package $previous -StepId "self-contained-clean-prepare"
        }
    }
}

Write-Host "WPF MSI 수명주기 원시 증거: $lifecyclePath"
Write-Host "framework-dependent/self-contained 신규 설치·업그레이드·제거·재설치·rollback 완료"
