param(
    [string]$ServerRoot = "C:\FlowNote\Server"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$serverRootPath = [System.IO.Path]::GetFullPath($ServerRoot)
$apiRoot = Join-Path $serverRootPath "api"
$pythonPath = Join-Path $apiRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $serverRootPath ".env"
$dataRoot = Join-Path $serverRootPath "data"
$storageRoot = Join-Path $serverRootPath "storage"
$logRoot = Join-Path $serverRootPath "logs"
$stdoutLog = Join-Path $logRoot "flownote-api.out.log"
$stderrLog = Join-Path $logRoot "flownote-api.err.log"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        if ($trimmed -notmatch "^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
            continue
        }

        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function ConvertTo-SqliteUrl {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path).Replace("\", "/")
    return "sqlite:///$fullPath"
}

function Set-DefaultEnvironmentVariable {
    param(
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, "Process"))) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

if (-not (Test-Path $apiRoot)) {
    throw "FlowNote API directory was not found: $apiRoot"
}

if (-not (Test-Path $pythonPath)) {
    throw "FlowNote API virtualenv python was not found: $pythonPath"
}

foreach ($directory in @($dataRoot, $storageRoot, $logRoot)) {
    New-Item -ItemType Directory -Force $directory | Out-Null
}

Import-DotEnv $envPath
Set-DefaultEnvironmentVariable "FLOWNOTE_ENV" "production"
Set-DefaultEnvironmentVariable "FLOWNOTE_API_HOST" "0.0.0.0"
Set-DefaultEnvironmentVariable "FLOWNOTE_API_PORT" "5184"
Set-DefaultEnvironmentVariable "FLOWNOTE_DATABASE_URL" (ConvertTo-SqliteUrl (Join-Path $dataRoot "flownote.sqlite3"))
Set-DefaultEnvironmentVariable "FLOWNOTE_STORAGE_ROOT" $storageRoot

$hostName = [Environment]::GetEnvironmentVariable("FLOWNOTE_API_HOST", "Process")
$port = [Environment]::GetEnvironmentVariable("FLOWNOTE_API_PORT", "Process")

Set-Location $apiRoot
& $pythonPath -m uvicorn app.main:app --host $hostName --port $port 1>> $stdoutLog 2>> $stderrLog
