# Handoff: Court Delay Observatory (Ontario + federal courts)

Owner: Vikram Rai · Drafted 2026-11-15 · Status: greenfield, local development first

## 1. What this project is

Build a reproducible pipeline that collects every publicly and lawfully automatable data source on how long cases take in Ontario's courts and the federal courts, estimates wait times and the age of pending cases as well as the data allows, and publishes the results on a static website.

**Research framing: court resourcing.** Delay that comes from waiting for a judge, courtroom or hearing date is an access-to-justice cost created by the institution, not by the parties. The court is a third party to delay, alongside the Crown and defence (criminal) or plaintiff and defendant (civil). Most published statistics cannot separate the three. Wherever possible, the pipeline should produce measures that isolate institutional delay (booking waits, reserve times, delay attributed to "institutional resources" in delay rulings) and link delay to resources (judicial vacancies, complement).

**Standards.** Rigorous and honest. Every estimate carries an uncertainty range, a sample size, a data vintage and a plain statement of its bias (e.g. "lower bound", "completed cases only", "published decisions only"). Prefer distributions (median, p75, p90) over means.

## 2. Courts in scope

Ontario Court of Justice (OCJ), Superior Court of Justice (SCJ, incl. Divisional Court and Small Claims), Court of Appeal for Ontario (ONCA), Federal Court (FC), Federal Court of Appeal (FCA), Tax Court of Canada (TCC), Supreme Court of Canada (SCC). Tribunals are out of scope.

## 3. Data sources, in three tiers

Verify every URL and endpoint below before building against it; several were found via search and may have moved. Record what you find in `docs/sources.md`.

### Tier 1 — open data, build first

| ID | Source | What to extract | Access | Notes |
|---|---|---|---|---|
| S1 | Statistics Canada Integrated Criminal Court Survey tables via the Web Data Service API | Tables 35-10-0029-01 (median elapsed time), 35-10-0027-01 (cases/decisions), 35-10-0173-01 and 35-10-0174-01 (annual key indicators incl. Jordan-ceiling shares), 35-10-0172-01 and 35-10-0176-01 (preliminary quarterly). Ontario and Canada rows | StatCan WDS (JSON/CSV), Open Government Licence | Completed cases only; cannot attribute delay to Crown, defence or court |
| S2 | Statistics Canada Civil Court Survey | Tables 35-10-0112-01, 35-10-0114-01 (Ontario counts by case type) | WDS | Counts, no timing; denominators only |
| S3 | A2AJ Canadian Legal Data (decision texts) | For SCC, FCA, FC, TCC, ONCA: citation, decision date, hearing date(s) parsed from headers, judge(s), file number(s), proceeding type, procedure (TCC informal/general from file-number suffix), lower-court decision date where stated | API `https://api.a2aj.ca/search` and `/fetch`; Hugging Face dataset `a2aj/canadian-case-law` (parquet, per-court `data_dir`); updated weekly | Licence CC BY-NC 4.0 plus upstream court terms; **do not republish full texts or make them indexable**; store only derived fields in published outputs. ONCA is included; ONSC/ONCJ are not |
| S4 | Refugee Law Lab "Luck of the Draw III" | All FC immigration dockets filed 1997–2022 (docket entries with dates) | Hugging Face `refugee-law-lab/luck-of-the-draw-iii` | CC BY-NC 4.0; use as baseline and validation for S9 |
| S5 | SCC Year in Review + historical statistics PDFs | Annual average time lapses: leave filing→leave decision, leave→hearing, hearing→judgment; counts | scc-csc.ca HTML pages (2018+), PDFs 2003–2017 (some only on Library and Archives Canada web archive) | Averages only |
| S6 | ONCA Annual Report (July 2026, first in over a decade) | Civil appeals: filing→ready, ready→hearing, hearing→decision; 2014–2024 trends; leave and outcome counts | PDF from ontariocourts.ca/coa | One-off so far; check for criminal tables |
| S7 | OCJ Court Statistics PDFs | Criminal: cases received/disposed, average days and appearances to disposition, % disposed by months elapsed, clearance rate, by region and courthouse; bail; family and POA counts; Criminal Modernization Committee dashboards | ontariocourts.ca/ocj/statistics/; older years at collections.ola.org (Legislative Assembly archive, series 283147 and 108774) | PDF table extraction (pdfplumber/camelot); expect definition breaks across years; Ministry of the Attorney General collects the data and the court disclaims accuracy |
| S8 | Federal court workload tables | FC quarterly statistics (filed/disposed/pending by type); FCA statistics page; TCC workload + status-at-March-31 table (not perfected, perfected, reserved, awaiting timetable, scheduled, etc.); Courts Administration Service annual reports for earlier years | fct-cf.ca, fca-caf.ca, tcc-cci.ca, cas-satj.gc.ca | Use for stock–flow (Little's law) estimates |
| S9 | Federal judicial complement and vacancies | Monthly "Number of federally appointed judges as of <date>" tables: judges in office, supernumeraries, vacancies, by court (ONCA, ONSC, Ontario Family Court branch, FC, FCA, TCC, SCC) | Commissioner for Federal Judicial Affairs page (`fja.gc.ca/appointments-nominations/judges-juges-eng.aspx`, also served from cmf.gc.ca variants); history via the Wayback Machine CDX API | Monthly snapshots will have gaps; record snapshot timestamps. Law360's 2023 analysis (349 vacancies filled 2019–2023, average fill time 8+ months) is a validation benchmark |

### Tier 2 — court docket sites (build after Tier 1; scraping, be polite)

| ID | Source | What to extract | Notes |
|---|---|---|---|
| S10 | FC "Court Files" docket search + Recorded Entries | For sampled file numbers (T-####-YY general; IMM-####-YY immigration): filing date, proceeding type, every recorded entry with date and summary text → stage dates (leave decision, hearing, judgment, discontinuance) | Sample by filing-year cohort, not from decisions. Extend S4 beyond 2022 and to general proceedings |
| S11 | FCA recorded entries | Same, for FCA files (A-###-YY) | Small volume; full census feasible |
| S12 | TCC docket (case search → docket/clock icon) | For sampled file numbers by year (YYYY-NNNN(IT)G / (IT)I / (GST)G etc.): filing, reply, status hearings, hearing date, judgment, discontinuance, consent judgment | Grant's Substack samples (20 files) are the only prior estimate; ours should be cohort-based with censoring |

Rules for Tier 2: read robots.txt and site terms first and write findings to `docs/sources.md`; one request every 3–5 seconds or slower, single-threaded; descriptive User-Agent with a contact address supplied by Vikram via env var (never hardcode); cache every raw response to disk so nothing is fetched twice; resume-safe; stop and report if blocked. Party names are not needed — drop them at parse time; keep only file number, dates, entry types.

### Tier 3 — do NOT build without Vikram's explicit go-ahead

| Source | Why it is blocked |
|---|---|
| SCJ Calendly booking availability (calendly.com/toronto-region and other regions) | Courtready (courtready.ca, Tom Macintosh Zheng) already monitors this daily; plan is to ask for their series or partner first. Calendly terms unreviewed |
| ontariocourtdates.ca daily court lists | Site terms state the lists may not be collected, copied or distributed; Toronto civil, family and Divisional Court matters were removed from the lists in October 2025 |
| CanLII (ONSC, ONCJ decision texts) | Terms prohibit bulk or systematic downloading; CanLII has sued a scraper; API is metadata-only. Build a clean interface (`sources/canlii_licensed.py` stub) so licensed data can be dropped in later |
| Ontario Courts Public Portal / online case search | Assume prohibited for bulk use; not reviewed |

## 4. Estimands and methods

Define each estimand precisely in `docs/methods.md` and on the site.

1. **Stage durations (FC, FCA, TCC dockets; S10–S12, S4).** Stages: filing → first defence/reply → (leave decision for FC immigration) → hearing scheduled → hearing → decision; and filing → any final disposition (judgment, discontinuance, consent, dismissal). Estimate by filing-year cohort with Kaplan–Meier, censoring open files at the scrape date. Report median, p75, p90 with bootstrap CIs; competing risks (settle vs. adjudicate) where sample allows.
2. **Age of pending cases.** (a) From docket cohorts: at each month-end, the age distribution of files open on that date. (b) From year-end stock and flow tables (S8, S7 pending counts): implied mean time in stage via Little's law, W = L / λ, stated as a steady-state approximation with its bias. Cross-check (a) against (b) for FC and TCC.
3. **Reserve time (hearing → decision)** for SCC, FCA, FC, TCC, ONCA from S3: parse "Heard/Date of hearing" and decision date. Distribution by court-year and, where judge is identified, judge workload (decisions in prior 12 months). Caveat: written, published decisions only; oral rulings excluded.
4. **ONCA appeal duration** from S3: lower-court decision date (where stated) → appeal hearing → decision. Compare to S6 published averages.
5. **Criminal time to disposition (Ontario).** S1 medians and Jordan-ceiling shares; S7 courthouse panel (2000–2026) with event-study framing around Jordan (July 2016), COVID (March 2020) and the 2023 bail reforms. Descriptive; no causal claims without a design.
6. **Resource linkage.** Build a court × month panel: vacancy rate (S9), judges in office, filings (S8), and delay measures (1–5). Show co-movement with honest caveats (reverse causality, lags). The headline question: does delay rise when vacancies rise?
7. **Institutional-delay share (pilot, Phase 4).** From ONCA decisions on Charter s. 11(b) (in S3), extract each delay period and its attribution (defence, Crown, institutional/court resources, exceptional). LLM-assisted extraction with a hand-coded validation set of ≥50 decisions; report agreement. Clearly labelled as a selected sample (only cases where delay was litigated on appeal).

**Validation benchmarks** (sanity checks, not targets): SCC published time lapses; ONCA 2024 civil averages (≈140 days filing→ready, ≈192 days ready→hearing, ≈65 days hearing→decision, ≈397 days filing→decision); Grant's TCC samples (general-procedure trial decisions ≈5.3 years filing→decision; 2021 files settled/discontinued ≈869 days); Lesage's 2019 SCJ figure (5 years 9 months to trial, six GTA courthouses).

## 5. Architecture

- **Language/tooling:** Python 3.12, `uv` for env and lockfile, `ruff`, `pytest`. Polars or pandas + DuckDB; Parquet for all processed data.
- **Layout:**
  ```
  court-delay/
    CLAUDE.md                 # conventions for future sessions
    docs/HANDOFF.md           # this file
    docs/sources.md           # verified URLs, terms, robots findings, licences
    docs/methods.md           # estimand definitions and caveats
    src/courtdelay/
      sources/<id>_<name>.py  # each: fetch() -> raw, parse() -> tidy, validate()
      estimate/               # survival, stock_flow, reserve_time, panel
      common/                 # http client (cache, rate limit, UA), provenance
    data/raw/<source>/        # immutable cached responses (gitignored)
    data/processed/           # parquet (gitignored); small published CSVs exported to site
    data/manifest.jsonl       # url, fetched_at, sha256, status per raw file
    tests/                    # parser tests on saved fixtures
    site/                     # static site
    Makefile or justfile      # `fetch-<source>`, `build`, `site`, `all`
  ```
- **Provenance:** every published number traces to raw files via the manifest; site footers show data vintage.
- **Site:** Observable Framework (static, Markdown pages, Python data loaders, good charting via Observable Plot) is the default recommendation; Quarto is an acceptable alternative if methods prose dominates. Pages: Overview (headline findings + data gaps), one page per court, Criminal (Ontario), Resources (vacancies vs delay), Methods, Data downloads (derived CSVs only), Sources & limitations, Changelog. Every chart states definition, n, CI, vintage and source.
- **Local first:** everything runs on Vikram's machine. No deployment, scheduling or cloud resources until asked. Design so a later scheduled refresh (e.g. GitHub Actions) is easy.

## 6. Legal, ethical and licensing guardrails

- Publish aggregates only. Never publish party names, full decision texts or document copies.
- Respect licences: A2AJ and Refugee Law Lab data are CC BY-NC 4.0 with upstream court terms (non-commercial, attribution, documents not to be made search-indexable). StatCan data under the Open Government Licence. Attribute all sources on the site.
- Respect robots.txt and terms; Tier 3 is off-limits without approval.
- Courts sometimes restrict access by publication ban; if a docket shows a sealing/confidentiality marker, drop the record.

## 7. Milestones and definition of done

- **M0 Scaffold (first session):** repo, `uv` env, CLAUDE.md, docs stubs, HTTP client with cache/rate-limit/provenance, Makefile, CI-less test run. Done when `make test` passes and `docs/sources.md` records verified status of every Tier 1 and Tier 2 URL.
- **M1 Tier 1 data:** S1–S9 fetched and parsed into Parquet with tests; S7 panel built at least 2010–2026. Done when each source has a parser test and a one-paragraph data note.
- **M2 Site skeleton:** static site renders Tier 1 descriptives (criminal medians, SCC/ONCA time lapses, OCJ courthouse panel, vacancy panel, stock–flow implied durations).
- **M3 Dockets + estimation:** S10–S12 scrapers with cohort sampling plan; survival estimates; pending-age distributions; reserve-time analysis from S3. Site v1 with methods page.
- **M4 Institutional-delay pilot:** ONCA s. 11(b) extraction with validation set.

Check in with Vikram at the end of each milestone with a short summary and the open questions.

## 8. Open questions for Vikram

1. Contact email for the scraper User-Agent (env var `COURTDELAY_CONTACT`).
2. Approval to contact Courtready about its booking-wait series (and whether to build a Calendly collector if they decline).
3. Docket sample sizes per filing-year cohort (suggest: FC general 400/yr, FC immigration 400/yr, TCC 300/yr, FCA census) — trade-off between precision and crawl time at 3–5 s per request.
4. Site name and whether the repo will eventually be public.
