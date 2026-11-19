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
backup location from the `RESTIC_REPOSITORY` environment variable and the password from a file
outside the repository; neither is stored here. With the code in this repository and a restored
`data/raw`, `uv run courtdelay fetch <source> --no-fetch` and `uv run courtdelay build` rebuild
every table.
