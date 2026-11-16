You're starting a new research-engineering project with me: a reproducible pipeline and static site that measures court delay in Ontario's courts and the federal courts, framed as a court-resourcing / access-to-justice question. I'm an economist (comfortable in Python and R); treat me as a technical collaborator.

The full specification is in HANDOFF.md, which I've put in this folder. Read it completely before doing anything else. It defines the scope, the three tiers of data sources, the estimands and methods, the repo layout, the guardrails, and the milestones.

For this first session, do Milestone M0 and as much of M1 as is clean:

1. I've already made the repo `bench-time`. Finish setting it up (Python 3.12 with uv, ruff, pytest). Move HANDOFF.md to docs/HANDOFF.md. Write a concise CLAUDE.md capturing the conventions future sessions must follow (tiers, rate limits, provenance, no republishing texts or names, uncertainty on every estimate).
2. Build the shared HTTP client first: on-disk cache of every raw response, single-threaded rate limit (default 4 s for court sites, faster for APIs that allow it), User-Agent read from the env var COURTDELAY_CONTACT, and an append-only data/manifest.jsonl with url, fetched_at, sha256 and status.
3. Verify every Tier 1 and Tier 2 URL/endpoint in the handoff before coding against it (several came from web search and may have moved). For each, record in docs/sources.md: the working URL, format, licence/terms, robots.txt findings, and anything surprising. Do not touch Tier 3 sources at all.
4. Then implement Tier 1 sources in priority order: S1 (StatCan WDS tables), S9 (federal judicial vacancies via Wayback CDX), S8 (federal workload tables), S5 (SCC time lapses), S3 (A2AJ decisions → hearing and decision dates for SCC, FCA, FC, TCC, ONCA), S7 (OCJ PDF panel). Each source gets fetch/parse/validate, a parser test on a saved fixture, and a short data note.

Working style:

- Plan briefly, then build. Commit in small, well-described commits.
- When something in the handoff turns out to be wrong or infeasible, say so plainly, record it in docs/sources.md, and propose the alternative rather than forcing it.
- Ask me before: any Tier 3 source, anything that would publish names or decision text, any request rate faster than the handoff allows, or any cloud/deployment step.
- Stop at the end of the session with a short summary: what works, what's verified vs. not, data coverage per source, and the open questions from section 8 of the handoff that you need me to answer.
