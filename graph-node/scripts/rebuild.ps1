<#
.SYNOPSIS
    Runs a graph rebuild and logs the result. Intended for Task Scheduler.

.DESCRIPTION
    Wraps `python -m graph_node.cli` so that a scheduled run leaves a record.
    An unattended job that fails silently looks exactly like a graph with no
    new experiments, which is the thing worth designing against.

    Exit code is passed through, so Task Scheduler's "Last Run Result" is
    meaningful:
        0  rebuild applied (or dry run with nothing wrong)
        1  source data has errors, or the sweep refused to run
        2  source root missing or empty - usually the share drive is not mounted

.PARAMETER DryRun
    Report what would change without writing. Use this for the first run.

.EXAMPLE
    .\rebuild.ps1 -DryRun
    .\rebuild.ps1
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [int]$KeepLogs = 60
)

$ErrorActionPreference = "Stop"

# The package root is the parent of scripts/, so this works regardless of
# where Task Scheduler thinks the working directory is.
$PackageRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $PackageRoot "logs"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Mode = if ($DryRun) { "dryrun" } else { "apply" }
$LogFile = Join-Path $LogDir "rebuild_${Stamp}_${Mode}.log"

Set-Location $PackageRoot

$cliArgs = @("run", "python", "-m", "graph_node.cli")
if (-not $DryRun) { $cliArgs += "--apply" }

"=== cataverse graph rebuild ===" | Tee-Object -FilePath $LogFile
"started : $(Get-Date -Format 'u')" | Tee-Object -FilePath $LogFile -Append
"mode    : $Mode" | Tee-Object -FilePath $LogFile -Append
"machine : $env:COMPUTERNAME" | Tee-Object -FilePath $LogFile -Append
"" | Tee-Object -FilePath $LogFile -Append

& uv @cliArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
$code = $LASTEXITCODE

"" | Tee-Object -FilePath $LogFile -Append
"finished: $(Get-Date -Format 'u')  exit=$code" | Tee-Object -FilePath $LogFile -Append

# Keep the log directory from growing without bound. Four runs a day at the
# default keeps roughly a fortnight.
Get-ChildItem $LogDir -Filter "rebuild_*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLogs |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $code
