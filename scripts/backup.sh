#!/usr/bin/env bash
# Encrypted, incremental backup of data/raw and the request log with restic (owner decision 2026-11-17).
#
#   scripts/backup.sh init     create the repository (once)
#   scripts/backup.sh          back up data/raw + data/manifest.jsonl, then a quick integrity check
#   scripts/backup.sh verify   deeper check: read 5% of packs + restore 25 random cached
#                              responses and compare their SHA-256 with the fetch-time sidecars
#   scripts/backup.sh list     list snapshots
#
# Repository: $RESTIC_REPOSITORY (required; set it as a user environment variable on the machine
# that runs backups, pointing at a folder that syncs off the device). Password: from
# $RESTIC_PASSWORD_FILE (preferred; a file OUTSIDE the repo, e.g. %USERPROFILE%\.restic-courtdelay)
# or $RESTIC_PASSWORD. Never commit or print the password. If it is lost, the backup is unreadable.
# data/raw contains party names in raw court responses; restic encrypts before anything leaves the PC.
# Snapshots are never pruned by this script.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${RESTIC_REPOSITORY:-}" ]; then
  echo "RESTIC_REPOSITORY is not set: point it at the backup folder (see the header)."; exit 2
fi
export RESTIC_REPOSITORY

RESTIC="$(command -v restic || true)"
if [ -z "$RESTIC" ]; then
  for c in "$LOCALAPPDATA/Microsoft/WinGet/Links/restic.exe" \
           "/c/Users/$USERNAME/AppData/Local/Microsoft/WinGet/Links/restic.exe"; do
    [ -f "$c" ] && RESTIC="$c" && break
  done
fi
[ -n "$RESTIC" ] || { echo "restic not found (winget install restic.restic)"; exit 2; }

if [ -z "${RESTIC_PASSWORD_FILE:-}" ] && [ -z "${RESTIC_PASSWORD:-}" ]; then
  default_pw="${USERPROFILE:-$HOME}/.restic-courtdelay"
  if [ -f "$default_pw" ]; then
    export RESTIC_PASSWORD_FILE="$default_pw"
  else
    echo "No restic password: set RESTIC_PASSWORD_FILE or create $default_pw (one line)."; exit 2
  fi
fi

cmd="${1:-backup}"
case "$cmd" in
  init)
    "$RESTIC" init
    ;;
  backup)
    cd "$ROOT"
    # the request log sits beside data/raw and is not in git: back it up with the raw files
    "$RESTIC" backup data/raw data/manifest.jsonl --tag bench-time --host bench-time-local \
      --exclude "data/raw/**/*.part"
    "$RESTIC" check
    "$RESTIC" snapshots --latest 3
    ;;
  verify)
    cd "$ROOT"
    "$RESTIC" check --read-data-subset=5%
    # restore-test: dump random cached responses from the latest snapshot and compare SHA-256
    # with the sidecar recorded at fetch time
    ok=0; bad=0
    for meta in $(ls data/raw/s1[02]_*/*.meta.json data/raw/s[5-9]_*/*.meta.json 2>/dev/null | shuf -n 25); do
      file="$(dirname "$meta")/$(grep -o '"file": "[^"]*"' "$meta" | cut -d'"' -f4)"
      want="$(grep -o '"sha256": "[^"]*"' "$meta" | cut -d'"' -f4)"
      # backups run from the repo root with a relative path, so snapshots store /data/raw/...
      # MSYS_NO_PATHCONV stops Git Bash rewriting "/data/raw/..." into a C:\ path
      got="$(MSYS_NO_PATHCONV=1 "$RESTIC" dump latest "/$file" 2>/dev/null | sha256sum | cut -d' ' -f1 || true)"
      if [ "$got" = "$want" ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "MISMATCH $file"; fi
    done
    echo "restore test: $ok ok, $bad mismatched (files newer than the latest snapshot also show as mismatched)"
    ;;
  list)
    "$RESTIC" snapshots
    ;;
  *)
    echo "usage: $0 [init|backup|verify|list]"; exit 2
    ;;
esac
