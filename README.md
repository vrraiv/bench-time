# bench-time — Court Delay Observatory

Reproducible pipeline (and, later, a static site) measuring how long cases take in Ontario's
courts and the federal courts, framed as a court-resourcing / access-to-justice question.

- Spec: `docs/HANDOFF.md`. Conventions for coding sessions: `CLAUDE.md`.
- Verified sources, terms and robots findings: `docs/sources.md`. Estimands: `docs/methods.md`.

## Quick start

```
uv sync                       # Python 3.12 env (uv.toml uses copy link mode)
export COURTDELAY_CONTACT="you@example.org"   # goes into the User-Agent; required for Tier 2
uv run pytest
uv run courtdelay list        # registered sources
uv run courtdelay fetch s1    # fetch + parse + validate one source (cached, rate-limited)
uv run courtdelay fetch s9 --no-fetch   # re-parse cached raw files only
```

`data/manifest.jsonl` (also gitignored; backed up with the raw files); processed Parquet goes to `data/processed/` (gitignored).
`data/manifest.jsonl`; processed Parquet goes to `data/processed/` (gitignored).

## Backups

`scripts/backup.sh` makes encrypted restic backups of `data/raw` and the request log. It reads the
backup location from the `COURTDELAY_RESTIC_REPOSITORY` environment variable (a project-specific
name, so other projects on the same machine cannot write here by accident) and the password from a file
outside the repository; neither is stored here. With the code in this repository and a restored
`data/raw`, `uv run courtdelay fetch <source> --no-fetch` and `uv run courtdelay build` rebuild
every table.

## Scheduled refreshes

Three refreshes run on their own; none of them commits to `main`.

- **Weekly, on the owner's machine** (`scripts/weekly_refresh.ps1`, Sunday night): the court-file
  sources (Federal Court and Federal Court of Appeal, Tax Court, Supreme Court), then a backup.
- **Monthly, on GitHub Actions** (`.github/workflows/statcan-refresh.yml`): Statistics Canada tables.
- **Quarterly, on GitHub Actions** (`.github/workflows/court-pages-refresh.yml`): the statistics
  pages the courts publish (Supreme Court, Ontario Court of Justice, Federal Court, Federal Court
  of Appeal) and federal judicial vacancies.

The GitHub runs open a pull request only when a published table's data has changed. After merging
one, bring the local copy in line before the next local build:
`uv run courtdelay fetch <source> --refresh` (for example `s8`). `--refresh` requests open-data
pages again even when they are cached; a failed answer never replaces a good cached copy.
