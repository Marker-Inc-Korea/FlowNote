param(
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
$packageSuffix = if ($SelfContained.IsPresent) { "$ProductVersion-$Runtime-self-contained" } else { "$ProductVersion-$Runtime" }
$msiPath = Join-Path $artifactRootPath "FlowNote.Windows.App-$packageSuffix.msi"
$manifestPath = Join-Path $artifactRootPath "FlowNote.Windows.App-$packageSuffix.files.txt"
$publishPath = Join-Path $artifactRootPath "publish\FlowNote.Windows.App"
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

$webView2Entries = @()
foreach ($registryPath in @(
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\*",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\*"
)) {
    if (Test-Path -LiteralPath ($registryPath.TrimEnd("*"))) {
        $webView2Entries += @(
            Get-ItemProperty $registryPath -ErrorAction SilentlyContinue |
                Where-Object { $_.name -like "*WebView2*" } |
                Select-Object name, pv
        )
    }
}

Write-Check "WebView2 Runtime 확인" ($webView2Entries.Count -gt 0) "$($webView2Entries.Count)건"
if ($webView2Entries.Count -gt 0) {
    $webView2Entries | Format-Table -AutoSize
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
    throw "WPF MSI install verification failed with $failures failure(s)."
}

Write-Host "WPF MSI install verification completed."
