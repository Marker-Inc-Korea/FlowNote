param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^PILOT-\d{8}-\d{4}-[A-Z0-9_-]+-\d{3}$")]
    [string]$RunId,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceRoot,
    [Parameter(Mandatory = $true)]
    [string]$ServerCandidatePath,
    [Parameter(Mandatory = $true)]
    [string]$ServerCandidateSignaturePath,
    [Parameter(Mandatory = $true)]
    [string]$ServerCandidateManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ServerCandidateVersion,
    [Parameter(Mandatory = $true)]
    [string]$ServerCandidateApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$ServerCandidateApprovedSignerSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfMsiCandidatePath,
    [Parameter(Mandatory = $true)]
    [string]$WpfExeCandidatePath,
    [Parameter(Mandatory = $true)]
    [string]$WpfCandidateManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$WpfCandidateVersion,
    [Parameter(Mandatory = $true)]
    [string]$WpfMsiCandidateApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfExeCandidateApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfCandidateApprovedSignerSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfSelfContainedMsiCandidatePath,
    [Parameter(Mandatory = $true)]
    [string]$WpfSelfContainedExeCandidatePath,
    [Parameter(Mandatory = $true)]
    [string]$WpfSelfContainedCandidateManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$WpfSelfContainedMsiCandidateApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfSelfContainedExeCandidateApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfSelfContainedCandidateApprovedSignerSha256,
    [Parameter(Mandatory = $true)]
    [string]$ServerPreviousPath,
    [Parameter(Mandatory = $true)]
    [string]$ServerPreviousSignaturePath,
    [Parameter(Mandatory = $true)]
    [string]$ServerPreviousManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$ServerPreviousVersion,
    [Parameter(Mandatory = $true)]
    [string]$ServerPreviousApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$ServerPreviousApprovedSignerSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfMsiPreviousPath,
    [Parameter(Mandatory = $true)]
    [string]$WpfPreviousManifestPath,
    [Parameter(Mandatory = $true)]
    [string]$WpfPreviousVersion,
    [Parameter(Mandatory = $true)]
    [string]$WpfMsiPreviousApprovedSha256,
    [Parameter(Mandatory = $true)]
    [string]$WpfPreviousApprovedSignerSha256,
    [string]$SignToolPath = "signtool.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FullExistingFile {
    param([string]$Path, [string]$Label)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label 파일이 없습니다: $Path"
    }

    return (Resolve-Path -LiteralPath $Path).Path
}

function Assert-Sha256 {
    param([string]$Value, [string]$Label)

    if ($Value -notmatch "^[0-9a-fA-F]{64}$") {
        throw "$Label 값은 64자리 SHA-256이어야 합니다."
    }
}

function Get-ForbiddenCounts {
    param([string]$ManifestPath)

    $secretCount = 0
    $sqliteCount = 0
    $customerFileCount = 0
    foreach ($rawPath in @(Get-Content -LiteralPath $ManifestPath)) {
        $path = $rawPath.Trim().Replace("\", "/").ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $fileName = [System.IO.Path]::GetFileName($path)
        if (
            $fileName -eq ".env" -or
            $fileName -match "\.(pfx|p12|pem|key|cer|crt)$" -or
            $fileName -match "(secret|credential|password|private[-_]?key|token)"
        ) {
            $secretCount += 1
        }
        if ($fileName -match "\.(sqlite|sqlite3|db)(-(wal|shm))?$") {
            $sqliteCount += 1
        }
        $segments = @($path -split "/" | Where-Object { $_ })
        if (
            $segments -contains "storage" -or
            $segments -contains "files" -or
            $segments -contains "uploads" -or
            $path.Contains("customer") -or
            $fileName -match "\.(hwp|doc|docx|ppt|pptx|xls|xlsx|pdf|dwg|jpg|jpeg|png)$"
        ) {
            $customerFileCount += 1
        }
    }

    return [pscustomobject]@{
        SecretCount = $secretCount
        SqliteCount = $sqliteCount
        CustomerFileCount = $customerFileCount
    }
}

function Get-SignerSha256 {
    param([System.Security.Cryptography.X509Certificates.X509Certificate2]$Certificate)

    if ($null -eq $Certificate) {
        return ""
    }

    return $Certificate.GetCertHashString(
        [System.Security.Cryptography.HashAlgorithmName]::SHA256
    ).ToLowerInvariant()
}

function Test-Artifact {
    param(
        [string]$Role,
        [string]$ArtifactPath,
        [string]$SignaturePath,
        [string]$ManifestPath,
        [string]$Version,
        [string]$ApprovedSha256,
        [string]$ApprovedSignerSha256,
        [string]$RunRoot
    )

    Assert-Sha256 -Value $ApprovedSha256 -Label "$Role 승인 hash"
    Assert-Sha256 -Value $ApprovedSignerSha256 -Label "$Role 승인 signer"
    $artifact = Get-FullExistingFile -Path $ArtifactPath -Label "$Role 패키지"
    $signatureArtifact = Get-FullExistingFile -Path $SignaturePath -Label "$Role 서명 대상"
    $manifest = Get-FullExistingFile -Path $ManifestPath -Label "$Role 포함 파일 목록"
    $artifactHash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifestHash = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()
    $counts = Get-ForbiddenCounts -ManifestPath $manifest
    $signature = Get-AuthenticodeSignature -LiteralPath $signatureArtifact
    $signerSha256 = Get-SignerSha256 -Certificate $signature.SignerCertificate
    $timestampStatus = if ($null -ne $signature.TimeStamperCertificate) { "PASS" } else { "FAIL" }
    $detachedHashBound = $true
    if ($artifact -ne $signatureArtifact) {
        $signatureContent = Get-Content -LiteralPath $signatureArtifact -Raw
        $detachedHashBound = $signatureContent.ToLowerInvariant().Contains($artifactHash)
    }
    $signatureStatus = if (
        $signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid -and
        $detachedHashBound
    ) { "PASS" } else { "FAIL" }
    $safeRole = $Role -replace "[^A-Za-z0-9_-]", "_"
    $transcriptRelative = "packages/windows-signature-$safeRole.txt"
    $transcript = Join-Path $RunRoot $transcriptRelative
    @(
        "artifact_name=$([System.IO.Path]::GetFileName($artifact))"
        "artifact_sha256=$artifactHash"
        "signature_artifact_name=$([System.IO.Path]::GetFileName($signatureArtifact))"
        "signer_sha256=$signerSha256"
        "manifest_name=$([System.IO.Path]::GetFileName($manifest))"
        "manifest_sha256=$manifestHash"
        "detached_hash_bound=$detachedHashBound"
        "authenticode_status=$($signature.Status)"
        "secret_count=$($counts.SecretCount)"
        "sqlite_count=$($counts.SqliteCount)"
        "customer_file_count=$($counts.CustomerFileCount)"
        "manifest_entries_begin"
    ) | Out-File -LiteralPath $transcript -Encoding utf8
    Get-Content -LiteralPath $manifest |
        Out-File -LiteralPath $transcript -Encoding utf8 -Append
    "manifest_entries_end" |
        Out-File -LiteralPath $transcript -Encoding utf8 -Append
    & $SignToolPath verify /pa /all /v $signatureArtifact *>&1 |
        Out-File -LiteralPath $transcript -Encoding utf8 -Append
    $signToolPassed = $LASTEXITCODE -eq 0
    $chainStatus = if ($signToolPassed) { "PASS" } else { "FAIL" }
    $result = if (
        $artifactHash -eq $ApprovedSha256.ToLowerInvariant() -and
        $signerSha256 -eq $ApprovedSignerSha256.ToLowerInvariant() -and
        $signatureStatus -eq "PASS" -and
        $chainStatus -eq "PASS" -and
        $timestampStatus -eq "PASS" -and
        $counts.SecretCount -eq 0 -and
        $counts.SqliteCount -eq 0 -and
        $counts.CustomerFileCount -eq 0
    ) { "PASS" } else { "FAIL" }

    return [pscustomobject][ordered]@{
        pilot_run_id = $RunId
        artifact_role = $Role
        artifact_name = [System.IO.Path]::GetFileName($artifact)
        version = $Version
        sha256 = $artifactHash
        approved_sha256 = $ApprovedSha256.ToLowerInvariant()
        signer_sha256 = $signerSha256
        approved_signer_sha256 = $ApprovedSignerSha256.ToLowerInvariant()
        signature_status = $signatureStatus
        chain_status = $chainStatus
        timestamp_status = $timestampStatus
        secret_count = $counts.SecretCount
        sqlite_count = $counts.SqliteCount
        customer_file_count = $counts.CustomerFileCount
        result = $result
        evidence = $transcriptRelative
    }
}

if (-not (Get-Command $SignToolPath -ErrorAction SilentlyContinue)) {
    throw "signtool을 찾을 수 없습니다: $SignToolPath"
}

$runRoot = Join-Path ([System.IO.Path]::GetFullPath($EvidenceRoot)) $RunId
$packagesRoot = Join-Path $runRoot "packages"
New-Item -ItemType Directory -Force -Path $packagesRoot | Out-Null
$output = Join-Path $packagesRoot "windows-server-packages.csv"
if (Test-Path -LiteralPath $output) {
    $existingRows = @(Import-Csv -LiteralPath $output)
    if (@($existingRows | Where-Object { $_.result -ne "NOT_RUN" }).Count -gt 0) {
        throw "기존 원시 증거를 덮어쓰지 않습니다: $output"
    }
}

$artifacts = @(
    @{
        Role = "server_candidate"
        ArtifactPath = $ServerCandidatePath
        SignaturePath = $ServerCandidateSignaturePath
        ManifestPath = $ServerCandidateManifestPath
        Version = $ServerCandidateVersion
        ApprovedSha256 = $ServerCandidateApprovedSha256
        ApprovedSignerSha256 = $ServerCandidateApprovedSignerSha256
    },
    @{
        Role = "wpf_framework_msi_candidate"
        ArtifactPath = $WpfMsiCandidatePath
        SignaturePath = $WpfMsiCandidatePath
        ManifestPath = $WpfCandidateManifestPath
        Version = $WpfCandidateVersion
        ApprovedSha256 = $WpfMsiCandidateApprovedSha256
        ApprovedSignerSha256 = $WpfCandidateApprovedSignerSha256
    },
    @{
        Role = "wpf_framework_exe_candidate"
        ArtifactPath = $WpfExeCandidatePath
        SignaturePath = $WpfExeCandidatePath
        ManifestPath = $WpfCandidateManifestPath
        Version = $WpfCandidateVersion
        ApprovedSha256 = $WpfExeCandidateApprovedSha256
        ApprovedSignerSha256 = $WpfCandidateApprovedSignerSha256
    },
    @{
        Role = "wpf_self_contained_msi_candidate"
        ArtifactPath = $WpfSelfContainedMsiCandidatePath
        SignaturePath = $WpfSelfContainedMsiCandidatePath
        ManifestPath = $WpfSelfContainedCandidateManifestPath
        Version = $WpfCandidateVersion
        ApprovedSha256 = $WpfSelfContainedMsiCandidateApprovedSha256
        ApprovedSignerSha256 = $WpfSelfContainedCandidateApprovedSignerSha256
    },
    @{
        Role = "wpf_self_contained_exe_candidate"
        ArtifactPath = $WpfSelfContainedExeCandidatePath
        SignaturePath = $WpfSelfContainedExeCandidatePath
        ManifestPath = $WpfSelfContainedCandidateManifestPath
        Version = $WpfCandidateVersion
        ApprovedSha256 = $WpfSelfContainedExeCandidateApprovedSha256
        ApprovedSignerSha256 = $WpfSelfContainedCandidateApprovedSignerSha256
    },
    @{
        Role = "server_previous"
        ArtifactPath = $ServerPreviousPath
        SignaturePath = $ServerPreviousSignaturePath
        ManifestPath = $ServerPreviousManifestPath
        Version = $ServerPreviousVersion
        ApprovedSha256 = $ServerPreviousApprovedSha256
        ApprovedSignerSha256 = $ServerPreviousApprovedSignerSha256
    },
    @{
        Role = "wpf_msi_previous"
        ArtifactPath = $WpfMsiPreviousPath
        SignaturePath = $WpfMsiPreviousPath
        ManifestPath = $WpfPreviousManifestPath
        Version = $WpfPreviousVersion
        ApprovedSha256 = $WpfMsiPreviousApprovedSha256
        ApprovedSignerSha256 = $WpfPreviousApprovedSignerSha256
    }
)

$results = foreach ($artifact in $artifacts) {
    Test-Artifact @artifact -RunRoot $runRoot
}
$results | Export-Csv -LiteralPath $output -NoTypeInformation -Encoding utf8
$failed = @($results | Where-Object { $_.result -ne "PASS" })
Write-Host "패키지 원시 증거: $output"
Write-Host "패키지 불일치: $($failed.Count)건"
if ($failed.Count -gt 0) {
    throw "Windows/서버 패키지 검증에 실패했습니다."
}
