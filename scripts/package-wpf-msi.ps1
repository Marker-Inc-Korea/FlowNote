param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$ProductVersion = "0.1.0",
    [string]$OutputRoot = "artifacts\wpf-msi",
    [switch]$SelfContained,
    [switch]$EnableWindowsTargeting,
    [switch]$Sign,
    [string]$SignToolPath = "signtool.exe",
    [string]$SigningCertificateThumbprint = "",
    [string]$SigningCertificateSubjectName = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectPath = Join-Path $repoRoot "apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj"
$outputRootPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot))
$publishPath = Join-Path $outputRootPath "publish\FlowNote.Windows.App"
$wixPath = Join-Path $outputRootPath "FlowNote.Windows.App.wxs"
$packageSuffix = if ($SelfContained.IsPresent) { "$ProductVersion-$Runtime-self-contained" } else { "$ProductVersion-$Runtime" }
$msiPath = Join-Path $outputRootPath "FlowNote.Windows.App-$packageSuffix.msi"
$fileManifestPath = Join-Path $outputRootPath "FlowNote.Windows.App-$packageSuffix.files.txt"
$upgradeCode = "8F1C478A-8D5F-48B9-8B6D-693313E3125C"

if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    throw "WiX Toolset CLI was not found. Install it with: dotnet tool install --global wix"
}

if (Test-Path -LiteralPath $publishPath) {
    Remove-Item -LiteralPath $publishPath -Recurse -Force
}

New-Item -ItemType Directory -Force $publishPath | Out-Null

$selfContainedValue = if ($SelfContained.IsPresent) { "true" } else { "false" }
$publishArguments = @(
    "publish",
    $projectPath,
    "-c",
    $Configuration,
    "-r",
    $Runtime,
    "--self-contained",
    $selfContainedValue,
    "-o",
    $publishPath
)
if ($EnableWindowsTargeting.IsPresent) {
    $publishArguments += "-p:EnableWindowsTargeting=true"
}

dotnet @publishArguments

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
}

function Invoke-CodeSign {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Cannot sign missing file: $Path"
    }

    if ([string]::IsNullOrWhiteSpace($SigningCertificateThumbprint) -and [string]::IsNullOrWhiteSpace($SigningCertificateSubjectName)) {
        throw "Signing requires -SigningCertificateThumbprint or -SigningCertificateSubjectName."
    }

    $signArguments = @("sign", "/fd", "SHA256", "/td", "SHA256")
    if (-not [string]::IsNullOrWhiteSpace($TimestampUrl)) {
        $signArguments += @("/tr", $TimestampUrl)
    }

    if (-not [string]::IsNullOrWhiteSpace($SigningCertificateThumbprint)) {
        $signArguments += @("/sha1", $SigningCertificateThumbprint)
    }
    else {
        $signArguments += @("/n", $SigningCertificateSubjectName)
    }

    $signArguments += $Path
    & $SignToolPath @signArguments
    if ($LASTEXITCODE -ne 0) {
        throw "signtool sign failed for $Path with exit code $LASTEXITCODE."
    }
}

function Invoke-CodeSignVerification {
    param([string]$Path)

    $verifyArguments = @("verify", "/pa", $Path)
    & $SignToolPath @verifyArguments
    if ($LASTEXITCODE -ne 0) {
        throw "signtool verify failed for $Path with exit code $LASTEXITCODE."
    }
}

function ConvertTo-WixId {
    param([string]$Value)

    $id = [regex]::Replace($Value, "[^A-Za-z0-9_]", "_")
    if ($id -match "^[0-9]") {
        $id = "x_$id"
    }

    return $id
}

function ConvertTo-XmlAttribute {
    param([string]$Value)

    return [System.Security.SecurityElement]::Escape($Value)
}

function ConvertTo-RelativePublishPath {
    param([string]$Path)

    $basePath = [System.IO.Path]::GetFullPath($publishPath).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    $targetPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $targetPath.StartsWith($basePath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is not under publish directory: $targetPath"
    }

    return $targetPath.Substring($basePath.Length).TrimStart([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
}

$publishedFiles = @(
    Get-ChildItem -LiteralPath $publishPath -File -Recurse |
        Where-Object { $_.Extension -notin @(".pdb", ".xml") } |
        Sort-Object FullName
)
if ($publishedFiles.Count -eq 0) {
    throw "No published files were found in $publishPath"
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

    if ($path.StartsWith("data/") -or $path.StartsWith("files/") -or $path.Contains("/data/") -or $path.Contains("/files/")) {
        return $true
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

$relativePublishedFiles = @(
    $publishedFiles | ForEach-Object { (ConvertTo-RelativePublishPath $_.FullName).Replace("\", "/") }
)
$forbiddenPublishedFiles = @(
    $relativePublishedFiles | Where-Object { Test-ForbiddenPackagePath $_ }
)
if ($forbiddenPublishedFiles.Count -gt 0) {
    $forbiddenList = [string]::Join([Environment]::NewLine, ($forbiddenPublishedFiles | ForEach-Object { "  - $_" }))
    throw "Forbidden files were found in the MSI file set. Remove them from publish output before packaging:$([Environment]::NewLine)$forbiddenList"
}

Set-Content -LiteralPath $fileManifestPath -Value $relativePublishedFiles -Encoding UTF8

if ($Sign.IsPresent) {
    Invoke-CodeSign -Path (Join-Path $publishPath "FlowNote.Windows.App.exe")
    Invoke-CodeSignVerification -Path (Join-Path $publishPath "FlowNote.Windows.App.exe")
}

$directoryIds = @{}
$directoryIds[""] = "APPFOLDER"
$directoryIndex = 0
foreach ($directory in @(Get-ChildItem -LiteralPath $publishPath -Directory -Recurse | Sort-Object FullName)) {
    $relativeDirectory = (ConvertTo-RelativePublishPath $directory.FullName).Replace("\", "/")
    $directoryIndex += 1
    $directoryIds[$relativeDirectory] = ConvertTo-WixId "dir_$directoryIndex`_$relativeDirectory"
}

function New-DirectoryXml {
    param(
        [string]$RelativeDirectory,
        [int]$IndentLevel
    )

    $indent = " " * $IndentLevel
    $children = @(
        $directoryIds.Keys |
            Where-Object {
                if ([string]::IsNullOrEmpty($RelativeDirectory)) {
                    $_ -ne "" -and -not $_.Contains("/")
                }
                else {
                    $_.StartsWith("$RelativeDirectory/") -and ($_.Substring($RelativeDirectory.Length + 1) -notmatch "/")
                }
            } |
            Sort-Object
    )

    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($child in $children) {
        $name = if ($child.Contains("/")) { $child.Split("/")[-1] } else { $child }
        $lines.Add("$indent<Directory Id=`"$($directoryIds[$child])`" Name=`"$(ConvertTo-XmlAttribute $name)`">")
        $childXml = New-DirectoryXml -RelativeDirectory $child -IndentLevel ($IndentLevel + 2)
        if (-not [string]::IsNullOrWhiteSpace($childXml)) {
            $lines.Add($childXml)
        }
        $lines.Add("$indent</Directory>")
    }

    return [string]::Join([Environment]::NewLine, $lines)
}

$directoryXml = New-DirectoryXml -RelativeDirectory "" -IndentLevel 10
$components = New-Object System.Collections.Generic.List[string]
$componentRefs = New-Object System.Collections.Generic.List[string]
$fileIndex = 0
foreach ($file in $publishedFiles) {
    $fileIndex += 1
    $relativePath = (ConvertTo-RelativePublishPath $file.FullName).Replace("\", "/")
    $relativeDirectory = [System.IO.Path]::GetDirectoryName($relativePath)
    if ($null -eq $relativeDirectory) {
        $relativeDirectory = ""
    }

    $relativeDirectory = $relativeDirectory.Replace("\", "/")
    $fileId = ConvertTo-WixId "fil_$fileIndex`_$($file.Name)"
    $componentId = ConvertTo-WixId "cmp_$fileIndex`_$relativePath"
    $directoryId = $directoryIds[$relativeDirectory]
    $source = ConvertTo-XmlAttribute $file.FullName
    $components.Add("    <Component Id=`"$componentId`" Directory=`"$directoryId`" Guid=`"*`"><File Id=`"$fileId`" Source=`"$source`" KeyPath=`"yes`" /></Component>")
    $componentRefs.Add("      <ComponentRef Id=`"$componentId`" />")
}

$componentXml = [string]::Join([Environment]::NewLine, $components)
$componentRefXml = [string]::Join([Environment]::NewLine, $componentRefs)
$wixContent = @"
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="FlowNote Windows Client" Manufacturer="FlowNote" Version="$ProductVersion" UpgradeCode="$upgradeCode" Scope="perMachine">
    <MajorUpgrade DowngradeErrorMessage="더 최신 FlowNote Windows 클라이언트가 설치되어 있습니다. 승인된 rollback 절차 없이 이전 버전을 설치할 수 없습니다." />
    <MediaTemplate EmbedCab="yes" />

    <StandardDirectory Id="ProgramFilesFolder">
      <Directory Id="INSTALLFOLDER" Name="FlowNote">
        <Directory Id="CLIENTFOLDER" Name="Client">
          <Directory Id="APPFOLDER" Name="FlowNote.Windows.App">
$directoryXml
          </Directory>
        </Directory>
      </Directory>
    </StandardDirectory>

    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="ApplicationProgramsFolder" Name="FlowNote" />
    </StandardDirectory>

    <Feature Id="MainFeature" Title="FlowNote Windows Client" Level="1">
      <ComponentGroupRef Id="PublishedFiles" />
      <ComponentRef Id="ApplicationShortcut" />
    </Feature>
  </Package>

  <Fragment>
    <ComponentGroup Id="PublishedFiles">
$componentRefXml
    </ComponentGroup>

$componentXml

    <Component Id="ApplicationShortcut" Directory="ApplicationProgramsFolder" Guid="*">
      <Shortcut Id="ApplicationStartMenuShortcut" Name="FlowNote" Target="[APPFOLDER]FlowNote.Windows.App.exe" WorkingDirectory="APPFOLDER" />
      <RemoveFolder Id="ApplicationProgramsFolder" On="uninstall" />
      <RegistryValue Root="HKCU" Key="Software\FlowNote\FlowNote.Windows.App" Name="installed" Type="integer" Value="1" KeyPath="yes" />
    </Component>
  </Fragment>
</Wix>
"@

Set-Content -LiteralPath $wixPath -Value $wixContent -Encoding UTF8

wix build $wixPath -o $msiPath
if ($LASTEXITCODE -ne 0) {
    throw "WiX build failed with exit code $LASTEXITCODE."
}

if ($Sign.IsPresent) {
    Invoke-CodeSign -Path $msiPath
    Invoke-CodeSignVerification -Path $msiPath
}

Write-Host "Created MSI: $msiPath"
Write-Host "Created package file list: $fileManifestPath"
