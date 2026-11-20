# Weekly refresh of the docket sources, then an encrypted backup (owner decision 2026-11-19).
#
# Run by Windows Task Scheduler overnight on Sunday; can also be run by hand:
#   pwsh -File scripts\weekly_refresh.ps1            full weekly run
#   pwsh -File scripts\weekly_refresh.ps1 -NewOnly   new filings only (short)
#   pwsh -File scripts\weekly_refresh.ps1 -DryRun    print what would run, start nothing
#
# The two court sites are different hosts, so their refreshes run side by side, one process per
# host, each at its own approved request spacing. Needs the user environment variables
# COURTDELAY_CONTACT (court sites are refused without it) and COURTDELAY_RESTIC_REPOSITORY
# (backup).
# Parsing and rebuilding tables is a separate monthly step: `courtdelay fetch s10 --no-fetch`,
# `courtdelay fetch s12 --no-fetch`, `courtdelay build`.
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
foreach ($court in 'fc', 'tcc') {
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
if ($DryRun) {
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
Get-Content (Join-Path $root 'data\raw\refresh_log.jsonl') -Tail 2 | ForEach-Object { Write-Summary $_ }

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
