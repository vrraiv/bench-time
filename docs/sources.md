# Sources: verified status, terms, robots, licences

Verification pass run 2026-11-15 through `scripts/verify_sources.py` (every request cached under
`data/raw/verify/` and logged in `data/manifest.jsonl`). `COURTDELAY_CONTACT` was **unset**
during this session, so the User-Agent read `bench-time/0.1.0 (court-delay research; contact not
configured)`; no Tier 2 docket queries were made and no Tier 3 host was contacted in any way
(the client refuses them; see `BLOCKED_HOSTS` in `common/http.py`).

Status legend: **OK** works as described in the handoff · **MOVED** works at a different URL ·
**PARTIAL** works with caveats · **BLOCKED** refused or forbidden · **UNVERIFIED** not yet checked.

Robots summary: `www150.statcan.gc.ca` asks `Crawl-delay: 2` (we use 1 s for the WDS API, which
is an API, not a crawl; raise to 2 s if anyone objects). `huggingface.co`, `www.a2aj.ca`,
`www.scc-csc.ca`, `www.fja.gc.ca`, `www.fct-cf.ca`, `www.fca-caf.ca`, `www.tcc-cci.ca`: no
restriction relevant to us (empty or allow-all; SCC disallows only two case documents and
`/cso-dce/`). `www.ontariocourts.ca` disallows `/decisions/`, `/coa/en/*`, `/search/`,
`/statisticslogs/` etc.; `/ocj/statistics/` and `/ocj/files/stats/` are allowed.
`api.a2aj.ca` robots.txt carries Cloudflare "content signals" boilerplate (no explicit
search/ai-input/ai-train values set) and the API description itself prohibits systematic scraping.

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
  Licence" is the wrong name; attribution required).
- Surprise: the WDS user guide moved to `https://www.statcan.gc.ca/en/developers/wds/user-guide`.
  Whole-table download is far cheaper than per-vector calls; we filter Canada/Ontario locally.
- Data note: see S1 section at the bottom once fetched.

### S2 — StatCan Civil Court Survey (WDS) — **OK**

- 35-10-0112-01 and 35-10-0114-01 both resolve through `getFullTableDownloadCSV`. Same mechanics
  and licence as S1. Not fetched this session (denominators only; low priority).

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
  immigration dockets filed 1997–2022 as of November 2022. Not fetched this session.

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
- Coverage from HTML alone: **2010–2025**. Pre-2010 (handoff says PDFs 2003–2017, some only on
  the LAC web archive) still **UNVERIFIED**; Wayback captures of the old `stat` page are the
  likely route.
- Terms: `https://www.scc-csc.ca/resources-ressources/terms-avis/` — standard Government of
  Canada non-commercial reproduction permission. Averages only; no distributions.

### S6 — ONCA Annual Report — **PARTIAL**

- Current report: `https://www.ontariocourts.ca/coa/files/annual-reports/2023-2024-EN.pdf`
  (92 pages; covers calendar 2023 and 2024). Listed on
  `…/coa/about-the-court/archives/#Annual_Report` alongside 2009–2013 reports (HTML + PDF).
  The handoff's "July 2026, first in over a decade" description does not match what is posted:
  the file is titled 2023-2024. Whether a 2025 report exists is **UNVERIFIED**.
- Page 70 ff: "Appeal Timelines" — average days filing→scheduling readiness, readiness→hearing,
  hearing→decision, by filing year 2014–2024, for Civil, Criminal (excluding inmate) and Inmate
  appeals. Values are inside bar charts; pdfplumber text extraction returns the axis and some
  labels, so numbers may need to be read from chart data labels or by hand. Criminal tables
  exist (answering the handoff's question).
- Terms-of-use page linked in the handoff (`/en/terms-of-use/`) is gone ("page has moved");
  no site-wide terms page found yet. Court publications → treat as Crown copyright, non-commercial.

### S7 — OCJ Court Statistics — **PARTIAL (coverage starts 2012)**

- `https://www.ontariocourts.ca/ocj/statistics/` lists Criminal, Family and Provincial Offences
  statistics. File pattern `https://www.ontariocourts.ca/ocj/files/stats/{crim|fam|poa|bail}/{YYYY}/
  {YYYY}-{Offence-Based|Clearance-Rate|Disposition-Rate}-{Criminal|Youth}.{pdf|xlsx}`.
  **2012–2019 are PDF; 2020–2026 are XLSX** (much easier to parse; 2026 is partial-year).
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
  recent pages add pending-share comparisons and leave-granted counts; June 2021 is missing from
  the index). Plus a historic workbook `FC-CF_2003-2025_Historic-Stats-Historiques.xlsx`
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

### S10 — Federal Court "Court Files" — **MOVED host, UNVERIFIED mechanics**

- `https://www.fct-cf.ca/en/court-files-and-decisions/court-files` (redirect from fct-cf.gc.ca).
  Page links a "Notice to the Parties and the Profession" and "User Guide (PDF)" for the
  2022 Online Access pilot. The search form itself is JavaScript-driven; request pattern not
  examined. robots.txt is empty (allow-all). Important Notices: Crown copyright, non-commercial
  reproduction permitted; privacy notice says no personal data gathered automatically. No clause
  on automated querying found.

### S11 — FCA recorded entries — **UNVERIFIED**

- `https://www.fca-caf.ca/en/pages/court-files` is 404. Court-files search location not yet
  found; Important Notices page is standard GoC boilerplate.

### S12 — TCC docket — **UNVERIFIED**

- `tcc-cci.gc.ca` host is dead for these paths; `www.tcc-cci.ca/en/pages/court-files-and-decisions/
  court-files` is also 404. Practice Note 16 ("privacy and public access to court files") and the
  "Preliminary Ruling Docket" practice note are linked from the notices page. Search location
  not yet found.

---

## Tier 3 — not contacted

No request of any kind was made to calendly.com, ontariocourtdates.ca, canlii.org/canlii.ca or
the Ontario Courts Public Portal. The client raises `Tier3Error` for these hosts.

---

## Data notes (filled per source as fetched)

(see below)
