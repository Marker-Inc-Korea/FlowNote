param(
    [ValidatePattern("^$|^PILOT-\d{8}-\d{4}-[A-Z0-9_-]+-\d{3}$")]
    [string]$RunId = "",
    [string]$EvidenceRoot = "D:\FlowNotePilotEvidence",
    [string]$ProductVersion = "0.1.0",
    [string]$Runtime = "win-x64",
    [string]$ArtifactRoot = "artifacts\wpf-msi",
    [string]$InstallFolder = "C:\Program Files\FlowNote\Client\FlowNote.Windows.App",
    [string]$LocalDataDir = "C:\FlowNote\LocalData",
    [switch]$SelfContained,
    [switch]$CheckSignature,
    [string]$SignToolPath = "signtool.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifactRootPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ArtifactRoot))
if (-not [string]::IsNullOrWhiteSpace($RunId)) {
    & (Join-Path $PSScriptRoot "invoke-wpf-msi-lifecycle.ps1") `
        -RunId $RunId `
        -EvidenceRoot $EvidenceRoot `
        -ArtifactRoot $artifactRootPath `
        -InstallFolder $InstallFolder `
        -LocalDataDir $LocalDataDir
    return
}
$packageSuffix = if ($SelfContained.IsPresent) { "$ProductVersion-$Runtime-self-contained" } else { "$ProductVersion-$Runtime" }
$msiPath = Join-Path $artifactRootPath "FlowNote.Windows.App-$packageSuffix.msi"
$manifestPath = Join-Path $artifactRootPath "FlowNote.Windows.App-$packageSuffix.files.txt"
$modeName = if ($SelfContained.IsPresent) { "self-contained" } else { "framework-dependent" }
$publishPath = Join-Path $artifactRootPath "publish\FlowNote.Windows.App-$modeName"
$exePath = Join-Path $publishPath "FlowNote.Windows.App.exe"

function Write-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail = ""
    )

    $status = if ($Passed) { "PASS" } else { "FAIL" }
    if ([string]::IsNullOrWhiteSpace($Detail)) {
        Write-Host "[$status] $Name"
    }
    else {
        Write-Host "[$status] $Name - $Detail"
    }
}

function Write-RecoveryGuidance {
    param(
        [string]$MissingItem,
        [string]$Owner,
        [string]$NextAction
    )

    Write-Host "[누락 항목] $MissingItem"
    Write-Host "[보존된 데이터] 기존 로컬 DB, 고객 파일, 동기화 대기 기록은 변경하거나 삭제하지 않았습니다."
    Write-Host "[담당자] $Owner"
    Write-Host "[다음 조치] $NextAction"
}

function Test-ForbiddenPackagePath {
    param([string]$RelativePath)

    $path = $RelativePath.Replace("\", "/").ToLowerInvariant()
    $fileName = [System.IO.Path]::GetFileName($path)
    $documentExtensions = @(
        ".hwp",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".pdf",
        ".dwg",
        ".zip",
        ".7z",
        ".rar",
        ".jpg",
        ".jpeg",
        ".png",
        ".txt",
        ".md"
    )

    $forbiddenDirectoryNames = @("data", "files", "storage", "logs")
    $pathSegments = @($path -split "/" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    foreach ($directoryName in $forbiddenDirectoryNames) {
        if ($pathSegments -contains $directoryName) {
            return $true
        }
    }

    if ($fileName -match "\.(sqlite|sqlite3|db)(-(wal|shm))?$" -or $fileName -match "\.(sqlite|sqlite3)-(wal|shm)$") {
        return $true
    }

    if ($path.Contains("test") -or $path.Contains("smoke") -or $path.Contains("sample-registration") -or $path.Contains("customer")) {
        return $true
    }

    foreach ($extension in $documentExtensions) {
        if ($fileName.EndsWith($extension, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Get-RelativePath {
    param(
        [string]$BasePath,
        [string]$Path
    )

    $baseFullPath = [System.IO.Path]::GetFullPath($BasePath).TrimEnd([char]"\", [char]"/")
    $targetFullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $targetFullPath.StartsWith($baseFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is not under base path: $targetFullPath"
    }

    return $targetFullPath.Substring($baseFullPath.Length).TrimStart([char]"\", [char]"/").Replace("\", "/")
}

$failures = 0

$msiExists = Test-Path -LiteralPath $msiPath
Write-Check "MSI 파일 존재" $msiExists $msiPath
if (-not $msiExists) {
    $failures += 1
}
else {
    $msiSha256 = (Get-FileHash -LiteralPath $msiPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Check "MSI SHA-256 계산" $true $msiSha256
}

$fileList = @()
if (Test-Path -LiteralPath $manifestPath) {
    $fileList = @(Get-Content -LiteralPath $manifestPath | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Write-Check "MSI 파일 목록 존재" $true $manifestPath
}
elseif (Test-Path -LiteralPath $publishPath) {
    $fileList = @(
        Get-ChildItem -LiteralPath $publishPath -File -Recurse |
            Where-Object { $_.Extension -notin @(".pdb", ".xml") } |
            ForEach-Object { Get-RelativePath -BasePath $publishPath -Path $_.FullName }
    )
    Write-Check "MSI 파일 목록 존재" $false "manifest가 없어 publish 폴더에서 대체 검사: $publishPath"
}
else {
    Write-Check "MSI 파일 목록 존재" $false "manifest와 publish 폴더가 모두 없습니다."
}

$forbiddenFiles = @($fileList | Where-Object { Test-ForbiddenPackagePath $_ })
Write-Check "MSI 파일 목록 금지 패턴 0건" ($forbiddenFiles.Count -eq 0) "$($forbiddenFiles.Count)건"
if ($forbiddenFiles.Count -gt 0) {
    $failures += 1
    $forbiddenFiles | ForEach-Object { Write-Host "  - $_" }
}

$installFolderExists = Test-Path -LiteralPath $InstallFolder
Write-Check "설치 폴더 존재" $installFolderExists $InstallFolder
if ($installFolderExists) {
    $forbiddenInstalledFiles = @(
        Get-ChildItem -LiteralPath $InstallFolder -File -Recurse |
            ForEach-Object { Get-RelativePath -BasePath $InstallFolder -Path $_.FullName } |
            Where-Object { Test-ForbiddenPackagePath $_ }
    )
    Write-Check "설치 폴더 금지 파일 0건" ($forbiddenInstalledFiles.Count -eq 0) "$($forbiddenInstalledFiles.Count)건"
    if ($forbiddenInstalledFiles.Count -gt 0) {
        $failures += 1
        $forbiddenInstalledFiles | ForEach-Object { Write-Host "  - $_" }
    }
}
else {
    $failures += 1
}

$installDbFiles = @()
if ($installFolderExists) {
    $installDbFiles = @(
        Get-ChildItem -LiteralPath $InstallFolder -File -Recurse |
            Where-Object { $_.Name -match "\.(sqlite|sqlite3|db)(-(wal|shm))?$" -or $_.Name -match "\.(sqlite|sqlite3)-(wal|shm)$" }
    )
}

Write-Check "설치 폴더 로컬 DB 없음" ($installDbFiles.Count -eq 0) "$($installDbFiles.Count)건"
if ($installDbFiles.Count -gt 0) {
    $failures += 1
}

$installFilesFolder = Join-Path $InstallFolder "Files"
Write-Check "설치 폴더 Files 없음" (-not (Test-Path -LiteralPath $installFilesFolder)) $installFilesFolder
if (Test-Path -LiteralPath $installFilesFolder) {
    $failures += 1
}

$localDbPath = Join-Path $LocalDataDir "flownote.local.sqlite"
$localFilesPath = Join-Path $LocalDataDir "Files"
Write-Check "로컬 데이터 DB 위치" (Test-Path -LiteralPath $localDbPath) $localDbPath
Write-Check "로컬 데이터 Files 위치" (Test-Path -LiteralPath $localFilesPath) $localFilesPath
if (-not (Test-Path -LiteralPath $localDbPath) -or -not (Test-Path -LiteralPath $localFilesPath)) {
    $failures += 1
}

$desktopRuntime = $false
try {
    $desktopRuntime = @(& dotnet --list-runtimes 2>$null | Select-String "Microsoft.WindowsDesktop.App 10\.").Count -gt 0
}
catch {
    $desktopRuntime = $false
}

$runtimeLabel = if ($SelfContained.IsPresent) { "self-contained MSI는 .NET 런타임 포함 대상" } else { "framework-dependent MSI 실행 전 필수" }
Write-Check ".NET Windows Desktop Runtime 10 확인" ($SelfContained.IsPresent -or $desktopRuntime) $runtimeLabel
if (-not $SelfContained.IsPresent -and -not $desktopRuntime) {
    $failures += 1
}

$webView2ClientId = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
$webView2Entries = @()
foreach ($registryPath in @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$webView2ClientId",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$webView2ClientId",
    "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$webView2ClientId"
)) {
    if (Test-Path -LiteralPath $registryPath) {
        $entry = Get-ItemProperty -LiteralPath $registryPath -ErrorAction SilentlyContinue
        if (
            $null -ne $entry -and
            -not [string]::IsNullOrWhiteSpace([string]$entry.pv) -and
            [string]$entry.pv -ne "0.0.0.0"
        ) {
            $webView2Entries += [pscustomobject]@{
                Scope = if ($registryPath.StartsWith("HKCU:")) { "현재 사용자" } else { "컴퓨터" }
                Version = [string]$entry.pv
                RegistryPath = $registryPath
            }
        }
    }
}

Write-Check "WebView2 Runtime 확인" ($webView2Entries.Count -gt 0) "$($webView2Entries.Count)건"
if ($webView2Entries.Count -gt 0) {
    $webView2Entries | Format-Table -AutoSize
}
else {
    $failures += 1
    Write-RecoveryGuidance `
        -MissingItem "Microsoft Edge WebView2 Runtime" `
        -Owner "현장 관리자 또는 Windows 설치 담당자" `
        -NextAction "승인된 사내 WebView2 Evergreen Runtime을 설치한 뒤 FlowNote를 다시 실행하고 이 점검을 재실행하세요."
}

if ($CheckSignature.IsPresent) {
    if (-not (Get-Command $SignToolPath -ErrorAction SilentlyContinue)) {
        Write-Check "signtool 확인" $false $SignToolPath
        $failures += 1
    }
    else {
        foreach ($path in @($exePath, $msiPath)) {
            if (-not (Test-Path -LiteralPath $path)) {
                Write-Check "서명 검증 대상 존재" $false $path
                $failures += 1
                continue
            }

            & $SignToolPath verify /pa $path
            $verified = $LASTEXITCODE -eq 0
            Write-Check "signtool verify /pa" $verified $path
            if (-not $verified) {
                $failures += 1
            }
        }
    }
}

if ($failures -gt 0) {
    if (-not $msiExists) {
        Write-RecoveryGuidance `
            -MissingItem "승인된 $modeName MSI" `
            -Owner "배포 패키지 담당자" `
            -NextAction "ProductVersion, Runtime, SelfContained, ArtifactRoot가 승인 패키지와 같은지 확인하세요."
    }
    if (-not $installFolderExists) {
        Write-RecoveryGuidance `
            -MissingItem "FlowNote WPF 설치 폴더" `
            -Owner "Windows 설치 담당자" `
            -NextAction "승인된 MSI의 hash와 signer를 확인한 뒤 관리자 권한 설치 로그와 함께 다시 설치하세요."
    }
    if (-not $SelfContained.IsPresent -and -not $desktopRuntime) {
        Write-RecoveryGuidance `
            -MissingItem ".NET Windows Desktop Runtime 10" `
            -Owner "현장 관리자 또는 Windows 설치 담당자" `
            -NextAction "승인된 .NET Windows Desktop Runtime 10을 설치하거나 승인된 self-contained MSI를 사용하세요."
    }
    Write-Host "[다음 조치] 실패 상태와 설치 로그를 같은 run_id 증거 폴더에 보존하고, 원인을 해결하기 전에는 배포를 계속하지 마세요."
    throw "WPF MSI install verification failed with $failures failure(s)."
}

Write-Host "WPF MSI install verification completed."
