# Methods: estimands, estimators, caveats

Every number the site publishes carries: the estimand definition below, n, an uncertainty range,
the data vintage (fetch date in `data/manifest.jsonl`), the source id, and the bias statement.
Prefer medians and quantiles to means; the courts' own published figures are averages and are
reported as such.

## Vocabulary

- **Institutional delay**: waiting that the institution creates (no judge, no courtroom, no hearing
  date, a reserved decision). It is the quantity of interest; most published statistics measure
  total elapsed time and cannot isolate it.
- **Stock and flow**: *pending* (stock at a date), *commenced/received* and *disposed* (flows over a
  period). Year-to-date flows (FC, FCA) are differenced to quarters before use.
- **Censoring**: a file open at the observation date has an unknown final duration; it is
  right-censored at that date and must not be dropped.

## Estimands

### E1. Stage durations (dockets: S4 now; S10–S12 later)

Population: files by filing-year cohort (FC immigration IMM-#-YY from S4; later FC general, FCA,
TCC). Stages (dates from classified recorded entries): filing → leave decision (FC immigration) →
hearing → judgment; filing → any final disposition (judgment, discontinuance, leave dismissed).
Estimator: Kaplan–Meier survival by cohort with censoring at the scrape date (S4: November 2022);
report median, p75, p90 with bootstrap percentile CIs (≥500 resamples); competing-risk cumulative
incidence (settle/discontinue vs adjudicate) where cohorts exceed ~200 files.
Bias: entry classification is regex-based (unclassified share reported per cohort); S4 covers
immigration only; sealed files dropped.

### E2. Age of pending cases

(a) From docket cohorts: at each month-end, the distribution of ages of files open on that date.
(b) From stock–flow tables (S8 FC/FCA/TCC, S7 OCJ cases pending): Little's law W = L / λ, with L
the average stock over the period and λ the disposal rate (dispositions per day), stated
explicitly as a steady-state approximation. We report W under both arrival-rate and
disposal-rate denominators; their gap is a diagnostic of non-stationarity. Uncertainty: the
published counts are censuses, so the interval reflects the choice of denominator and the quarterly
timing, not sampling. Cross-check (a) against (b) for FC immigration.
Precondition: the identity pending_t = pending_{t−1} + commenced − dispositions must hold
(within rounding) for each court-year before any W is published; violations are listed.

### E3. Reserve time (hearing → decision), S3

Population: published written decisions of SCC, FCA, FC, TCC, ONCA with a parsed hearing date
and `hearing_mode != written`. Duration: decision date minus last hearing date. Report by
court × decision-year: n, median, p75, p90, share > 6 months, with bootstrap CIs; by judge where
the header names a single judge (FC, TCC) together with that judge's decisions in the prior 12
months as a workload proxy. Validation: SCC series against the Court's published averages (S5);
ONCA 2024 against the annual report (S6). Bias: oral and unreported decisions absent; multi-day
hearings use the last day; ~1 % of rows have a mis-parsed hearing date (flagged, excluded).

### E4. ONCA appeal duration, S3 + S6

Lower-court decision date (where the header says "On appeal from … dated …") → hearing →
decision. Compare to S6 published filing→ready, ready→hearing, hearing→decision averages
(filing date itself is not in decision texts, so the first interval is not identified from S3).

### E5. Criminal time to disposition (Ontario), S1 + S7

S1: median days first appearance → final decision, Ontario and Canada, by offence group and
fiscal year (StatCan ICCS, completed cases). Jordan-ceiling shares from the key-indicator tables
where available. S7: OCJ courthouse × period panel of average days and appearances to
disposition, share disposed within 10/15/18 months, pending counts and clearance rates.
**Definition break:** OCJ periods are calendar years for 2012–2019 (PDF) and April–March fiscal
years for 2020–2026 (XLSX); monthly disposition and clearance series are continuous from 2011-01.
Event-study framing around Jordan (July 2016), COVID (March 2020) and the 2023 bail reforms is
descriptive; no causal claim without a design.

### E6. Resource linkage, S9 + S8 + E2/E3/E5

Court × month panel: judges in office, supernumeraries, vacancies (S9; irregular snapshots carried
forward with the snapshot date recorded), filings and pending (S8/S7), delay measures. Show
co-movement with lags; state reverse causality (vacancies may be filled when backlogs grow) and
that supernumerary judges carry reduced loads.

### E7. Institutional-delay share (pilot, M4)

From ONCA s. 11(b) decisions in S3: each delay period and its attribution (defence, Crown,
institutional, exceptional), LLM-assisted with a ≥50-decision hand-coded validation set and
reported agreement. Selected sample (delay litigated on appeal); labelled as such.

## Uncertainty conventions

- Sample statistics: bootstrap percentile intervals, 95 %, seed recorded.
- Census counts (StatCan, court tables): no sampling interval; show revision ranges where a later
  publication revised the figure (S5 and S7 log cross-page revisions).
- Averages published by courts: reported as published, labelled "average (court-published)".

## Validation benchmarks (sanity checks, not targets)

SCC time lapses (S5) · ONCA 2024 civil averages (≈140 / 192 / 65 / 397 days) · Grant's TCC samples
(≈5.3 years to trial decision; 2021 files settled ≈869 days) · Lesage 2019 SCJ (5 y 9 m to trial, six
GTA courthouses) · Law360 2023 vacancy analysis (349 fills 2019–2023, 8+ months average).

Docket censuses against court-published workload (S8): aggregate S12 Tax Court files by fiscal year
(April–March) and compare with https://www.tcc-cci.ca/en/pages/about/reports-and-statistics
(FY2018-19 to 2022-23): proceedings instituted ↔ files by `FILED_DATE` (comparable from FY2018-19);
total dispositions ↔ files by close date and files heard ↔ first "Minutes of Hearing" (comparable
only from about FY2021-22, because the census starts with 2018 docket numbers and misses older
files closing or heard in earlier years). Same idea for S10/S11 against the FC and FCA activity
summaries (commenced, dispositions, pending). Report differences, not just agreement; a large gap in
hearings tests whether "Minutes of Hearing" marks the trial.

## Tax Court docket census (S12): provisional cohort tables

Built by `courtdelay build` into `data/processed/derived/` only (not `site/src/data/`): the tables
are provisional until the practitioner review of entry labels is back, and publishing aggregates
from a Tier 2 docket source is an owner decision.

- `s12_tcc_km_by_cohort`: Kaplan-Meier time from filing to the end of the file, by file-number year
  and procedure group (General, Informal, Application, EI, CPP, OAS). Right-censored at the scrape
  date; 200 bootstrap replicates for the 95% interval.
- `s12_tcc_file_outcomes_by_cohort`: shares of files closed, heard, closed without a hearing,
  discontinued, held in abeyance, case-managed, and with an adjournment request.

Definitions and rules:

- **Filing date.** The listing's filed date when its year is within one year of the file number's
  year (December filings numbered in January are common). It is missing for most applications and
  implausible for 136 files (typing errors such as year 0026, or dates years before the number).
  Fallbacks, in order: the notice of appeal entry, then the first recorded entry. The source is
  kept in `date_filed_source`; 67 of 29,714 files have no usable date and are left out.
- **End of file.** The court's status field decides whether a file has ended. Files it lists as
  active (case management in progress, ready or not ready to be scheduled, scheduled, hold,
  awaiting timetable, settled or settlement received) are treated as open even when they carry a
  judgment or withdrawal entry, because those are usually on a motion: 18,713 of 18,722 "Closed"
  files have a "File Closed" entry and almost no active file does. For the rest, the end is the
  "File Closed" entry, else the earliest of a judgment, a withdrawal of the appeal, or a bare
  outcome entry (Dismissed, Allowed, Allowed in Part, Quashed, Dism. for failure to appear, File
  Cancelled). Before this rule about 700 active files were wrongly counted as ended.
- **Listed filing date later than the first entry.** For 9% of files the first recorded entry is
  more than a week before the listed filing date (median 198 days for the 946 files whose listed
  date falls in the year after the file number). The listed date is used for now, so those
  durations are understated; `first_entry_date` is kept for a sensitivity check (practitioner
  question 5).
- **Censored tails.** A quantile is reported as not yet estimable when fewer than 20 files are
  still at risk at that time and that is under half of what a fully observed cohort would have.
  Without this, recent cohorts show medians read off one or two old files.
- **Abeyance.** Recorded (first date, number of entries) but not subtracted: only 1,016 of 3,738
  files with an abeyance have an entry releasing it.
- **"Hearing Adjourned by TCC".** All 702 entries are dated 2020, so this marks the pandemic
  closures, not a general signal of court-initiated adjournments.

Bias statement: file numbers are a census of what the court's search lists; confidential files are
not listed. Entry labels are classified by pattern, and 56% of entries (clerical) are unclassified.
Time to the end of the file mixes settlements, withdrawals and judgments, so it is not the wait
for a hearing; that needs cumulative incidence with settlement as a competing event (not built).

## Decision-to-docket linkage (owner decision 2026-11-18; first version 2026-11-19)

Join published decisions (S3) to docket files (S10) by court file number, for the Federal Court
and Federal Court of Appeal. Purpose: attach the docket's nature of proceeding and filing date to
each decision, separate interlocutory from final decisions, measure filing to decision, and count
the files that end with no published decision. Coverage is limited to what the docket crawl holds:
FCA files from 2010, FC general files from 2018, and a sample of 1,000 FC immigration files per
year from 2023. The linked table is per-decision and stays in `data/processed/` (not published);
only aggregates go to the site.

Code: `estimate/linkage.py`, run by `courtdelay build`. Grain is decision x cited file number
(43,994 decisions, 46,819 pairs). Each pair gets a status against the docket frame: `linked`,
`sealed_dropped` (the file exists but we drop it), `in_frame_no_docket`, `sample_frame`
(immigration file in a sampled year, not drawn), `out_of_frame`, `bad_key` (truncated or malformed
number, 282 pairs). Vintage: A2AJ snapshot and docket crawl of 2026-11-19.

First results (inside the census frame only):

| Decisions citing | Pairs | Linked | Dropped by us | No docket found |
|---|---|---|---|---|
| FC `T` files, 2018 on | 3,779 | 3,096 (82%) | 680 (18%) | 3 |
| FCA `A` files, 2010 on | 4,393 | 3,854 (88%) | 533 (12%) | 6 |

- **Census completeness.** Only 12 of 8,179 cited in-frame file numbers were not found by the
  crawl (including 3 `A` numbers cited by FC decisions, likely typos). The census is not missing
  files that produce decisions.
- **Decision date against docket entries.** A judgment or order entry falls on the decision date
  for 88% of linked FC pairs and 86% of FCA pairs (92% and 94% within a week).
- **Hearing date against docket entries.** Where the decision states a hearing date, a recorded
  hearing entry falls on it for 72% (FC) and 70% (FCA); 77% and 72% within a week. The rest are
  mostly matters decided in writing or hearings the docket records under another entry type.
- **Hearing to judgment, FC decisions from 2016.** All decisions: n = 14,157, median 26 days.
  Linked `T` files: n = 2,500, median 28 days, 50% within 28 days, 43 at a year or more. Where the
  docket confirms both dates (n = 1,943): median 27, 22 at a year or more. So the centre of the
  distribution does not depend on the decision header's dates; the far tail partly does (7 of 29
  linked decisions at a year or more have a later docket hearing that shortens them).
- **Not yet reliable: interlocutory versus final.** The docket `judgment` entry type matches any
  entry that mentions a judgment, so "last judgment on the file" is not a usable marker of the
  final decision (FCA: only 15% of linked decisions are "last"). Needs the FCA closing rule.

### Open issue: the confidentiality drop removes the largest files (found 2026-11-19)

S10 drops a whole file when any entry carries the court's confidential flag or its text matches
`sealed`, `confidential order`, `publication ban` (rule from the handoff, section 6). 2,115 files
are dropped. 94% of them are dropped by the text match alone, not by the court's flag, and no
dropped file is confidential throughout except one. The drop is not neutral:

| | All files | Files with a published decision | Files with 50+ entries | Median entries, dropped vs kept |
|---|---|---|---|---|
| FC `T` | 5.8% dropped | 14.1% | 25.3% | 59 vs 12 |
| FCA `A` | 8.8% dropped | 11.6% | 18.1% | 64 vs 35 |

What triggers the drop (files can match more than one):

| Trigger | FC `T` | FCA `A` |
|---|---|---|
| Entry text says `sealed` (typically "Sealed envelope pursuant to the Confidentiality Order...") | 965 | 474 |
| Entry text says `confidential order` / `confidentiality order` | 686 | 330 |
| Court's own confidential flag on an entry | 249 | 43 |
| Entry text mentions a publication ban | 12 | 6 |

Read locally, the matching entries are sealed envelopes and protective or confidentiality orders
over commercial evidence. The text match also catches entries that say the opposite ("will not be
bringing a motion for a confidentiality order", "no publication ban in place"). The drop is
concentrated by subject: 45% of Patented Medicines (NOC) actions, 46% of final patent appeals, 32%
of patent infringement actions, 59% of Special Import Measures appeals, 34% of trade tribunal
reviews and 25% of access to information applications, against 6% of ordinary judicial reviews.
The court lists all of these files publicly and publishes their decisions.

Effect on durations, measured by parsing the dropped files in memory (filing to final disposition,
Kaplan-Meier median, days):

| Cohort | Kept files only | With dropped files restored |
|---|---|---|
| FC `T`, filed 2018-2022 | 399 (n = 9,250) | 404 (n = 9,879) |
| FCA `A`, filed 2010-2016 | 308 (n = 3,237) | 308 (n = 3,466) |
| FCA `A`, filed 2017-2022 | 437 (n = 1,953) | 441 (n = 2,181) |
| FC patent files, filed 2018-2022 | 301 (n = 310) | 367 (n = 503) |

So court-wide medians barely move, but any breakdown by subject is distorted (patent files lose
their longer half) and counts of files and decisions are short by 6% to 9%. No entry text or names
are kept for any file either way. Options for the owner: (a) keep these files and drop only the
flagged entries, still dropping the 18 publication-ban files whole; (b) keep dropping and state
the bias; (c) drop a file only when the court's own flag is set. Unchanged until decided.

### Immigration and Tax Court links (first version 2026-11-19)

Same code, run by `courtdelay build`; per-decision rows in `data/processed/links/`.

**FC immigration decisions to Refugee Law Lab dockets (S3 to S4).** 22,973 decision x file pairs;
19,482 linked. For decisions dated 2001 to 2022, 94% to 99% link each year. 521 cited files have
no docket: 191 are 2022 files, mostly numbered above IMM-11000-22, where the Refugee Law Lab
scrape stops (last filing date 2022-11-07), so they are outside the frame rather than misses; the
other 330 cannot be told apart from the 667 files S4 drops for sealing markers, whose numbers are
not kept. A judgment or order entry falls on the decision date for 80% to 97% by year, and a
recorded hearing falls on the decision's hearing date for 71% to 86%. Decisions after the
November 2022 scrape link to a file but have no entry to match.

- The decision header's *first* hearing date precedes the file's filing date for 12% of linked
  decisions (2,281): it is picking up another date in the header. The *last* hearing date, which
  reserve time uses, does so for under 1% (158). Reserve time is unaffected; `hearing_dates_n` and
  any multi-day measure from S3 are not reliable.
- **Coverage of published decisions is thinner for files filed 2012 to 2015.** Per file with leave
  granted (a denominator that does not use the hearing classifier), the share with a published
  decision in A2AJ is 57% to 62% for files filed 2005 to 2011, 35% to 48% for 2012 to 2015, and
  54% to 62% for 2016 to 2021. Per file with a recorded hearing the pattern is the same (75% to
  81%, then 46% to 67%, then 85% to 96%), though the 2012 figure is also pulled down by 491 files
  with a hearing entry and no leave granted, which is a classifier problem. Any series built on
  published decisions alone (ours in E3, and others using A2AJ) has a thinner base in those
  years. Not yet known whether the gap is in A2AJ or in what the court published.

**Tax Court decisions to Tax Court dockets (S3 to S12).** The S3 file-number pattern required a
`G` or `I` suffix, so it missed EI, CPP, OAS and application files: fixed, and 1,692 Tax Court
decisions gained a file number (no other court changed). Of 967 pairs citing files from 2018 on,
956 link; the 11 misses are 6 file numbers. A hearing entry ("Minutes of Hearing") falls on the
decision's hearing date for 79% and within a week for 93%. The docket's judgment entry is on the
decision date for only about 42% but within a week for 94%: the docket records it a few days
later. Share of files filed 2018 to 2022 with a published decision: General 4.1%, Informal 3.2%,
EI 9.1%, CPP 8.7%, Applications 2.6%; among files with a hearing entry, 13% (General) and 8%
(Informal). Most Tax Court files end without published reasons, so decision-based measures for
this court describe a small and selected group.

### FC immigration 2022 overlap sample (run 2026-11-19)

300 files drawn at random from IMM-1-22 to IMM-13672-22 on the court's site. 243 are also in the
Refugee Law Lab series (S4); the other 64 parsed files are numbered above IMM-11000-22, where S4
stops. For the 243, comparing S10 entries dated up to S4's scrape date:

- Stage dates agree wherever S4 has one: leave decision 47 of 47 (and the result, 47 of 47),
  discontinuance 71 of 71, judgment 4 of 4, hearing 2 of 2, final disposition 106 of 106.
- Entry counts by type are identical for 95% of files; the rest differ by a few entries the court
  added or back-dated after the scrape (3 files have a stage date on or before the scrape date
  that S4 lacks).
- **Bug found and fixed:** S10 filing dates were one day early for about 60% of files filed in
  daylight-time months (the timestamp conversion assumed standard time all year). After the fix
  filing dates match S4 for 243 of 243. All S10 durations from filing shift by at most one day.
- 44% of these files were disposed when S4 was scraped; 98% are now. The two series are measured
  alike and can be read as one, with S4's 2022 cohort heavily censored.

### Further linkages (owner decision 2026-11-18: build all)

1. **FC immigration decisions to Refugee Law Lab dockets (S3 to S4)** by IMM file number,
   1997-2022. No new crawling.
2. **Tax Court decisions to Tax Court dockets (S3 to S12)** by file number, 2018 on. Also a test
   of whether the docket's "Minutes of Hearing" date matches the hearing date printed in the
   decision.
3. **Hearing dates in decisions against docket hearing entries (S3 to S4, S10)**, to repair the
   docket hearing classifier.
4. **Appeal chains** from a Tax Court or Federal Court file to its FCA appeal and on to the SCC,
   using the decision under appeal. Report the match rate; unmatched appeals are not dropped
   silently.
5. **FC immigration 2022 overlap sample (S10)**: about 300 files from the court's site, to check
   that the Refugee Law Lab series (to 2022) and our sample (from 2023) are measured alike.
   Approved 2026-11-18; runs at the approved 3 s spacing after the FC general crawl.
6. **Judges in decisions to the judicial complement (S3 to S9).** Judge names are used only as a
   linking key. No published table, chart or text names an individual judge; per-judge figures
   are published only as anonymous distributions.

All linked tables are per-file or per-decision and stay in `data/processed/`.
