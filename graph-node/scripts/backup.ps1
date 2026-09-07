<#
.SYNOPSIS
    Uploads the share drive to S3 and logs the result. For Task Scheduler.

.DESCRIPTION
    Wraps `python -m graph_node.backup`. Separate from rebuild.ps1 on purpose:
    the backup only needs S3 on port 443, while the rebuild needs Bolt on 7687,
    so the backup can run on a schedule today even where the rebuild cannot.

    Uploading is additive and re-runnable. Anything already in the bucket at the
    same size is skipped, so an interrupted run costs nothing but time.

    Exit code is passed through, so Task Scheduler's "Last Run Result" means
    something:
        0  uploaded, or dry run with nothing wrong
        1  one or more files failed to upload - read the log
        2  S3_BUCKET unset, or the share root is not reachable (drive unmapped)
        3  another run was still going; this one did nothing

.PARAMETER DryRun
    Report what would be uploaded without uploading. Use this first.

.PARAMETER ShareRoot
    Drive or directory holding peakFit, OpusConvert_lgRfl, and the rest.
    Defaults to SHARE_ROOT from .env.

.EXAMPLE
    .\backup.ps1 -DryRun
    .\backup.ps1 -ShareRoot "X:\"
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$ShareRoot,
    [int]$KeepLogs = 60
)

$ErrorActionPreference = "Stop"

# Parent of scripts/, so this works whatever Task Scheduler thinks the working
# directory is.
$PackageRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $PackageRoot "logs"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# A full upload can outlast the six-hour interval. Two concurrent runs would
# not corrupt anything - uploads are idempotent - but they would both walk the
# share and re-upload the same files, so let the first one finish.
$LockFile = Join-Path $LogDir ".backup.lock"
if (Test-Path $LockFile) {
    $held = Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1
    $alive = $null
    if ($held) { $alive = Get-Process -Id $held -ErrorAction SilentlyContinue }
    if ($alive) {
        Write-Output "A backup is already running (pid $held). Doing nothing."
        exit 3
    }
    # Lock left behind by a run that died. Safe to take over.
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
$PID | Out-File -FilePath $LockFile -Encoding ascii

try {
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $Mode = if ($DryRun) { "dryrun" } else { "apply" }
    $LogFile = Join-Path $LogDir "backup_${Stamp}_${Mode}.log"

    Set-Location $PackageRoot

    $cliArgs = @("run", "python", "-m", "graph_node.backup")
    if (-not $DryRun) { $cliArgs += "--apply" }
    if ($ShareRoot)   { $cliArgs += @("--share-root", $ShareRoot) }

    "=== cataverse S3 backup ===" | Tee-Object -FilePath $LogFile
    "started : $(Get-Date -Format 'u')" | Tee-Object -FilePath $LogFile -Append
    "mode    : $Mode" | Tee-Object -FilePath $LogFile -Append
    "machine : $env:COMPUTERNAME" | Tee-Object -FilePath $LogFile -Append
    "" | Tee-Object -FilePath $LogFile -Append

    & uv @cliArgs 2>&1 | Tee-Object -FilePath $LogFile -Append
    $code = $LASTEXITCODE

    "" | Tee-Object -FilePath $LogFile -Append
    "finished: $(Get-Date -Format 'u')  exit=$code" | Tee-Object -FilePath $LogFile -Append

    Get-ChildItem $LogDir -Filter "backup_*.log" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $KeepLogs |
        Remove-Item -Force -ErrorAction SilentlyContinue

    exit $code
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
