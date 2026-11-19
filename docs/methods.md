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

## Decision-to-docket linkage (planned, owner decision 2026-11-18)

Join published decisions (S3) to docket files (S10) by court file number, for the Federal Court
and Federal Court of Appeal. Purpose: attach the docket's nature of proceeding and filing date to
each decision, separate interlocutory from final decisions, measure filing to decision, and count
the files that end with no published decision. Coverage is limited to what the docket crawl holds:
FCA files from 2010, FC general files from 2018, and a sample of 1,000 FC immigration files per
year from 2023. The linked table is per-decision and stays in `data/processed/` (not published);
only aggregates go to the site.

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
