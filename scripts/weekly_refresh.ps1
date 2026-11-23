# Weekly refresh of the docket sources, then an encrypted backup (owner decision 2026-11-19).
#
# Run by Windows Task Scheduler overnight on Sunday; can also be run by hand:
#   pwsh -File scripts\weekly_refresh.ps1            full weekly run
#   pwsh -File scripts\weekly_refresh.ps1 -NewOnly   new filings only (short)
#   pwsh -File scripts\weekly_refresh.ps1 -DryRun    print what would run, start nothing
#   pwsh -File scripts\weekly_refresh.ps1 -Monthly   also re-parse the dockets (any day)
#   pwsh -File scripts\weekly_refresh.ps1 -NoPR      skip the build and pull request
#   pwsh -File scripts\weekly_refresh.ps1 -BuildOnly [-Monthly]   only the build and pull request
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
#
# Last step: build the published tables and open a pull request if their data changed (weekly:
# open-data tables; first Sunday of the month: dockets re-parsed too, PR for review). See the
# section at the end. Needs git push access and an authenticated `gh` for this user.
param(
    [switch]$NewOnly,
    [switch]$DryRun,
    [switch]$Monthly,
    [switch]$NoPR,
    [switch]$BuildOnly,
    [int]$MaxMinutes = 420
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$logDir = Join-Path $root 'data\raw\refresh_logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
# monthly rebuild on the first Sunday of the month (the task starts Sunday 23:00), or on request
$now = Get-Date
$isMonthly = $Monthly -or ($now.DayOfWeek -eq 'Sunday' -and $now.Day -le 7)
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

$failed = $false
if (-not $BuildOnly) {
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
    if (-not $NoPR) {
        $what = if ($isMonthly) { 'parse s10, s12, s13 from the cache, then build' } else { 'build' }
        Write-Summary "would $what in the bench-time-auto worktree (origin/main) and open a PR if published tables changed"
    }
    exit 0
}

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
}  # end of the -BuildOnly skip

# --- build the published tables and open a pull request when their data changed -------------
# Runs in a separate git worktree kept on origin/main (sibling folder bench-time-auto) that
# shares this checkout's data folder, so it always builds from main and never touches the
# branch or uncommitted work in this checkout. Weekly: open-data tables only (the docket
# sources are not re-parsed, so their tables cannot change). Monthly: first Sunday of the
# month, or -Monthly: the three docket sources are parsed from the cache first (no requests to
# the courts) and the pull request is marked for review. Owner decisions 2026-11-23.
if (-not $NoPR) {
    $auto = Join-Path (Split-Path -Parent $root) 'bench-time-auto'
    $buildLog = Join-Path $logDir "weekly_${stamp}_build.log"
    $kind = if ($isMonthly) { 'monthly' } else { 'weekly' }
    Write-Summary "starting $kind build in $auto"
    try {
        if (-not (Test-Path $auto)) {
            git -C $root worktree add --detach $auto origin/main *>> $buildLog
        }
        git -C $auto fetch --quiet origin main *>> $buildLog
        git -C $auto checkout --quiet --detach --force origin/main *>> $buildLog
        if ($LASTEXITCODE -ne 0) { throw "could not put the worktree on origin/main" }
        git -C $auto clean -fdq -- site/src/data *>> $buildLog
        Push-Location $auto
        $env:COURTDELAY_DATA_DIR = Join-Path $root 'data'
        & uv sync --frozen *>> $buildLog
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed ($LASTEXITCODE)" }
        if ($isMonthly) {
            foreach ($src in 's10', 's12', 's13') {
                & uv run --no-sync courtdelay fetch $src --no-fetch *>> $buildLog
                if ($LASTEXITCODE -ne 0) { throw "parse $src failed ($LASTEXITCODE)" }
                Write-Summary "parsed $src from the cache"
            }
        }
        & uv run --no-sync courtdelay build *>> $buildLog
        if ($LASTEXITCODE -ne 0) { throw "build failed ($LASTEXITCODE)" }
        $changedFile = Join-Path $logDir "weekly_${stamp}_changed.txt"
        & uv run --no-sync python scripts/tables_changed.py > $changedFile
        if ($LASTEXITCODE -ne 0) { throw "tables_changed failed ($LASTEXITCODE)" }
        $changed = @(Get-Content $changedFile | Where-Object { $_ })
        if ($changed.Count -eq 0) {
            Write-Summary "$kind build: no published table changed; no pull request"
        } else {
            $date = Get-Date -Format 'yyyy-MM-dd'
            $branch = "refresh/$kind-$date"
            git checkout --quiet -B $branch *>> $buildLog
            git add -- $changed 'site/src/data/source_vintage.json' *>> $buildLog
            $title = if ($isMonthly) { "Monthly rebuild $date (review)" } else { "Open-data tables: weekly refresh $date" }
            git commit --quiet -m $title *>> $buildLog
            if ($LASTEXITCODE -ne 0) { throw "commit failed ($LASTEXITCODE)" }
            git push --quiet --force -u origin $branch *>> $buildLog
            if ($LASTEXITCODE -ne 0) { throw "push failed ($LASTEXITCODE)" }
            $body = Join-Path $logDir "weekly_${stamp}_pr.md"
            @(
                $(if ($isMonthly) {
                    'Monthly rebuild: the Federal Court/FCA, Tax Court and Supreme Court files were parsed again from the cache, then all tables rebuilt. Please review before merging.'
                } else {
                    'Weekly rebuild after the open-data refresh (Statistics Canada, the courts'' statistics pages, judicial vacancies). Docket tables are not re-parsed weekly. Usually safe to merge after a look at the changes.'
                }),
                '',
                'Tables whose data changed (a new fetch time alone does not count):',
                '',
                ($changed | ForEach-Object { "- $_" }),
                '',
                "Opened by scripts/weekly_refresh.ps1 (run $stamp). Held-back tables for the review page were rebuilt in the bench-time-auto worktree; upload them with scripts/push_review_data.sh from there if wanted."
            ) | Set-Content -Encoding utf8 $body
            & gh pr create --base main --head $branch --title $title --body-file $body *>> $buildLog
            if ($LASTEXITCODE -ne 0) { & gh pr edit $branch --body-file $body *>> $buildLog }
            Write-Summary "$kind build: $($changed.Count) table(s) changed; pull request on $branch"
        }
    } catch {
        $failed = $true
        Write-Summary "$kind build STOPPED: $($_.Exception.Message) (see $buildLog)"
    } finally {
        Pop-Location -ErrorAction SilentlyContinue
        Remove-Item Env:COURTDELAY_DATA_DIR -ErrorAction SilentlyContinue
    }
}

Write-Summary ($(if ($failed) { 'WEEKLY REFRESH FINISHED WITH PROBLEMS' } else { 'weekly refresh finished cleanly' }))
exit ([int]$failed)
