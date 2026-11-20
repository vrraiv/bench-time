# Weekly refresh of the docket sources, then an encrypted backup (owner decision 2026-11-19).
#
# Run by Windows Task Scheduler overnight on Sunday; can also be run by hand:
#   pwsh -File scripts\weekly_refresh.ps1            full weekly run
#   pwsh -File scripts\weekly_refresh.ps1 -NewOnly   new filings only (short)
#   pwsh -File scripts\weekly_refresh.ps1 -DryRun    print what would run, start nothing
#
# The three court sites (Federal Court, Tax Court, Supreme Court) are different hosts, so their
# refreshes run side by side, one process per
# host, each at its own approved request spacing.
#
# When they have all finished, the open-data pages that change in place (Statistics Canada
# tables, the courts' statistics pages, judicial vacancies) are requested again, one source
# after another in a single process (owner decision 2026-11-20). This waits for the court-file
# refreshes because some of those pages are on the same hosts (www.fct-cf.ca, www.scc-csc.ca),
# and only one process may talk to a host at a time. Skipped with -NewOnly. It keeps this
# machine in line with the GitHub refreshes; see site/src/data/source_vintage.json.
#
# Needs the user environment variables
# COURTDELAY_CONTACT (court sites are refused without it) and COURTDELAY_RESTIC_REPOSITORY
# (backup).
# Parsing and rebuilding tables is a separate monthly step: `courtdelay fetch s10 --no-fetch`,
# `courtdelay fetch s12 --no-fetch`, `courtdelay fetch s13 --no-fetch`, `courtdelay build`.
param(
    [switch]$NewOnly,
    [switch]$DryRun,
    [int]$MaxMinutes = 420
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$logDir = Join-Path $root 'data\raw\refresh_logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$summary = Join-Path $logDir "weekly_$stamp.txt"

function Write-Summary([string]$line) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $line" | Tee-Object -FilePath $summary -Append
}

foreach ($name in 'COURTDELAY_CONTACT', 'COURTDELAY_RESTIC_REPOSITORY') {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        Write-Summary "STOPPED: environment variable $name is not set"
        exit 2
    }
}

$extra = @('--max-minutes', "$MaxMinutes")
if ($NewOnly) { $extra += '--new-only' }
$procs = @()
foreach ($court in 'fc', 'tcc', 'scc') {
    $uvArgs = @('run', '--no-sync', 'courtdelay', 'refresh', $court) + $extra
    $out = Join-Path $logDir "weekly_${stamp}_$court.log"
    if ($DryRun) {
        Write-Summary "would run: uv $($uvArgs -join ' ')  > $out"
        continue
    }
    Write-Summary "starting $court refresh"
    $procs += [pscustomobject]@{
        Court = $court
        Proc  = Start-Process -FilePath 'uv' -ArgumentList $uvArgs -NoNewWindow -PassThru `
            -RedirectStandardOutput "$out.stdout" -RedirectStandardError $out
    }
}
$openData = if ($NewOnly) { @() } else { 's1', 's2', 's5', 's7', 's8', 's9' }
if ($DryRun) {
    foreach ($src in $openData) {
        Write-Summary "would run after the court refreshes: uv run --no-sync courtdelay fetch $src --refresh"
    }
    Write-Summary 'would run: bash scripts/backup.sh'
    exit 0
}

$failed = $false
foreach ($p in $procs) {
    $p.Proc.WaitForExit()
    $code = $p.Proc.ExitCode
    if ($code -ne 0) { $failed = $true }
    Write-Summary "$($p.Court) refresh finished, exit code $code"
}
# the last line each refresh wrote to the shared status log (counts; no file numbers or names)
Get-Content (Join-Path $root 'data\raw\refresh_log.jsonl') -Tail 3 | ForEach-Object { Write-Summary $_ }

# open-data pages that change in place: only now, when no other process is on those hosts
foreach ($src in $openData) {
    $out = Join-Path $logDir "weekly_${stamp}_opendata_$src.log"
    & uv run --no-sync courtdelay fetch $src --refresh *> $out
    $code = $LASTEXITCODE
    if ($code -ne 0) { $failed = $true }
    Write-Summary "open-data refresh $src finished, exit code $code"
}

Write-Summary 'starting backup'
# Git's bash, not the WSL launcher that plain `bash` resolves to on Windows
$gitBash = Join-Path (Split-Path -Parent (Split-Path -Parent (Get-Command git).Source)) 'bin\bash.exe'
if (-not (Test-Path $gitBash)) {
    Write-Summary "STOPPED: Git bash not found at $gitBash; backup not run"
    exit 3
}
& $gitBash scripts/backup.sh *> (Join-Path $logDir "weekly_${stamp}_backup.log")
$backupCode = $LASTEXITCODE
Write-Summary "backup finished, exit code $backupCode"
if ($backupCode -ne 0) { $failed = $true }

Write-Summary ($(if ($failed) { 'WEEKLY REFRESH FINISHED WITH PROBLEMS' } else { 'weekly refresh finished cleanly' }))
exit ([int]$failed)
