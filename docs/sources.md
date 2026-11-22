# Sources: verified status, terms, robots, licences

Verification pass run 2026-11-15 through `scripts/verify_sources.py` (every request cached under
`data/raw/verify/` and logged in `data/manifest.jsonl`). `COURTDELAY_CONTACT` was **unset**
during this session, so the User-Agent read `bench-time/0.1.0 (court-delay research; contact not
configured)`; no Tier 2 docket queries were made and no Tier 3 host was contacted in any way
(the client refuses them; see `BLOCKED_HOSTS` in `common/http.py`).

Status legend: **OK** works as described in the handoff · **MOVED** works at a different URL ·
**PARTIAL** works with caveats · **BLOCKED** refused or forbidden · **UNVERIFIED** not yet checked.

Robots summary (re-read from the cached files by final host, 2026-11-16):
- `www150.statcan.gc.ca` (200, text): `Crawl-delay: 2` for `*` → the client now waits 2 s.
  `www.statcan.gc.ca` (200): standard Drupal file, nothing relevant.
- `www.scc-csc.ca` (200): disallows only two case documents and `/cso-dce/`.
- `www.ontariocourts.ca` (200, 1,299 bytes, `User-agent: *` only, no crawl-delay): disallows
  `/decisions/`, `/coa/en/*`, `/search/`, `/statisticslogs/`, `/coafiles/`, `/scj/files/archive/`
  etc. Checked with the stdlib parser: `/ocj/statistics/`, `/ocj/files/stats/…` and
  `/coa/files/annual-reports/…` are allowed.
- `huggingface.co`, `www.a2aj.ca` (200): `Allow: /`. The client uses 1 s for Hugging Face and the
  4 s default for `api.a2aj.ca` (published limit 1,000 requests/hour; we made 3 requests).
- `api.a2aj.ca` (200): Cloudflare "content signals" boilerplate with no explicit values; the API
  description itself prohibits systematic scraping.
- **No robots.txt at all (HTTP 404 HTML error pages)**: `www.fct-cf.ca`, `www.fca-caf.ca`,
  `www.tcc-cci.ca`, `www.fja.gc.ca`, `www.fja-cmf.gc.ca`, `www.cas-satj.gc.ca`,
  `web.archive.org`. The `*.gc.ca` court hosts redirect to the `.ca` hosts first. Absence of a
  robots file means no stated restriction, not an explicit allowance; we keep 4 s per host.
- `collections.ola.org/robots.txt` redirects to the library's discovery UI (HTML), i.e. none.

The Tier 3 blocklist entry for the Ontario Courts Public Portal uses the hostname
`ontariocourts.on.ca`, which is an **unverified guess** (we did not look it up, to avoid any
request); add the real hostname once the owner confirms it.

---

## Tier 1

### S1 — StatCan Integrated Criminal Court Survey (WDS) — **OK**

- Endpoints verified: `POST https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata`
  (body `[{"productId": 35100029}]`, 8-digit PID) and
  `GET https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{pid}/en`, which returns
  `{"status":"SUCCESS","object":"https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip"}`.
  The zip holds `{pid}.csv` (long format; `REF_DATE, GEO, DGUID, <dimensions…>, UOM, …, VALUE,
  STATUS`) and `{pid}_MetaData.csv`.
- 35-10-0029-01 metadata: "Adult criminal courts, cases by median elapsed time in days",
  1994–2024 (fiscal years), 133,152 series, released 2026-10-01, status CURRENT.
- Format: CSV in zip. Licence: [Statistics Canada Open Licence]
  (https://www.statcan.gc.ca/en/terms-conditions/open-licence) (the handoff's "Open Government
  Licence" is the wrong name; attribution required). Request spacing 2 s per robots.txt.
- Surprise: the WDS user guide moved to `https://www.statcan.gc.ca/en/developers/wds/user-guide`.
  Whole-table download is far cheaper than per-vector calls; we filter Canada/Ontario locally.
- Data note: see S1 section at the bottom once fetched.

### S2 — StatCan Civil Court Survey (WDS) — **OK**

- 35-10-0112-01 and 35-10-0114-01 both resolve through `getFullTableDownloadCSV`. Same mechanics
  and licence as S1. Fetched and tidied (see data note); denominators only, not yet used.

### S3 — A2AJ Canadian Legal Data — **PARTIAL (use parquet, not API)**

- API: `https://api.a2aj.ca/` root is 404; `/docs` (Swagger) and `/openapi.json` work.
  Endpoints: `GET /search` (max `size` 50, **no pagination parameter**), `GET /fetch` (full text
  by citation), `GET /coverage`. Rate limits 1,000 req/h and 5,000 req/day per IP.
  **"Systematic scraping prohibited: for bulk access, see https://a2aj.ca/data/".** So the API
  is unusable for a census; it is fine for spot checks only.
- Bulk: Hugging Face dataset `a2aj/canadian-case-law` (public, ungated, format parquet,
  `lastModified` 2026-11-15). Layout is one file per court: `SCC/train.parquet` (366 MB),
  `ONCA/train.parquet` (185 MB), `FC/train.parquet` (855 MB), `FCA/train.parquet` (145 MB),
  `TCC/train.parquet` (207 MB). Row counts (dataset card): SCC 10,900 (1877–2026); FCA 7,838
  (2001–); ONCA 24,298 (1998–); FC 36,156 (2001–); TCC 8,149 (2003–).
- Schema: `dataset, citation_en/fr, citation2_en/fr, name_en/fr, document_date_en/fr (decision
  date), url_en/fr, scraped_timestamp_en/fr, unofficial_text_en/fr, cases_cited_*,
  cases_citing_*, citing_cases_count, upstream_license`. **No hearing-date, judge or file-number
  fields**: these must be parsed from the text header, as the handoff anticipated.
- **Licence differs from the handoff.** The dataset card says A2AJ's own work is **MIT**, and
  "users must also comply with upstream licenses found in the `upstream_license` field …
  [which] may include limits on commercial use". So the binding terms are the per-row upstream
  court terms, not a blanket CC BY-NC 4.0. We will treat every row as non-commercial,
  attribution-required, not-to-be-indexed until the `upstream_license` values are tabulated
  (first S3 task), and we still publish derived fields only.
- `https://www.a2aj.ca/` is up (robots allow-all).

### S4 — Refugee Law Lab "Luck of the Draw III" — **OK**

- `refugee-law-lab/luck-of-the-draw-iii`: public, ungated, single `train.parquet` (195 MB),
  last modified 2024-01-25. Licence **CC BY-NC 4.0** (confirmed in card).
- Fields: `citation` (docket no. IMM-#-YY), `year`, `name` (style of cause: **drop at parse**),
  `date_filed`, `city_filed`, `nature`, `class`, `track`, `documents` (list of
  `{RE_NO, DOCNO, DOC_DT, RECORDED_ENTRY}`), `source_url`, `scraped_timestamp`. All FC
  immigration dockets filed 1997–2022 as of November 2022. Fetched and parsed (see data note).

### S5 — SCC Year in Review / statistics — **MOVED**

- Every handoff URL under `/review-revue/…aspx` and `/case-dossier/stat/` now 200-redirects to the
  home page (soft 404). The site was reorganised:
  - Index: `https://www.scc-csc.ca/about-apropos/work-travail/review-retro/`
  - **Statistical summaries (HTML tables):** `…/review-retro/stat-{2020…2025}/`. Each is one
    table "Annual Supreme Court of Canada statistics by category" covering an 11-year window
    (stat-2020 = 2010–2020; stat-2025 = 2016–2025), including the rows
    *Average time lapses (in months)*: leave filing → leave decision; leave granted (or notice of
    appeal as of right) → hearing; hearing → judgment. Also leave counts, appeals heard,
    judgments, "appeals standing for judgment at year end" (a reserve stock).
  - Year in Review narrative: 2021–2023 at `/review-revue/{year}/index-eng.html` (no tables),
    2024–2025 at `…/review-retro/{year}/`; 2020 as PDF `/review-revue/2020/yr-ra2020-eng.pdf`;
    2025 PDF `/pdf/YIR_2025_EN.pdf`.
- Coverage: **2010–2025** from the live HTML pages, extended to **2002** from the Court's former
  `case-dossier/stat/cat5` page as captured by the Internet Archive on 2013-10-01 (see data note).
  1990s PDFs (the handoff mentions 2003–2017 PDFs on the LAC archive) were not pursued.
- Terms: `https://www.scc-csc.ca/resources-ressources/terms-avis/` — standard Government of
  Canada non-commercial reproduction permission. Averages only; no distributions.

### S6 — ONCA Annual Report — **OK (one edition)**

- Current report: `https://www.ontariocourts.ca/coa/files/annual-reports/2023-2024-EN.pdf`
  (92 pages; covers calendar 2023 and 2024). Listed on
  `…/coa/about-the-court/archives/#Annual_Report` alongside 2009–2013 reports (HTML + PDF).
  The handoff's "July 2026, first in over a decade" description does not match what is posted:
  the file is titled 2023-2024. Whether a 2025 report exists is **UNVERIFIED**.
- Page 70 ff: "Appeal Timelines" — average days filing→scheduling readiness, readiness→hearing,
  hearing→decision, by filing year 2014–2024, for Civil, Criminal (excluding inmate) and Inmate
  appeals. The charts on pp. 70–73 have no numbers in the text layer, but the same series are
  printed as tables in the statistical appendix (pp. 88–91) and are parsed from there. Criminal
  tables exist (answering the handoff's question).
- Terms-of-use page linked in the handoff (`/en/terms-of-use/`) is gone ("page has moved");
  no site-wide terms page found yet. Court publications → treat as Crown copyright, non-commercial.

### S7 — OCJ Court Statistics — **PARTIAL (coverage starts 2012)**

- `https://www.ontariocourts.ca/ocj/statistics/` lists Criminal, Family and Provincial Offences
  statistics. File pattern `https://www.ontariocourts.ca/ocj/files/stats/{crim|fam|poa|bail}/{YYYY}/
  {YYYY}-{Offence-Based|Clearance-Rate|Disposition-Rate}-{Criminal|Youth}.{pdf|xlsx}`.
  **2012–2019 are PDF; 2020–2026 are XLSX** (much easier to parse). Periods: calendar years to 2019, April–March fiscal years from 2020; the
  2026 files cover April 2025–March 2026.
  Criminal series: Offence-Based (cases received/disposed, average appearances and days to
  disposition, trial rate), Clearance Rate (two-year files), Disposition Rate (% disposed by
  months elapsed, average appearances/days). Bail 2015–2026. Family and POA counts too.
  100 PDFs + ~100 XLSX in total.
- Pre-2012 (`collections.ola.org` series 283147 and 108774): every URL tried
  (`/ser/283147`, `/ser/283147/2010.pdf`, `/mon/`) redirects to the Legislative Library's
  Primo discovery UI (`librarysearch.ola.org`, JavaScript app, `noindex`). The old static
  collection URLs appear to be gone; **pre-2012 OCJ panel is BLOCKED until a direct document URL
  pattern is found** (possibly via Wayback or the library's permalinks). The handoff's
  "2000–2026 panel" is therefore 2012–2026 for now.
- Disclaimer on the page: data are MAG's; the court disclaims accuracy. Expect definition breaks
  (the page itself warns bookmarks/regions change).

### S8 — Federal court workload tables — **MOVED (all three courts)**

- **FC**: handoff URLs on `fct-cf.gc.ca` 404 or redirect to `www.fct-cf.ca`. Statistics index:
  `https://www.fct-cf.ca/en/pages/about-the-court/reports-and-statistics/statistics`. Quarterly
  "Activity Summary" pages exist for **every quarter 2003–2026** at
  `…/reports-and-statistics/statistics-{march-31|june-30|september-30|december-31}-{YYYY}`
  (one HTML table: subject matter × proceedings commenced, dispositions, pending at quarter end;
  recent pages add pending-share comparisons and leave-granted counts; September 2007 and June
  2021 are missing from the index; 2003 pages label the total "TOTAL TRIAL DIVISION"). Plus a historic workbook `FC-CF_2003-2025_Historic-Stats-Historiques.xlsx`
  (one sheet: new proceedings by year, total/immigration).
- **FCA**: `https://www.fca-caf.ca/en/pages/about-the-court/statistics` works (handoff URL
  correct). One page, ~50 tables: cumulative year-to-date commenced/dispositions/pending by
  subject matter for each quarter from 2019 to Q2 2026.
- **TCC**: `tcc-cci.gc.ca` paths 404; site is `www.tcc-cci.ca`. Statistics at
  `https://www.tcc-cci.ca/en/pages/about/reports-and-statistics`: a single workload table
  (proceedings instituted, judgments processed, files heard, recorded entries, total
  dispositions) for 2018-19 to 2022-23 only. The handoff's **status-at-March-31 table (not
  perfected / perfected / reserved / awaiting timetable / scheduled) was not found** on the site;
  it may live in the Courts Administration Service annual reports. **UNVERIFIED.**
- **CAS**: `cas-satj.gc.ca/en/publications/...shtml` paths 404. Annual reports are now at
  `https://www.cas-satj.gc.ca/en/pages/publications/ar/annual-report-{YYYY}-{YYYY}` (HTML; the
  2022-23 page has a "Part III: The Courts we serve — statistics at a glance" section with 8
  tables for FCA, FC, CMAC, TCC). Older PDF links listed on the TCC page
  (`/en/publications/ar/2013-14/…pdf` etc.) return **404** — the PDFs moved or were removed.
  Coverage of the HTML reports (which years exist) **UNVERIFIED**.
- Terms (FC/FCA/TCC "Important Notices"): Crown copyright; non-commercial reproduction permitted
  without charge; no anti-automation clause found. Fine for Tier 1 statistics pages.

### S9 — Federal judicial complement and vacancies — **OK**

- Live page: `https://www.fja.gc.ca/appointments-nominations/judges-juges-eng.aspx` (also served
  identically from `www.fja-cmf.gc.ca`). Heading "NUMBER OF FEDERALLY APPOINTED JUDGES AS OF
  NOVEMBER 1, 2026"; 15 `<table class="width95">` each with a `<caption>` (Canada, Alberta, …,
  Ontario, …, Total). Columns: Court, Total Number of Judges in Office, Supernumeraries,
  Grand Total, Total Number of Women Judges, Number of Current Vacancies. Canada table rows:
  Supreme Court, Federal Court of Appeal, Federal Court, Tax Court of Canada. Ontario rows:
  Court of Appeal, Superior Court of Justice, Family Court.
- Wayback CDX (`https://web.archive.org/cdx/search/cdx?url=…&output=json&fl=timestamp,original,
  statuscode,digest&collapse=timestamp:6`) works; `collapse=timestamp:6` gives one capture per
  month. Capture counts with status 200:
  - `fja.gc.ca/…/judges-juges-eng.html` (older URL): 46 months, 2009-06 → 2026-05 (sparse
    before 2017).
  - `fja-cmf.gc.ca/…/judges-juges-eng.aspx`: 65 months, 2015-10 → 2026-08.
  - `fja.gc.ca/…/judges-juges-eng.aspx`: 13 months, 2015-08 → 2018-06.
  Union ≈ 100 distinct months over 2009–2026, with real gaps (e.g. 2016 only on fja-cmf; 2021
  thin). Snapshot timestamps are recorded per row. Pre-2015 HTML layout likely differs; parser
  must be caption/heading tolerant.
- Terms: `https://www.fja.gc.ca/notices-avis/index-eng.html` — Government of Canada
  non-commercial reproduction permitted.

---

## Tier 2 (landing and notice pages only; no docket queries made)

### S10 + S11 — Federal Court and FCA dockets — **CENSUS COMPLETE 2026-11-19**

- Landing page `https://www.fct-cf.ca/en/court-files-and-decisions/court-files`. Its scripts
  (`/Content/js/pages/courtfiles.js`, `/Content/js/base/data.js`, read 2026-11-16) call JSON
  endpoints on the same host. One court-number search box serves both courts: `division=t` is the
  Federal Court, `division=a` the Federal Court of Appeal, so **S11 uses the same system as S10**.
  Per file: `GET /CourtFilesAndDecisions/proceedingQueriesAddInfo?division=&courtnumber=` (file
  information) and `GET /CourtFilesAndDecisions/proceedingQueriesRE?division=&courtnumber=`
  (recorded entries): **two requests per file**. Other endpoints exist for party-name search,
  related cases and public party lists; we do not use them.
- robots.txt: none (404). Important Notices: Crown copyright, non-commercial reproduction
  permitted; no clause on automated access. The 2022 online-access notice and user guide concern
  downloadable documents and confidentiality; they set no conditions on automated queries.
  Responses include party names: kept only in the local raw cache, dropped at parse.
- Plan (owner decision 2026-11-16): FCA census, FC general (T-) census, FC immigration sample of
  1,000 per filing year from 2023. At 4 s per request this is roughly: FCA 2010–2026 ≈ 15 h,
  FC general 2018–2026 ≈ 2–3 days, IMM 2023–2026 ≈ 9 h, plus misses at the end of each year.
  Implementation: `sources/s10_fc_fca_dockets.py`.
- **Run log.** 2026-11-16: pilot of 7 files OK. FCA census started 08:28 local; FCA-2010 complete
  (485 files, numbers probed to 694). At 10:20 the site began serving an **expired TLS certificate**
  (subject CN www.cas-satj.gc.ca, Entrust, notAfter 2026-11-02 23:59:59 GMT; the host is behind Azure
  Traffic Manager, so earlier requests were presumably routed to a backend with a valid certificate).
  The crawl stopped at A-193-11; certificate verification is not bypassed. 1,576 requests made,
  5 non-200. Resume once the certificate is renewed; cached files are not re-fetched.
- **Pre-2022 immigration list sample, 2026-11-22** (owner approval the same day, to test whether
  older files closing explain a gap with the Court's late-2025 dispositions). Stratum
  `IMM-PRE2022`: files the Refugee Law Lab dockets show filed before 2022 and without an ending
  in November 2022 (7,498), drawn in seeded order within four filing-year groups; plan in
  `plan_IMM-PRE2022.json`. 660 files fetched 12:33–13:37 UTC at 3 s spacing, single process;
  677 numbers tried, 17 returned no file; no failed request, no 403, 429 or challenge. Parsed to
  `data/processed/s10/imm_pre2022.parquet`, apart from the census and yearly samples. Result in
  `docs/methods.md`.
- **Crawl complete 2026-11-19 06:27** (resumed after the certificate was renewed; 3 s spacing on
  this host by owner approval 2026-11-16; interrupted twice on 2026-11-18 by a low-memory kill and
  a reboot, resumed from cache). No 403, 429 or challenge at any point. Parsed: 34,406 files and
  835,570 recorded entries. FCA `A` 2010–2026: 6,492 files. FC general `T` 2018–2026: 23,886
  files (1,954 / 1,816 / 1,289 / 1,734 / 2,457 / 2,523 / 3,261 / 4,464 / 4,388 by year). FC
  immigration sample 2023–2026: 4,028 files. (Counts before 2026-11-19 07:28, when 2,116 files with a
  confidentiality marker were restored: 36,829 files in all; see `docs/methods.md`.) Cross-check from the decision link:
  of 8,179 in-frame file numbers cited by published decisions, 12 were not found.
- **IMM-2022 overlap sample** (owner approval 2026-11-18): stratum `IMM-2022`, 300 files drawn at
  random, run 2026-11-19 at the same 3 s spacing; finished 07:20, no errors (frame top IMM-13672-22).

### Superior Court of Justice timing: what open data exists (checked 2026-11-19)

- **Civil and family: yes.** Statistics Canada table 35-10-0116 (Civil Court Survey) gives active
  cases by elapsed time from initiation to first disposition, by level of court, for Ontario,
  2005/06 to 2024/25, in five bands (3 months or less, to over 24 months). Table 35-10-0117 gives
  inactive cases by years since initiation. Both now fetched by S2. First look, Ontario superior
  court, general civil: the share over 12 months rose from 15% (2008/09) to 33% (2019/20); family
  stayed near 6%. **Before use:** read the survey's definition of "active" and "first
  disposition"; 2005-2007 look incomplete; active general civil cases double in 2024/25 (133,339
  to 268,178) with 44% over 24 months, which looks like a change in reporting, not in the court.
- **Criminal: no court-level split.** None of the ICCS tables separates superior from provincial
  court (checked the full table list). Table 35-10-0124 has caseload by age of case but ends in
  2018; 35-10-0173 has the share of cases over the Jordan limit, which we already hold.
- **Booking calendars (Tier 3): not available to us.** Calendly's Acceptable Use Policy (effective
  2024-03-08; applies to visitors) prohibits "accessing or searching any part of the Services by
  any means other than our publicly supported interfaces (for example, 'scraping')". Two requests
  made, both to legal pages; no calendar opened. Owner decision 2026-11-19: the only route is
  Courtready agreeing to share its series.

### S13 — Supreme Court of Canada case information — **COLLECTED 2026-11-20 (9,131 files)**

Checked at the owner's request for the leave-application stage of appeal chains. Ten requests in
all (robots, home, the cases landing page, the search page and its script, the access policy, the
terms, two site maps, one case page); nothing parsed or stored beyond the cache.

- **Where the data is.** Each Supreme Court file has a page at
  `https://www.scc-csc.ca/cases-dossiers/search-recherche/{5-digit case number}`: one HTML page
  (about 160 KB for the sample) with a docket table (Date, Proceeding, Filed by), then Parties,
  Counsel, Summary, Filed documents and Webcasts. The docket rows carry the stage events
  ("Hearing of the appeal", "Judgment reserved", "Judgment on the appeal rendered", "Appeal
  closed"). **One request per file.**
- **Listing the files.** `https://www.scc-csc.ca/en/sitemap.xml` lists 42,619 case pages, so the
  frame comes from the court's own site map. The search form on the site is not needed and would
  not be used: it posts to a third-party search service with a site key.
- **Robots** (re-read 2026-11-19): disallows `/*22551`, `/cso-dce/` and two named case
  documents. Case pages are not disallowed. No crawl delay stated.
- **Terms.** Standard Government of Canada non-commercial reproduction. Neither the terms nor the
  Policy for access to Supreme Court of Canada court records mentions automated access. The
  policy says access to a record may be restricted and the restriction recorded on the docket.
- **Not yet verified:** where the page states the court appealed from and the lower-court file
  number (the search form has both fields, so the data exists); how leave-stage events are
  worded; how restricted files appear.
- **Names.** Pages include party and counsel names. As with S10 and S12 they would stay in the
  local raw cache and be dropped at parse.
- **Pilot (owner approval 2026-11-19): 20 random case pages**, no errors. Confirmed: the leave
  stages are standard labels ("Application for leave to appeal", "All materials on application
  for leave submitted to the Judges", "Judgment of the Court on the application for leave to
  appeal", "Close file on Leave"); the leave-judgment entry names the court appealed from, its
  file number, citation and date, and the result; a "Lower court rulings" block gives the same
  for files not yet decided. Leave filing date read for 20 of 20, court appealed from for 20 of
  20, result for all 16 decided. "Certificate (on limitations to public access)" is a routine
  form on every file (60 entries in 20 files) and is counted, not treated as a sealing marker.
  Pages link to other sites, including one we do not use; links are never followed.
- **Full pass** started 2026-11-19 evening: 9,131 case pages (case numbers from 33500, about
  2010 on) at the default 4 s spacing, about 10 hours. Implementation:
  `sources/s13_scc_cases.py`.
- **Full pass finished 2026-11-20 06:06:** 9,131 of 9,131 pages, no failed requests, no
  block or challenge. Backed up. Parse: no page without a docket; leave filing date read
  for 96% of files (the rest are appeals as of right and references), leave result for
  100% of decided files, court appealed from for all but 9 files. Counts of appeals heard
  and judgments match the court's published statistics within one or two a year (see
  `docs/methods.md`). In the weekly refresh from 2026-11-20 (`courtdelay refresh scc`: the
  site map, new case pages, and a quarter of the files still open; about 120 requests).
- **Second, lighter source:** "Judgments on leave applications" and "Bulletins of proceedings"
  at `decisions.scc-csc.ca` (a different host, not checked). They give the leave decision date
  but not the filing date.
- **Size if approved.** Case numbers run at roughly 500 to 600 a year; files from 2010 on are
  about 8,500 pages, around 9 to 10 hours at 4 seconds a request. Restricting to cases from the
  federal courts needs an index of which cases those are, which the pages themselves provide.

### S12 — Tax Court dockets — **ENDPOINTS VERIFIED, PILOTED**

- Landing page `https://www.tcc-cci.ca/en/pages/find-a-court-file` (script `/Content/js/base/data.js`,
  read 2026-11-16). File search: `GET /en/tcc/pq/appealnumber/courtnumber?courtnumber=&lang=e`;
  recorded entries: `GET /en/tcc/pq/appealnumberRE?appealnumber=&lang=e`. Other endpoints (party
  search, representatives, related files) are not used.
- **The court-number search is a prefix match**: "2024-1" returned all 1,093 files of 2024 whose
  number starts with 1 in one 1.4 MB response (no cap; `Count` equals rows). A filing year is listed
  with nine queries ("YYYY-1" … "YYYY-9"), then one entries request per file. Listing rows already
  carry procedure (General/Informal), status, disposition text, filing date, nature, act code,
  hearing location, self-represented flag and a confidentiality flag. Entries are short standard
  labels with dates ("Reply to Notice of Appeal", "Appeal Scheduled", "Minutes of Hearing",
  "Judgment", "File Closed", "Adj. …"). Raw responses include appellant, representative and
  Crown counsel names: local cache only, never parsed into outputs.
- robots.txt: none (404). Important Notices: Crown copyright, non-commercial reproduction. Practice
  Note 16 (privacy and public access to court files) sets no conditions on automated access.
  Crawl at the 4 s default, in parallel with the Federal Court crawl (different host; owner
  approval 2026-11-16). Plan: census of filing years 2018–2026, roughly 3,000–5,000 files a year,
  about 4–5 hours per year. Implementation: `sources/s12_tcc_dockets.py`.
- The handoff's TCC status-at-March-31 table remains unfound, but per-file `STATUS` in the listing
  ("Case management in progress", "Ready To Be Scheduled", "Scheduled", "Heard", "Hold", "Closed")
  gives a better pending-stock breakdown at the scrape date.

---

## Tier 3 — not contacted

No request of any kind was made to calendly.com, ontariocourtdates.ca, canlii.org/canlii.ca or
the Ontario Courts Public Portal. The client raises `Tier3Error` for these hosts.

---

## Data notes (one paragraph per source as fetched; vintage = fetch date 2026-11-15/16 UTC)

**S1 (StatCan ICCS).** Six tables downloaded whole and filtered to Canada + Ontario:
35-10-0029 (median elapsed days; 389k rows kept of 3.4M; fiscal years 1994/95–2024/25; dimensions
offences × age × sex × type of case × statistic {Count, Median}), 35-10-0027 (cases/charges by
decision; 1.9M rows kept), 35-10-0173/0174 (adult/youth key indicators, 2005/06–2024/25, 40–56 %
of cells null because many indicators start later), 35-10-0172/0176 (preliminary quarterly
indicators, 2019–2026, 49–65 % null). Headline check: Ontario, Total Criminal Code, all ages/sexes,
total cases, median days to disposition in 2024/25 = **196**. Sparse cells (companies, "age not
applicable") carry medians above 10 years and are legitimate; validation checks the headline series
only. Bias: completed cases; first appearance → final decision; no attribution of delay. Processed:
`data/processed/s1/*.parquet`, release vintage in `tables.parquet` (release 2026-10-01).

**S5 (SCC statistics).** Six HTML pages (stat-2020 … stat-2025), each an 11-year window; 1,199
cells; most-recent page wins where windows overlap (no cross-page conflicts logged this vintage).
Time lapses (months, annual averages) **2010–2025**, latest 2025: leave filing → leave decision
4.4; leave → hearing 9.1; hearing → judgment 5.1. Also leave counts, appeals heard, judgments,
"appeals standing for judgment at year end". Bias: averages, by file number; pre-2010 not yet
captured. Processed: `data/processed/s5/scc_time_lapses.parquet`, `scc_stats.parquet`.

**S8 (federal workload).** FC: 93 quarterly Activity Summary pages, 2003-Q1 … 2026-Q3, 2,204
rows of subject matter × {commenced, dispositions, pending at period end, leave granted}; periods
are year-to-date so quarterly flows need differencing. Latest (2026-09-30 YTD): 30,845 commenced,
15,349 disposed, **43,536 pending** (immigration-driven). FCA: 50 YTD periods 2019–2026-Q2, 450
rows (TOTAL pending 473 at 2026-06-30). TCC: one table, five fiscal years 2018-19…2022-23, 18
metrics incl. proceedings instituted (3,230 in 2022-23) and total dispositions; no pending-status
breakdown. CAS annual report pages cached for 2017-18…2025-26 except 2023-24; not parsed yet.
Bias: counts of proceedings; category definitions change (e.g. 2010 vs 2026 subject lists);
Little's-law durations from these are steady-state approximations. Processed:
`data/processed/s8/{fc_activity,fca_activity,tcc_workload}.parquet`.

**S9 (judicial complement).** 118 captures (117 Wayback + live), 116 parsed, **112 distinct
"as of" dates 2009-06 → 2026-11**; 3,716 rows (jurisdiction × court). Coverage by year:
2009–2014 one or two snapshots each, 2015: 5, 2016–2019: 8–12, 2020: 6, 2021: 7, 2022–2026:
7–11. Two captures failed (error pages, "no tables"); one 2011 capture needed ordinal-date
handling. Federal Court example: 2009-06 27 in office / 6 vacancies; 2026-11 40 in office / 2
vacancies, 3 supernumeraries. Validation: grand_total = in_office + supernumerary holds; Canada
and Ontario tables present in the latest snapshot. Caveats: the "as of" date is the page's own
(first of month), captures are irregular, and pre-2015 page layouts name "Yukon Territory".
Processed: `data/processed/s9/judges_snapshots.parquet`, `parse_failures.parquet`.

**S2 (StatCan civil).** 35-10-0112 (1,020 Canada+Ontario rows) and 35-10-0114 (1,800 rows)
downloaded and tidied; counts only, intended as denominators; not yet used in any estimate.

**S3 (A2AJ decisions).** Five parquet files (1.76 GB raw, cached): SCC 10,900 decisions
(1877–2026), FCA 7,838, FC 36,156, TCC 8,149, ONCA 24,298. Derived fields only are stored
(`decisions_meta.parquet`): citation, decision date, URL, upstream licence, text length,
hearing date(s) and mode, file numbers, judges line (header labels only), TCC procedure, ONCA
lower-court date, reserve days. **Hearing-date coverage since 2015, decisions not disposed of in
writing:** FC 97 %, FCA 99.8 %, ONCA 90 %, SCC 99 %, TCC 95 %. SCC before 2016 relies on the
S.C.R. headnote date line and reaches ~84 % for 2005–2015 and ~0 % before 2005. Hearing dates
come from three places: the header ("Heard:", "Appeal heard:", "Audience tenue … le"), the FC
solicitors-of-record block at the end ("DATE OF HEARING:"), or the SCC headnote. "Dealt with in
writing" / "sans comparution" marks `hearing_mode = written` (FCA 12 %, FC 4 %). About 1 % of rows
have a parsed hearing date after the decision date (another date in the window); those keep a
null reserve time and `hearing_after_decision = true`.
Cross-checks: S3 mean hearing→judgment for the SCC tracks the Court's published S5 averages
within ~0.3 months in 13 of 16 years 2010–2025 (e.g. 2024: 6.6 vs 6.3; 2017: 4.6 vs 4.6);
ONCA 2024 mean hearing→decision 60 days (n = 787, median 13, p90 187) against the annual
report's ~65 days for civil appeals. Decision dates match the "Date:" header line on 99.9 % of
rows (no UTC day shift). `upstream_license` is the same CanLII-style notice for all five courts
("Users are responsible for identifying and complying with all legal restrictions on the
reproduction or publication of these documents…"), which does not state a licence; treat as
non-commercial, attribution, not indexable. **Owner's reading (2026-11-16): the notice means no commercial use and no reproduction of full texts; publishing derived aggregates with attribution is consistent with it.**
Bias: published written decisions only; oral rulings and unreported dispositions absent.

**S4 (Refugee Law Lab FC immigration dockets).** 218,639 dockets (filing years 1993–2022, scraped
Nov 2022); 667 dropped for sealing/confidentiality markers; 2.58 M recorded entries classified
(3.1 % unclassified) and stored as type, date and result only — no entry text, no style of cause.
Registry "(Final decision)" / "(Décision finale)" markers give the final disposition; English and
French wording are both handled. 80 % of dockets have a leave decision (grant rate ≈ 20 %: 34,076
granted vs 139,334 dismissed), 94 % a detected final disposition. Weak spots: the 2012 and 2014
cohorts lack a detected terminal event for ~17 % of files (a format not yet recognised), and
hearing entries are under-detected (10 % of dockets vs 16 % granted leave), so the
"leave granted → hearing" estimand is **not reliable yet** and is not charted. Filing → leave
decision KM medians: 104 days (2010 cohort), 98 (2016), 131 (2019), 266 (2020), 224 (2021).

**S5 extension (2002–2009).** The Court's former statistics pages (`/case-dossier/stat/cat1–5`)
were captured by the Internet Archive on 2013-10-01; category 5 holds the three time-lapse series for
2002–2012 as three small tables. They agree with the current pages where windows overlap
(2010–2012; one cell differs across all pages, the newer value is kept). S5 now covers
**2002–2025** for all three stages. Categories 1–4 (filings, leave decisions, appeals by
jurisdiction, judgments) are also archived for 2002–2012 but not yet parsed.

**S6 (ONCA annual report).** The charts on pp. 70–73 have no numbers in the text layer, but the same
series are printed in the statistical appendix (pp. 75–91). 13 tables parsed, 649 cells, 2014–2024:
appeals filed, incoming by subject, motions, leave-motion dispositions, appeal dispositions, merits
hearings, bench vs reserved decisions, and the four timeline tables (filing → ready, ready →
hearing, hearing → decision, filing → decision; civil, criminal excluding inmate, inmate, all).
2024 civil values equal the handoff benchmarks exactly (140.35 / 191.60 / 65.03 / 396.66 days).
Note: on p. 77 (self-represented litigants) the "Civil" and "Criminal" column groups appear swapped
relative to p. 75 (the "Civil" totals equal the criminal filing counts); that table is not parsed.
Earlier reports (2009–2013) exist as HTML and PDF on the archives page; not parsed yet.

**S7 (OCJ).** 90 criminal files (2012–2019 PDF, 2020–2026 XLSX; adult "all" and youth).
Offence-based: 70,964 rows, 72 unit names normalised to stable keys (e.g. "Ontario Overview" =
"Provincial Overview", "North West" = "Northwest"), route totals (before trial + at trial + after
trial) equal cases disposed in every year. Monthly series: disposition rate 18,772 unit-months and
clearance rate 22,942, **2011-01 → 2026-03**, after de-duplicating the two-year overlap between
files (later file kept; revisions counted in the Toronto-break paragraph below). **Layout
breaks:** 2012–2014 disposition files use bands under 8 / 8–12 / over 12 months instead of
10 / 15 / 18; PDF clearance tables add pending (net of bench warrants) and a clearance rate that the
XLSX files dropped; periods are calendar years to 2019 and April–March fiscal years from 2020. Small
courthouse cells (1–30 cases) can show averages of several years; validation checks cells with ≥50
dispositions. **Toronto break:** the 2023 files exclude Toronto entirely (data-integrity problems
after the six Toronto courthouses were amalgamated into 10 Armoury Street) and label the province
"Provincial/Ontario Overview, Less Toronto" (kept as `province_ex_toronto`, never mixed with full
province rows); Toronto resumes in January 2024, and the 2025 and 2026 Toronto sheets report
cumulative periods starting January 2024 rather than the file's own period. The 2020 files' French
headers read October 2019 – September 2020 for some sheets; periods are taken per sheet. Revisions
between overlapping monthly editions (same measure, different non-null value): 2,837 unit-months
(disposition) and 1,597 (clearance); the later edition is kept. The PDF monthly parser drops data
lines whose value count does not match the layout (blank cells in small courthouses) without counting
them. Pre-2012: the Internet Archive has no captures of `/ocj/files/stats/` before 2012
(prefix query, 2026-11-16), so the 2000–2011 panel remains **BLOCKED**. The archive does hold extra
2015–2016 quarterly bail files not on the live page.

**S8 identity check.** FC: of 90 quarter-to-quarter transitions, 76 reconcile within 1 % of the
pending stock (small gaps are expected from reopened and transferred files); 14 do not, including
2015-Q4 (published stock falls 1,246 more than flows imply, ≈20 %) and 2023-Q1 to Q3 (±284 to 710).
September 2007 and June 2021 are missing from the Court's index, so 2007 and 2021 have only three
quarters. FCA: 48 of 49 reconcile. Quarterly Little's-law rows carry `identity_ok`; annual rows carry
`publishable` (four quarters, all reconciling): 13 of 24 FC years qualify (not: 2006, 2007, 2009,
2015, 2016, 2018, 2019, 2021, 2023, 2024, 2026). The site marks failing quarters.
