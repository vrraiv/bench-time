# bench-time — conventions for Claude Code sessions

Court Delay Observatory: a reproducible pipeline + static site measuring court delay in
Ontario's courts and the federal courts, framed as a court-resourcing / access-to-justice
question. Full spec: `docs/HANDOFF.md` (read it before non-trivial work). Verified source
status: `docs/sources.md`. Estimand definitions: `docs/methods.md`.

The owner is an economist and a technical collaborator. Plan briefly, build, commit small.

## Tooling

- Python 3.12 via `uv` (`.python-version` pins it; system Python is 3.14 — don't use it).
- `uv run pytest`, `uv run ruff check . && uv run ruff format .` before every commit.
- `Makefile` targets are thin wrappers over `uv run courtdelay ...`; `make` is not installed
  on the dev machine, so run the underlying `uv run` commands directly.
- Polars + PyArrow; all processed data is Parquet under `data/processed/` (gitignored).
- Each source lives in `src/courtdelay/sources/<id>_<name>.py` with `fetch()`, `parse()`,
  `validate()`, a parser test on a saved fixture in `tests/fixtures/<id>/`, and a data note in
  `docs/sources.md`.

## Source tiers (non-negotiable)

- **Tier 1** (open data: StatCan WDS, A2AJ, Refugee Law Lab, SCC/ONCA/OCJ/federal-court
  statistics pages, FJA vacancy tables via Wayback): build freely, politely.
- **Tier 2** (FC/FCA/TCC docket sites): read robots.txt and terms first and record them in
  `docs/sources.md`; ≥3–5 s between requests, single-threaded; drop party names at parse time.
  The HTTP client refuses docket hosts while `COURTDELAY_CONTACT` is unset.
- **Tier 3** (SCJ Calendly, ontariocourtdates.ca, CanLII texts, Ontario Courts Public Portal):
  **zero requests of any kind** — not even robots.txt, WebFetch, or browser tools — without
  the owner's explicit go-ahead in the current session.

## HTTP and provenance

- All network access goes through `courtdelay.common.http.Client`. Never use `httpx`/`requests`
  directly in a source module. No parallel fetching (the rate limiter is in-process).
- Default rate limit is 4 s per host; faster only for hosts on the explicit API allowlist in
  `common/http.py`. Never go faster than the handoff allows without asking.
  `www.fct-cf.ca` runs at 3 s (owner approval 2026-11-16). One crawl process per host at a time;
  crawls on different hosts (e.g. Tax Court alongside Federal Court) may run in parallel.
- User-Agent is `bench-time/<version> (court-delay research; <COURTDELAY_CONTACT>)`. The contact
  comes only from the env var — never hardcode an address.
- Every raw response is cached on disk under `data/raw/<source>/` and logged to
  `data/manifest.jsonl` (append-only: url, fetched_at, sha256, status). Only 2xx responses
  are served from cache. Nothing is fetched twice.
- If a host returns 403/429 or a bot challenge: stop, record it in `docs/sources.md`, report.
  Do not change User-Agent or switch to a browser to get around it.

## Publishing guardrails

- Publish aggregates and derived fields only. Never publish party names, full decision texts,
  or document copies — not on the site, not in `data/processed` exports, not in test fixtures
  (git history is permanent; the repo may become public). Fixtures use header-only excerpts
  with names redacted or synthetic text modelled on real headers.
- Licences: A2AJ and Refugee Law Lab are CC BY-NC 4.0 + upstream court terms (non-commercial,
  attribution, not search-indexable). StatCan is Open Government Licence. Attribute everything.
- Drop any record carrying a sealing / publication-ban marker.
  Exception (owner, 2026-11-19): Federal Court and FCA docket files (S10) are kept even when an
  entry carries a confidentiality marker; the markers are counted per file. Pending practitioner
  review of what the markers mean.
- Derived aggregate tables in `site/src/data/` are committed (owner decision 2026-11-16) with the
  attribution table in `site/src/data/README.md`. Per-decision or per-docket rows are not.
- A2AJ `upstream_license` reading (owner, 2026-11-16): no commercial use, no full-text reproduction.
- No individual names in published results (owner, 2026-11-18): this includes judges. Judge names
  may be used as a linking key in `data/processed/` but never appear in site tables, charts or text;
  per-judge figures are published only as anonymous distributions.

## Statistics

- Every published estimate carries: definition, n, uncertainty (CI or range), data vintage,
  source, and a plain bias statement ("completed cases only", "published decisions only",
  "lower bound", "steady-state approximation").
- Prefer distributions (median, p75, p90) over means. Descriptive unless a design is stated.
- Validate parsers loudly: report parse rates per court-year; never drop misses silently.

## Working style

- When the handoff is wrong or infeasible, say so plainly, record it in `docs/sources.md`,
  propose an alternative; don't force it.
- Ask before: any Tier 3 source, publishing names or texts, faster request rates, any
  cloud/deployment/scheduling step.
- End each session with: what works, verified vs. not, data coverage per source, open questions.
