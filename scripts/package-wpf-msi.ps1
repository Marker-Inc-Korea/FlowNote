param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [string]$ProductVersion = "0.1.0",
    [string]$OutputRoot = "artifacts\wpf-msi"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$projectPath = Join-Path $repoRoot "apps\windows\src\FlowNote.Windows.App\FlowNote.Windows.App.csproj"
$outputRootPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot))
$publishPath = Join-Path $outputRootPath "publish\FlowNote.Windows.App"
$wixPath = Join-Path $outputRootPath "FlowNote.Windows.App.wxs"
$msiPath = Join-Path $outputRootPath "FlowNote.Windows.App-$ProductVersion-$Runtime.msi"
$upgradeCode = "8F1C478A-8D5F-48B9-8B6D-693313E3125C"

if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    throw "WiX Toolset CLI was not found. Install it with: dotnet tool install --global wix"
}

New-Item -ItemType Directory -Force $publishPath | Out-Null

dotnet publish $projectPath `
    -c $Configuration `
    -r $Runtime `
    --self-contained false `
    -o $publishPath

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE."
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
    <MajorUpgrade DowngradeErrorMessage="A newer FlowNote Windows Client is already installed." />
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

Write-Host "Created MSI: $msiPath"
