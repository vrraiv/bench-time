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
