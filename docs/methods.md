# Methods: estimands, estimators, caveats

Every number the site publishes carries: the estimand definition below, n, an uncertainty range,
the data vintage (fetch date; the per-request log `data/manifest.jsonl` is kept locally, not in the repository), the source id, and the bias statement.
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
Second precondition (2026-11-21): the period must be near steady state. Rows carry
`steady_state_ok`, false when commenced ÷ dispositions is outside 0.8–1.25
(`stock_flow.STEADY_BAND`; the band is a judgment call). For the Federal Court this fails in 21
of 93 quarters, including every quarter from 2025 (ratios 1.3 to 3.0), where W at the disposal
rate reaches 734 days and overstates the time a file takes. The site shows those quarters as
hollow markers and says not to read them. The annual `publishable` flag does not yet include
this condition.

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

### Federal Court pending proceedings: checks and benchmark (2026-11-21)

The pending series on the site is the Court's published stock (S8, total row of each quarterly
Activity Summary), not a count of ours. It rises from 6,301 at end-2019 to 15,627 at end-2024,
28,098 at end-2025 and 43,536 at 30 September 2026; immigration leave applications are 37,873 of
the last figure, non-immigration 5,663 (2,760 at end-2019).

Checks on our reading of the pages:

- Total and immigration rows for end-2019, end-2025, June and September 2026 compared by eye
  with the cached pages: identical.
- Subject rows sum to the total for filings, dispositions and pending in all 30 quarters from
  2019 (differences of 1 file in September 2019 and 9 in September 2023). Not checked before
  2019, where the row hierarchy differs.
- End-2019 stock plus published filings minus dispositions to September 2026 gives 44,648
  against 43,536 published (2.5%), the sum of the identity breaks already listed for 2021 and
  2023.

Benchmark from court-file records (`estimate/benchmark.py`, table
`s8_fc_benchmark_vs_court_files`, held back because it carries docket-derived pending counts;
shown on the review page). Flows are year to date.

| Component | Our count from | Ours ÷ Court's |
|---|---|---|
| Immigration filings, 2003–2021 by year | S4 dockets (census), by filing date | 0.998–1.006 |
| Immigration filings, 2023–2026 by quarter | S10 immigration sample, share of the year's sampled files dated by the cut-off × top file number | 0.92–1.09; the Court's figure is inside the 95% sampling interval in 14 of 15 quarters (June 2026: 1.09) |
| Non-immigration filings, 2018–2026 | S10 census of `T` files, registrations excluded | 1.008–1.033 |
| Non-immigration dispositions, 2022–2026 | same | 0.954–1.001 (2026 to 30 September: 0.959) |
| Immigration pending, 2023–2026 by quarter | S10 immigration sample (files opened from 2022), open at the cut-off, scaled by stratum | 0.96–1.12; 1.05 at end-2024, 1.10 at end-2025, 1.05 at September 2026 (39,844, interval 38,450–41,239, against 37,873) |
| The same, leaving out files not yet numbered at the cut-off | as above | 0.95–1.11; inside the sampling interval in all nine quarters from September 2023 to September 2025, then 1.05–1.09 |

Reading:

- The filings side of the rise is corroborated to within a few percent in every period, and the
  third-quarter 2026 jump is in the filing dates: sampled files dated in the three quarters of
  2026 number 209, 253 and 368, or about 6,900, 8,400 and 12,200 filings, against the Court's
  6,650, 7,403 and 13,591.
- **The 2026 entry format (found and fixed 2026-11-21).** The Registry's entries change format
  at 1 January 2026 (`LEGACY_RE_IND` goes from `Y` to `N`; a few appear from September 2025). A
  final decision is now written "Order (Final) dated …", "Reasons - for Judgment and Judgment
  (Final) …", "Decision (Final) …", "Ordonnance (final(e)) …"; other orders say
  "(Interlocutory)" or nothing; leave outcomes read "Result - Leave dismissed" or "Résultat -
  Demande d'autorisation rejetée"; a withdrawn entry reads "Recorded entry cancelled." The old
  rules matched none of this, so no entry dated 2026 was marked final and only discontinuances
  ended a file: our share of the Court's dispositions fell to 0.72–0.74 (immigration) and
  0.63–0.73 (non-immigration) in every quarter of 2026. Now recognised
  (`FINAL_2026_RE`, and additions to the leave, result, removed-entry and hearing-date rules in
  `s4_rll_fc_dockets.py`). Translations, corrections to reasons, costs assessments and documents
  "placed on file" carry the qualifier of the decision they belong to and are not counted as the
  ending. Effect of the re-parse: 1,206 files gain or change an ending (816 Federal Court
  non-immigration, 158 immigration, 232 Federal Court of Appeal), all but 11 dated 2026; 308
  leave decisions are newly recognised. Dispositions for 2026 are back to 0.93–0.98 of the
  Court's by quarter (non-immigration) and 1.00–1.07 (immigration, sampled). The published cohort
  tables move: share of files ended, Federal Court 2025 cohort 48% to 59%, Federal Court of
  Appeal 2025 cohort 31% to 58% and 2024 cohort 69% to 86%.
- Side effects on older entries, all small: the hearing date moves on 7 files (minutes whose
  result line shows a case conference are no longer taken as the hearing), and the recorded
  result of a hearing or judgment changes on 64 files (the result is now read from the words
  after "Résultat" before the rest of the entry). S4 re-parsed with these rules 2026-11-22:
  no ending, leave date or leave result changes on any of its 218,639 files (the 2026 forms
  match nothing in data that stops in 2022); a hearing result changes on 288 files and a
  scheduled hearing date is gained on 42; one published cell moves (2017 cohort, hearing to
  judgment, 90th percentile 128 to 127 days).
- Not done: a judgment or order in the 2026 format with no qualifier at all is not treated as
  an ending (about 40 judgment entries and 690 orders in files still open, most of them
  certainly interlocutory); English minutes in the 2026 format name the subject only sometimes,
  so a few conferences may still be read as hearings.

Residual after the fix (immigration pending, ours above the Court's by 5% at September 2026 and
by 10–12% in the three quarters before):

- **Files filed but not yet numbered.** File numbers are issued in sequence when the Registry
  opens a file. Sorting the sampled files by number, a file cannot have been numbered before the
  latest filing date among lower-numbered files. By that lower bound, numbering followed filing
  by 0 to 1 days (median) and about one to two weeks (90th percentile) until early 2025; from
  March 2025 to July 2026 the 75th percentile is 3 to 34 days and the 90th 13 to 53 days; from
  September 2026 it is back to 0 to 3 days. The first 500 numbers of 2026 went mostly to files
  filed in the second half of December 2025. The Court's counts follow the opened file, ours the
  filing date, so our stock is ahead by the files waiting for a number: at least 630 at
  end-2025, 560 at March 2026, 1,560 at June 2026 and 230 at September 2026 (lower bounds, ±170
  to ±430). This also explains why the Court's year-to-date filings ran 4% and 9% below ours in
  March and June 2026 and caught up in September, and part of the 13,591 filings it reports for
  the third quarter.
- **Leaving those files out**, our estimate is within sampling error of the Court's in every
  quarter from September 2023 to September 2025 (ratios 0.95–1.06), then sits 1,700 to 2,200
  files above it from December 2025 on (ratios 1.05–1.09; sampling error about ±1,000 to ±1,400).
- **That step arises in the fourth quarter of 2025.** The Court reports 4,559 immigration
  dispositions in that quarter; our sample gives 3,550 (±610), a ratio of 0.78 against 0.93–1.12
  in the ten other quarters of 2024–2026. The sampled files we count as open at end-2025 show
  no unrecognised endings in that quarter (their entries with words such as dismiss, final,
  closed, settle are leave grants, motions and letters). Of the files we count as open at
  September 2026, 94% have no decision of any kind recorded, and entries that look like an
  unmarked ending account for about 130 files of 39,800.
- **Not explained.** Candidates not tested: dispositions in late 2025 of immigration files
  opened before 2022, which our sample does not cover (published decisions show no such
  judgments, but an administrative closure would not appear there); a year-end adjustment in
  the Court's count; chance (the quarter is about three standard errors out, one of eleven
  quarters). A sample of pre-2022 immigration files from the Court's file search would test the
  first; it needs the owner's approval as a new stratum.
- **Older files tested and ruled out (2026-11-22, owner approval the same day).** Frame: the
  7,498 immigration files in the Refugee Law Lab dockets (S4) filed before 2022 with no ending
  recorded at the November 2022 scrape. List sample re-read from the Court's file search, in
  seeded random order within four filing-year groups (`IMM-PRE2022` in the S10 module; stored
  apart in `data/processed/s10/imm_pre2022.parquet` so no other table counts them): 300 of 1,092
  filed in 2021, 150 of 347 from 2018–2020, 150 of 4,977 from 2011–2017, 60 of 1,082 from 2010
  or earlier. 660 files, no failed request; 17 numbers drawn returned no file (5 of 305 and 12
  of 162 in the two recent groups). Files S4 shows as ended are assumed to have stayed ended.
  - None of the 660 ended in the fourth quarter of 2025, and one ended in the whole of 2025
    after March. The step is not older files closing. Scaled endings of these files: about 530
    in 2023, 85 in 2024, 7 in 2025, 8 in 2026; they are now in the benchmark's immigration
    dispositions row, which is 0.95–1.06 of the Court's by year and 0.78 for that one quarter
    (3,550 against 4,559), 0.93–1.26 in the fourteen other quarters from January 2023 to
    September 2026 (1.26 is July–September 2023; the rest are 0.93–1.12).
  - None of the 210 sampled files from before 2018 has an ending or any entry after 2017. They
    are not pending in the Court's sense (its whole immigration stock at end-2019 was 3,541) and
    are not added to our stock.
  - Of the 234 sampled files from 2018–2021 still without an ending (about 700 scaled), the
    last entry is a copy of a judgment or order made in another file for 111 of the 119 from
    2021 and for at least 40 of the 115 from 2018–2020; 97 of the 2021 files belong to one
    managed group. The group's lead file shows no ending in S4, so whether these files are
    ended is not established. If they are pending in the Court's count, our estimate plus
    these would sit further above the Court's, not closer.
  - In our own 2022–2026 sample, 33 of the 1,382 files without an ending carry a copy of a
    decision from another file (about 770 files scaled; 12 are copies of a discontinuance, about
    300 scaled). The lead files are mostly outside the sample, so the rule cannot confirm them.
    An upper bound of 770 on this source of excess, against a gap of 1,700 to 2,200.
  - Also unadjusted: 0.3% to 2.3% of the numbers drawn for the yearly samples returned no file
    (24 of 1,024 for 2025). The estimate scales by the top number as if every number were a
    file; if those numbers were never used, the September 2026 stock is overstated by about 550.
  - Both pieces would lower our estimate in every quarter, not only from late 2025: they bear
    on the level (up to roughly 850 to 1,300 files), not on the step. The excess of Court
    dispositions in the fourth quarter of 2025 remains unexplained. For 2023 our dispositions
    run 6% above the Court's, with its figure just below our interval.
- Also noted: the Court's own immigration stock fell by about 380 more than its flows imply in
  the first quarter of 2024 (the identity break flagged for that quarter).
- **Non-immigration.** Our open files (opened from 2018) are 11–13% above the Court's
  non-immigration pending in every quarter from 2024 (6,373 against 5,663 at September 2026),
  although the Court's figure also includes files opened before 2018. Reviewed 2026-11-22
  (below).

Non-immigration open files: where the excess sits (2026-11-22). All from the local cache; no
new requests.

- **By subject.** Mapping our `nature` field to the Court's subject rows, at 30 September 2026:
  citizenship 1,446 open against 1,443 pending, admiralty 258 against 247, intellectual property
  486 against 501, Aboriginal law 189 against 305 (the Court's figure holds files opened before
  2018), judicial review 2,753 against 2,418, Crown litigation and other appeals 1,241 against
  749. Filings match the Court's to within 3 a year in citizenship, admiralty and intellectual
  property and to within 17 in judicial review; the excess filings (28 to 57 a year) are all in
  the Crown and other group. Prairie Grain Advance Payments files (19 to 50 a year) are about
  that size and lost their own row in the Court's table after 2018, but the yearly counts do not
  match one for one, so this is a candidate only.
- **Do the Court's extra dispositions concern files in our records?** Partly. The Court's count
  includes endings of files opened before 2018, which we do not hold: about 100 in 2022 falling
  to about 25 in 2025 by a rough projection of our cohorts' ending rates onto the Court's
  2005–2017 filings (1–5% of its dispositions). The rest are endings in our files that the rules
  do not see, next item.
- **Lead-file orders.** Of the 2,107 files opened before 2025 that we count as open, 1,162 have
  had no entry for two years. In 381 of them the last decision is a copy of an order made in
  another file ("Copy of Order dated … placed on file. Original filed on Court File No. …") and
  that order ended its own file on that date. Two orders account for 287: one in April 2020
  dismissing a list of actions against the Crown (213 files), one in June 2023 striking the
  statements of claim in another list (74). The copy carries no final-decision marker, so our
  rule leaves the file open. The Court counts them: its Crown litigation dispositions for 2020
  are 480 against our 204, and 423 once these are counted. Recorded per file as
  `lead_order_end_date` and `lead_order_file` (`add_lead_file_endings` in the S10 module), kept
  apart from `final_disposition_date` at first; counted in the tables from the same day (see
  the rules adopted below). With them, open files at September 2026 are 5,992 against 5,663 (6% above,
  from 13%), and the Crown and other group 926 against 749.
- **Other dormant files (806), by words in their entries; not read one by one.** About 160 show
  enforcement steps after a judgment (writs, garnishment, default judgment); about 150 an order
  or judgment of their own with an outcome but no final marker; about 100 a copy of a judgment
  or discontinuance from a companion file (another 206 files belong to a group whose lead file
  has ended, 50 of them consolidated under one 2018 application discontinued in 2025); 70 a
  notice of settlement or abandonment; 66 a stay; 234 none of these.
- **Level against growth.** Lead-file orders explain the level of the gap, not its growth.
  The excess goes from 246 (end-2023) to 710 (September 2026) without them and from −107 to 329
  with them: about 440 more either way, and only 28 lead-order endings are dated 2024–2026.
  The growth is in two places. Crown and other: about 134 from the extra filings of 2024–2026
  (57, 49, 28), where we count more dispositions than the Court, not fewer. Judicial review:
  open excess up from 111 to 335 with filings matching, dispositions short by about 17, 92 and
  56 in 2024, 2025 and 2026. Of the judicial review files we count as open, 63 have a judgment
  entry dated 2025 and 46 one dated 2026 with no final-decision marker (201 in all years); the
  S10 rule does not end a file on an unmarked judgment. The counts are close to the shortfall
  but the entries have not been read, so this is the leading candidate, not a finding.
- **Rules adopted 2026-11-22 (owner decision).** Why our count differed although we hold the
  files: the Court publishes totals only, never the list of files behind them, so its count
  cannot be looked up file by file; we infer endings from each file's entries, and a file whose
  own entries never say it ended stays open in our count. Where the file's record shows the
  ending by another route we now count it. We do not scale our counts to the Court's totals:
  that would hide real differences and would not say which files ended when, which the
  duration tables need.
  - *Lead-file order*: a file carrying a copy of a decision that ended the file it was made in,
    on that date, ends on that date (`final_disposition_source = lead_file`; 377 Federal Court
    files, 72 Federal Court of Appeal).
  - *Unqualified 2026 judgment*: a judgment in the 2026 entry format with no "(Final)" or
    "(Interlocutory)" qualifier, not a copy, followed by no order, motion, hearing or direction,
    ends the file (`unmarked_judgment`; 30 Federal Court files, 1 immigration, all 2026). Of the
    538 open files with an entry classed as a judgment, 404 were motions for judgment,
    directions or copies, and 90 of the 134 real judgments are marked interlocutory; none of
    those is an ending.
  - Both are in the published cohort tables. Effect: share ended, Federal Court actions 2018
    cohort 74% to 92%, 2021 cohort 77% to 88%; Federal Court all files 2018 80% to 89%; 75th
    percentile, all files 2018, 1,387 to 804 days; Federal Court of Appeal 2018 cohort 92% to
    97% ended, 90th percentile 1,271 to 877 days. Medians move by 0 to 32 days (54 for 2019
    actions).
  - *Group ending, recorded but not counted* (`group_end_date`): a file carrying a copy of some
    decision from a file that has since ended, with no entry of its own more than 90 days after
    that ending (209 files; 57 judicial review files in 2025, 50 of them consolidated under one
    2018 application). Probably ended with the lead file; no entry says so. Benchmark only.
- **Tax-collection matters.** Our extra Crown-group filings track the Crown's tax-collection
  files (Income Tax Act and excise applications, jeopardy collection orders, search warrants)
  year for year: excess 54, 43, 34, 9, 29, 57, 49, 28 for 2019–2026 against 53, 38, 34, 27, 33,
  47, 40, 30 such files (303 against 302). Prairie Grain files fit less well. The Court's count
  of proceedings appears to leave these out; it publishes no definition, so this is inferred.
  146 of them were open at September 2026, up from 100 at end-2022. The benchmark leaves them
  out; the cohort tables keep them (owner's decision pending).
- **Result.** With the two adopted rules, group endings, and tax-collection matters left out:

  | | Filings, ours − Court | Dispositions, ours ÷ Court | Open files, ours ÷ Court pending |
  |---|---|---|---|
  | 2022 | −1 | 0.955 | 0.907 |
  | 2023 | +2 | 1.018 | 0.908 |
  | 2024 | +11 | 1.002 | 0.955 |
  | 2025 | −3 | 0.984 | 0.982 |
  | 2026 to 30 September | −1 | 0.963 | 1.001 |

  Without group endings the last column is 0.928, 0.933, 0.981, 1.013, 1.029. Filings now agree
  to within 11 files a year. The stock ratio still rises about 9 points over four years. Two
  things push it up: the Court's figure holds files opened before 2018, a share that shrinks as
  they close (Aboriginal law alone: 305 pending against our 189); and judicial review, where
  our dispositions remain short by 11, 35 and 45 in 2024–2026 (2–3%) and our open files are
  155 above the Court's at September 2026. That judicial review residual is the part still
  unexplained; candidates are orders that end a file without a marker (dismissal for delay,
  consent orders) and settlements never followed by a discontinuance. Crown and other is now
  747 open against 749.
- **Federal Court of Appeal (investigated 2026-11-22).** The first comparison (our endings
  85–92% of the court's) was against the wrong total. The court's TOTAL row includes
  "Preliminary Applications" (31 to 65 commenced and disposed a year, 6 to 10 pending): motions
  brought before an appeal exists, numbered apart from appeal files and not in our census of
  `A` files. With that row taken out of the court's figure: filings ours ÷ court 0.993–1.025
  (2019–2026, within 8 files a year); dispositions 0.94–1.00 (short by 1 to 16 a year); by
  category (appeals from Federal Court final and interlocutory judgments, Tax Court appeals,
  judicial reviews, statutory appeals) filings agree within 9 in every year checked. Open files
  remain above the court's pending: 598 against 539 at end-2019, 636 against 520 at September
  2026, a gap growing about 8 a year, which is the yearly shortfall in endings accumulating.
  Of 132 appeal files with no entry for 18 months, 23 ended with a copy of a notice of
  discontinuance (now counted, next item), about 50 carry a copy of a decision from another
  file, 10 a judgment of their own without a final marker, 10 a status review, 44 nothing
  recognisable. Rows for this court are in the benchmark table (`fca_benchmark`).
- **Copied discontinuance (adopted 2026-11-22).** A copy of a notice of discontinuance filed in
  another file and placed on this one ends the file when no order, motion, hearing or direction
  follows (`final_disposition_source = copied_discontinuance`; 78 Federal Court files, 23
  appeal files, 14 sampled immigration files). With it, Federal Court non-immigration open
  files are 0.999 of the Court's pending at end-2025 and 1.017 at September 2026 (0.975 and
  0.995 counting group endings), and the immigration pending estimate at September 2026 is
  39,452 (4% above the Court's; 39,220 leaving out files not yet numbered).
- **Population of the published tables (owner rule 2026-11-22: match the court's definition and
  say what it includes).** Federal Court cohort tables: `T` files, less registrations of
  tribunal decisions and certificates, less the Crown's tax-collection matters (inferred, see
  above). Appeal tables: `A` files; the court's preliminary applications have no `A` file.
- **What the courts publish about their definitions (searched 2026-11-22).** Nothing on the
  Federal Court's 93 quarterly Activity Summary pages, its statistics and reports pages, or the
  appeal court's statistics page beyond the tables themselves (one note records a re-posted
  quarter). The Courts Administration Service annual reports carry a glossary: "Dispositions:
  proceedings concluded by way of judgment, discontinuance or other documents"; "Proceedings
  instituted or filed" there includes certificates and tribunal decisions filed for
  enforcement, which the Federal Court's own Activity Summary evidently does not; and their
  pending tables break the stock into not perfected, perfected, consolidated, reserved,
  scheduled and stayed, so consolidated and stayed files count as pending. No document says
  which file types the Activity Summary leaves out. Not searched: strategic plans, departmental
  results reports, anything outside the three courts' sites. A question for the Registry or the
  practitioner is drafted in the closing notes of this session.
- **Reading.** For 2024–2026 the Court's extra dispositions are almost entirely of files in
  our records (older files: about 25 to 30 a year). The level of the excess is files ended in
  substance without an ending entry of their own. The published Federal Court cohort medians
  are little affected (381 of 23,900 files) but upper quantiles for 2018–2021 actions are
  overstated. The same rule finds 72 Federal Court of Appeal files (2010–2025, 18 in 2019),
  also not yet counted in the published tables.
- Highest immigration file number cited in published decisions (S3) is within 1–2% of the
  Court's yearly immigration filings for 2012–2025 (6% in 2020). It is not usable within a year:
  numbers are not issued in filing-date order.
- About 900 files numbered for 2026 carry a late-2025 filing date (27 of 1,011 sampled; 1 to 7 a
  year in 2023–2025): files that waited for a number over the year end (see the residual above).
- S4 open-file counts are 1.2 to 4 times the Court's immigration pending (files with no ending
  found), so S4 benchmarks flows only.
- All of these sources are the Court's own registry seen through different windows. No count
  from outside the Court was found; the Court's historic workbook (new proceedings by year) is
  not in the cache and would only check the parse.

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

Results (inside the census frame only; all files kept, see the decision below):

| Decisions citing | Pairs | Linked | No docket found |
|---|---|---|---|
| FC `T` files, 2018 on | 3,786 | 3,780 (99.8%) | 6 |
| FCA `A` files, 2010 on | 4,393 | 4,387 (99.9%) | 6 |

- **Census completeness.** Only 12 of 8,179 cited in-frame file numbers were not found by the
  crawl (including 3 `A` numbers cited by FC decisions, likely typos). The census is not missing
  files that produce decisions.
- **Decision date against docket entries.** A judgment or order entry falls on the decision date
  for 88% of linked FC pairs and 86% of FCA pairs (92% and 95% within a week).
- **Hearing date against docket entries.** Where the decision states a hearing date, a recorded
  hearing entry falls on it for 83% (FC) and 88% (FCA); 91% and 92% within a week (after the
  hearing-pattern fix below; 71% and 71% before it).
- **Hearing to judgment, FC decisions from 2016.** All decisions: n = 14,157, median 26 days.
  Linked `T` files: n = 2,836, median 33 days, 47% within 28 days, 70 at a year or more. Where the
  docket confirms both dates (n = 2,227): median 31, 41 at a year or more. With the
  confidentiality-marked files left out, the linked median was 28 (n = 2,500): those files carry
  longer reserve times. Non-immigration files run slower than the all-decision median, which is
  dominated by immigration (median 21).
- **Final versus interlocutory (added 2026-11-19).** A decision is final when the Registry's
  final-decision marker falls within 7 days of it (`decision_is_final`). Linked FCA pairs: 3,593
  final, 794 not. Linked FC pairs: 2,331 final, 1,449 not. Hearing to judgment, decisions from
  2016: FC final median 35 days (n = 1,956), FC interlocutory 29 (n = 880); FCA final 15
  (n = 1,862), FCA interlocutory 21 (n = 217). Of FCA files the Registry marks as ended by a
  judgment, 91% have a published final decision; FC files, 64%; files ended by an order, 12%.

## Federal Court and FCA docket census (S10): end of file and cohort tables (2026-11-19)

**End of file.** The Registry marks the entry that ends a file with "Final Decision". Entries
from the court's current system carry it on a line of its own after the entry text; the parser
looked only at the start of the text and so saw the marker on no FCA file and 314 FC files. Fixed:
the marker is on 4,697 FCA and 5,314 FC general files. A file ends at the first marked entry, else
at a discontinuance (`final_disposition_source` records which). The old second fallback, the first
entry that mentions a judgment, is off for S10: it was closing pending files (114 of the 391 FCA
files of 2025). S4 keeps it, and its end date changed for 1,865 of 217,972 files (0.9%).

**Registrations.** 3,207 Federal Court `T` files are tribunal decisions or certificates filed for
enforcement (Canada Labour Code copies of decisions, customs certificates). They are flagged
`is_registration` and left out of duration tables; 95% never get a closing entry.

**Check against the courts' published statistics** (S8, calendar years):

| | Filings: ours / court's | Dispositions: ours / court's |
|---|---|---|
| FCA 2014-2025, excluding the court's "Preliminary Applications" | 99.3% to 102.5% each year | 93.9% to 99.5% each year |
| FC non-immigration 2023-2025, registrations excluded | 100.8% to 101.9% | 97.4% to 100.2% |

Counting registrations puts FC filings 13% to 18% above the court's, so the court leaves them out
too. The disposition shortfall is files that ended with neither a marker nor a discontinuance.
It accumulates: our count of FCA files pending at year-end is 9% above the court's for 2014 and
42% above for 2025 (about 200 files). Pending stocks should come from the court's tables, not the
census; cohort durations treat those files as still open, a small upward bias in upper quantiles.
Two fallbacks for unmarked endings were tested and recovered under 2 points a year, so neither
was adopted.

**Cohort tables** (`s10_fc_fca_km_by_cohort`, `s10_fc_fca_file_outcomes_by_cohort`; published, no longer held out of
`site/src/data`). Kaplan-Meier, filing to end of file, by filing year and proceeding group,
bootstrap 95% intervals, censored-tail rule as for S12. Median days:

| Filing year | FCA all | FC all | FC judicial review | FC actions |
|---|---|---|---|---|
| 2010 | 272 (259-289) | | | |
| 2014 | 345 (329-362) | | | |
| 2018 | 408 (395-441) | 381 (350-420) | 358 (333-386) | 545 (469-656) |
| 2020 | 499 (479-539) | 389 (365-421) | 330 (302-389) | 461 (396-520) |
| 2022 | 403 (365-441) | 273 (261-284) | 256 (239-269) | 547 (481-598) |
| 2024 | 387 (352-421) | 271 (251-288) | 257 (223-277) | 364 (330-420) |

Cautions: 2025 and 2026 cohorts are still filling and their medians are not stable. FCA s. 28
judicial reviews of 2012 show a median of exactly 526 days because a block of related files ended
on one day. FC citizenship files rose from 178 (2023) to 1,420 (2025). About 350 actions against
the Crown from 2018-2021 have no entries since 2020 and count as open.

**Hearing entries (fixed 2026-11-19).** The hearing pattern missed the Registry's French minutes
("L'audition de cette affaire a lieu...", "... En présence de ... Matière en litige") and the
appeal court's English wording ("This matter comes on for hearing"): about 6,300 entries in S10.
It also took a case management conference, mediation or motion as "the hearing" when one came
first. Both fixed; `hearing_date` is now the first hearing entry that is not one of those.
Checked against linked final decisions: a docket hearing entry falls on the decision's hearing
date for 90% of FCA and 87% of FC decisions (70% and 72% before), and for 93% of FC immigration
decisions in S4 (78% before). In S4 the share of leave-granted files with a recorded hearing rose
from 47-64% to 53-76% by filing year. 3,256 hearing entries still state no subject.

**Appeal chains (first version 2026-11-19).** An appeal's opening entries usually name the file
appealed from; `appeal_from_file` reads it (73% of appeals from the Federal Court, 60% from the
Tax Court). Linked to lower files in S10, S4 and S12: 1,015 Federal Court and 166 Tax Court
chains; another 2,335 name a lower file outside our data (Federal Court files before 2018,
immigration files after 2022, Tax Court files before 2018). Legs: filing in the lower court to
the notice of appeal, then notice of appeal to the end of the appeal. The lower file's own end
date is not used, because a Tax Court file stays open until the appeal returns and an
interlocutory appeal is taken mid-file. Where the docket also states the date of the decision
appealed from (321 chains), the notice of appeal follows it by a median of 28 days. Median days,
completed chains (`link_appeal_chains_by_year`, not yet on the site):

| Appeal filed | Origin | Chains | Filing to notice of appeal | Appeal | Total |
|---|---|---|---|---|---|
| 2019 | Federal Court, final | 51 | 342 | 403 | 778 |
| 2021 | Federal Court, final | 96 | 601 | 438 | 1,056 |
| 2023 | Federal Court, final | 71 | 516 | 403 | 927 |
| 2023 | Tax Court | 21 | 1,372 | 433 | 1,818 |

Validation: where both the appeal and the lower file have a published decision (431 chains), the
appeal decision cites the lower decision in 89%. For final Federal Court appeals, the lower file
has a final-decision marker in the 60 days before the notice of appeal in 70% (82% have a marker
at all); for Tax Court appeals, a judgment entry in that window in 73%.

Bias: these totals are lower bounds, not a trend. Lower files start in 2018, so an appeal filed in
2019 can only link to a lower file that took under two years; the rise from 778 to 1,056 days is
mostly that truncation. Completed chains only. The Supreme Court leg covers heard appeals only (below).

Still unchecked on the end-of-file rule: 396 S10 files carry a final marker on more than one date
(median 78 days apart) and the first is used; and the last entries of about 136 FCA files from
2021 or earlier that still count as open have not been read. The cohort tables blank any
quantile that fewer than half the cohort has been followed long enough to reach, so 2025 and
2026 show no medians. S4 still uses the first-judgment fallback, for about 1% of its files.

**Supreme Court leg, heard appeals only (2026-11-19).** `build_scc_leg`. Since 2010, 95 Supreme
Court decisions are appeals from the Federal Court of Appeal; each states the FCA judgment it is
appealed from, all 95 are found among the FCA decisions, and 61 link on to an FCA court file (the
rest are files from before 2010). Median days, 2010-2026: FCA judgment to Supreme Court hearing
472 (n = 88); Supreme Court hearing to judgment 213 (n = 88); FCA filing to Supreme Court judgment
1,103 (n = 61). This route covers heard appeals only; leave applications come from the
Supreme Court's case pages (next paragraph). Only 4 chains reach a file in
the court below, too few to report. Held back with the other chain results.

**Supreme Court leave and appeal stages (2026-11-20).** `sources/s13_scc_cases.py`,
`build_scc_cases`. Every Supreme Court file opened from 2010 (9,131 case pages, none failed),
read 19-20 November 2026. Held back with the other chain results; not reviewed.

- *Unit and rules.* The unit is the file. The leave result is the Registry's short label at the
  end of the leave-judgment entry ("Granted", "Dismissed, with costs"), read for all 8,094
  decided files. 43 files carry leave judgments on more than one date (several applications, a
  remand, an oral hearing ordered first): the file's decision is the latest, and the most
  favourable result on that date. Judgments on applications to cross-appeal are not counted.
  330 files have no leave application (appeals as of right, references) and are kept out of the
  leave tables. The court appealed from is read from the leave judgment's wording, else from the
  page's "Lower court rulings" block; the two agree on the court for 99% of files and on the
  judgment date for 98%.
- *Check against the court's statistics (S5), 2011-2025.* Leave applications filed: ours are
  within 9 of the court's count every year. Appeals heard: within 1. Appeal judgments (2012 on):
  within 2. Average hearing to judgment: within 0.3 months. The court's "filing of application
  for leave to decision" average matches ours only when measured from the date the application
  was **complete** (within 0.4 months), not from first filing. Leaves granted differ by up to 7
  a year (the court counts applications; we count files at their latest decision).
- *Leave stage.* Kaplan-Meier from first filing to leave decision, pending files censored,
  discontinued applications censored at discontinuance. Median 125 days for 2010-2014 filings,
  147 for 2015-2019, 177 for 2020-2026. Courts appealed from are within a few weeks of each other; Quebec is
  consistently longer (median 160 days overall against 142-156 elsewhere; cause unknown). The time
  from filing to a complete application has grown (median 0 to 20 days, 90th percentile 51 to
  140), which the court's own average does not show. Granted: 12% of decided files in
  2010-2014, 8% since; Federal Court of Appeal 17% then 7-9%; Ontario 11% then 6-7%.
- *Heard appeals.* Completed intervals, pooled: leave granted to hearing median 252 days;
  appeal ready ("perfected") to hearing 56; hearing to judgment 178 (25th percentile 0: bench
  judgments); leave application to judgment 603.
- *Federal Court of Appeal chain.* 1,047 Supreme Court files name the FCA. 877 match our census
  by file number and 32 by citation (87%); 78 are FCA files from before 2010, 46 carry a motion
  number (`yy-A-n`, no appeal file), 10 give no number, 4 are not found. The Supreme Court's
  stated FCA judgment date is within 7 days of the end of our FCA file for 93% of linked files.
  For decided leave applications: FCA filing to FCA judgment median 395 days, judgment to leave
  application 60 (the deadline), application to leave decision 153, FCA filing to leave decision
  629 (n = 839). Where leave was granted, FCA filing to Supreme Court judgment 1,094 (n = 65),
  against 1,103 from published decisions above.
- *First ruling to appeal judgment below.* From the "Lower court rulings" block, for files that
  list an earlier ruling from a different court. Median 465 days for Ontario. A selected group
  (cases that went on to seek leave); not a measure of those courts in general.
- *Restriction notes.* 616 files (7%) have an entry mentioning a sealing order, a publication
  ban or confidential material. They are kept and counted, as for the Federal Court files; 28%
  of them were granted leave against 8% of the rest, so dropping them would bias the grant rate.
  Kept on the gated preview (owner, 2026-11-20). Settled 2026-11-25 (owner, on the practitioner's
  and an outside lawyer's advice that a ban does not take a case out of court statistics): these
  files stay in all aggregates, published or not; the Supreme Court tables remain held back for
  other reasons.
- *Open questions* are in the review list written to the owner's working folder on 2026-11-20:
  what "completed" means and why it now takes longer; how to treat remands and files with two
  leave decisions; what the FCA motion numbers are.

**Judges against complement (first version 2026-11-19).** `estimate/judges.py`. Federal Court
and Tax Court only (one judge decides). The judge's surname from the decision header is a
grouping key kept in `data/processed/links/`; the derived table
(`link_judges_vs_complement_by_court_year`) holds counts and across-judge distributions, and
withholds any distribution over fewer than five judges. Check: distinct judges issuing decisions
are 103% to 112% of the FJA complement (in office plus supernumerary) for the Federal Court each
year 2012-2025, the excess being turnover within the year. Federal Court 2023: 44 judges,
median 31 published decisions each; the median judge's median reserve time is 33 days, and the
10th and 90th percentile judges are at 7 and 126 days.

**Tax Court check against the court's statistics (S8, fiscal years).** Files filed in our census
are 92% to 97% of the court's "proceedings instituted or filed" for 2018-19 to 2022-23 (4,770 of
5,211; 4,439 of 4,684; 2,251 of 2,325; 3,285 of 3,426; 2,964 of 3,230). The gap is unexplained;
files the public search does not list are one candidate. First "Minutes of Hearing" entries in
our census (895, 1,358, 462, 672, 930) exceed the court's "files prepared for hearing and heard"
(888, 883, 273, 166, 713) even though our frame omits files from before 2018. So that entry is
written for more than trials, which supports practitioner question 1.

**Tax Court wait for a hearing** (`s12_tcc_hearing_wait_by_cohort`, provisional). Most files end
without a hearing, so this is a cumulative incidence with "ended without a hearing" as the
competing outcome (`survival.cif_table`), not a Kaplan-Meier median.

**Which sitting is the trial (changed 2026-11-24).** The practitioner's reading (round 1, TC-6) is
that "Minutes of Hearing" is kept for every kind of sitting: motions, status hearings and
conference calls as well as the hearing of the appeal. The census agrees: of 16,061 sitting days,
the entry most often follows "Case Management Conference scheduled". `classify_sittings` in
`s12_tcc_dockets.py` reads a sitting as the **trial** when (a) the minutes carry an exhibit list,
or a decision was reserved, a consent allowed or a withdrawal accepted "at hearing" that day; or
(b) the appeal had been set down ("Appeal Scheduled", "Continuation of Appeal scheduled",
"Appeal hearing reassigned", or for an application file "Application Scheduled") and no
conference, motion, status or show-cause hearing was waiting for its minutes. "Order Hearing
Fixed" and "Notice of Hearing" are not used as setters: they also accompany show-cause hearings
and motions. An adjournment before the hearing cancels whatever was set down last. Result: 7,228
trial sittings (45%), 8,030 other (50%), 803 unclassified (5%, counted as not a trial). Checks: a
judgment follows within 45 days after 39% of trial sittings and 4% of the others. Misses: among
files with a sitting and a judgment with no consent entry, no trial sitting is found in 47 of 287
General files (16%) and 32 of 1,776 Informal files (2%); some of those judgments decide motions.
Against the court's "Files prepared for hearing and heard in Court" (S8, fiscal years; definition
not published; our census has no pre-2018 files): files with a trial sitting 741 v. 713 (2022-23),
279 v. 166 (2021-22), 229 v. 273 (2020-21), 1,343 v. 883 (2019-20), 352 v. 888 (2018-19); files
with any sitting were 1,251, 1,387, 557, 1,820 and 895. A trial sitting dated before the filing
date (mostly converted extension applications) is not used. The rule is ours and inferred; it is
not the court's, and it is with the practitioner for review (round 2, TC-16). `first_hearing_date`
(any sitting) is kept beside the new `first_trial_date`.

Share of files with a first trial sitting within one and two years of filing (in brackets: the
earlier figure, which counted any sitting):

| Filing year | Informal, 1 year | Informal, 2 years | General, 2 years |
|---|---|---|---|
| 2018 | 16% (was 31%) | 30% (28-32) (was 41%) | 1.6% (1.0-2.3) (was 12%) |
| 2020 | 1% (was 6%) | 6% (5-8) (was 19%) | 1.3% (0.8-2.0) (was 13%) |
| 2022 | 7% (was 8%) | 23% (20-25) (was 26%) | 1.7% (1.0-2.2) (was 9%) |
| 2024 | 15% (was 18%) | 31% (29-34) (was 34%) | 3.7% (2.8-4.7) (was 12%) |

General procedure: about a third of 2018-2020 files had some sitting, about one in eight a trial
sitting. The low point for Informal files filed in 2020 is the pandemic closure.

**The court's public listing was incomplete from about 19 to 23 November 2026 (found and
resolved 2026-11-24).** The year listings returned 29,714 files on 16 November, about 4,700 on 19
and 23 November, and 29,626 again on 24 November (re-listed at 12:47 UTC; a search by number that
found nothing at about 02:00 UTC found the file at 12:50). During the gap the responses also
lacked the `APPELLANT_INITIALS` field, and the site's page script changed to display initials, so
the cause was most likely a site update in progress, not a removal of files; we do not know more.
Extension applications were mostly still listed during the gap (91%) and ordinary appeals mostly
not (9%). The entries endpoint answered for a delisted file throughout our test. Because the
weekly refresh had overwritten the cached listings, the parser now keeps a ledger of every file
ever listed (`_listing_ledger.json` in the raw folder; contains names, never exported); each file
carries `last_listed` and `listed_now`, and the refresh refuses a listing that shrinks. After the
24 November re-listing 29,614 of 29,780 files ever listed are listed now. Of the 166 that are
not, 134 are extension applications with no recorded status. **Re-lettered files:** 11 numbers
listed on 16 November are now listed under another letter (seven `APP` files now `I` or
unlettered; four unlettered files now `G` or `I`), which shows a file keeps its number when an
application becomes an appeal; the earlier listing is left out of the census as the same file.

### Confidentiality markers: files kept, markers counted (owner decision 2026-11-19)

**Decision:** S10 no longer drops files that carry a confidentiality marker. The court publishes
these files, so the markers are presumed to mean something narrower than a sealed proceeding. Each
file now carries `n_confidential_flag_entries`, `n_sealed_text_entries` and
`n_publication_ban_entries` so the earlier rule can be reproduced (`DROP_MARKED_FILES`). What the
markers mean goes to the practitioner in a second review document. Breakdown of the 2,119 files the old
rule matched (2026-11-19, entry wording read locally, names masked): court confidential flag 294
files; "sealed envelope" 804; confidentiality or protective order 983; publication ban 18 (4 with
wording of a ban granted). About 570 files match only through the court's seal on an issued
document ("sealed and issued copy") or an entry saying no confidentiality order is sought: these
were never confidentiality markers. In a flagged file the median is 3 flagged entries (about 5% of
the file); one file is flagged throughout. S4 (Refugee Law Lab) keeps its 667
marked files too (owner decision later the same day): 562 mention "sealed", 246 a confidentiality
order, 25 a publication ban.

**What the markers mean (outside lawyer, 2026-11-25; open-issues OI-1, OI-2, OI-5):** a
publication ban does not take a case out of the court's own statistics, so leaving banned files
out would break the match with the court's tables; they stay in. A *protective order* usually
covers documents the parties exchange before trial, is often agreed on consent and drawn broadly,
and covers only that exchange. A *confidentiality order* covers material before the court and is
construed narrowly because of the open-court principle. So the two should be counted separately:
a protective order is a weak signal of a contested file, a confidentiality order a stronger one.
Whether every "sealed envelope" entry reflects an order is still open (OI-1).

**Split counters (2026-11-25).** S10 and S4 files now carry `n_protective_order_entries`,
`n_confidentiality_order_entries` (entries mentioning each) and `protective_order_date`,
`confidentiality_order_date`: the first entry whose wording records an order *made* ("Protective
Order dated … rendered", "Sealed envelope pursuant to the Confidentiality Order …", "service of
…", French equivalents). A motion for an order, or a letter saying none will be sought, mentions
but does not count as made, so the dates are a lower bound on files with an order. Files with an
order made (FC/FCA, registrations excluded): FC `T` IP subjects 1,364 files, 264 protective, 123
confidentiality (66 both); FC `T` other 20,833 files, 75 and 134; FCA `A` 7,117 files, 53 and
129. Protective orders sit mostly in NOC (170 of 398 files) and patent, trade-mark and copyright
actions; confidentiality orders also appear in judicial reviews (51) and access to information
(21). Median days from filing to the order: protective 160 (FC) and 108 (FCA); confidentiality
333 (FC) and 87 (FCA). S4 (immigration): 35 files with a confidentiality order made, 3 protective.

*Landmark comparison* (an order needs the file to stay open, so a raw comparison of durations
favours marked files). Files still open one year after filing, grouped by the order made by then;
Kaplan-Meier median days remaining, 95% bootstrap CI, and the share of endings that were a
judgment:

| Group | Order by one year | n | Median days remaining | Ended by judgment |
|---|---|---|---|---|
| FC `T`, IP subjects | none | 521 | 341 (309–376) | 22% |
| | protective only | 127 | 225 (194–244) | 9% |
| | confidentiality | 27 | 269 (136–408) | 42% |
| FC `T`, other subjects | none | 7,193 | 427 (409–446) | 41% |
| | protective only | 31 | 411 (319–615) | 21% |
| | confidentiality | 66 | 412 (160–627) | 55% |
| FCA `A` | none | 3,102 | 164 (161–174) | 79% |
| | confidentiality | 58 | 273 (163–311) | 94% |

Read: a protective order goes with files that end sooner and seldom by judgment (consistent with
an agreed exchange in cases that settle, and with NOC actions' statutory timetable); a
confidentiality order goes with files more often decided by judgment, and at the FCA with longer
appeals. Small cells; descriptive; subject mix within "IP" not controlled beyond the split shown.
Not published (analysis note only).

### Motions and interlocutory decisions (2026-11-25)

Prompted by the outside lawyer: interlocutory rulings appear in the docket, but the decision
text is the more consistent account of what they decided. Built from both sources
(`courtdelay.common.motions`); categories and counts only.

**Docket (S10).** Each order or judgment entry is read for what it was "with regard to"
(motion, informal request by letter, case management conference, status review, the court's
own motion, the merits, other), the registry's own tag ("Interlocutory Decision" / "Final
Decision", from 2026 "Order (Interlocutory)"), and topics from the "with regard to" phrase and
the result (extension, stay, strike, summary judgment, confidentiality, amend, security for
costs, discovery, intervention, case management, adjournment, timetable, consolidation,
representation, injunction, record). Scheduling ("time and place") orders, copies of orders
from other files, standalone "Reasons for ..." entries and directions are not counted.
Untagged orders (mostly older entries) are read as interlocutory unless they are the file's
final-decision entry (`n_interlocutory_orders_inferred`). Notices of motion and informal
requests by letter are counted as filed. Entry rows carry `order_regarding`,
`order_interlocutory`, `order_topics`, `motion_filing`; files carry `n_motions_filed`,
`n_informal_requests`, `n_orders`, `n_interlocutory_orders`, `n_orders_on_motions`, ...,
`n_orders_<topic>`. FC and FCA census files: 48,126 orders, 37,655 interlocutory (10,630 of
them inferred), 17,564 notices of motion, 4,764 informal requests. Topics are named in about a
third of order entries; most say only "granted" or "dismissed".

| Group (non-registration) | Files | Any motion filed | Any interlocutory order | Interlocutory orders p50 / p90 |
|---|---|---|---|---|
| FC IP subjects | 1,364 | 44% | 73% | 2 / 9 |
| FC judicial review | 11,606 | 22% | 44% | 0 / 4 |
| FC other actions | 1,968 | 54% | 62% | 1 / 5 |
| FC other | 7,259 | 23% | 35% | 0 / 3 |
| FCA appeals | 7,117 | 46% | 56% | 1 / 3 |

**Published decisions (S3).** `opening_is_motion` and `opening_topics` read the first
paragraphs ("[1] This is a motion by ..."). Decisions the closing page calls an order describe a
motion in 29% (FC), 67% (FCA) and 59% (Tax Court) of cases; judgments in 4%, 15% and 4%. Among
linked decisions, those that are not the file's final decision describe a motion in 62% (FC) and
56% (FCA), final ones in 12% and 17%.

**The two together** (`data/processed/links/file_procedure.parquet`, per file, local only).
Of 1,703 linked interlocutory decisions, 945 sit within 7 days of a docket order entry; that entry
is tagged interlocutory in every case. The decision names a topic in 79% of them, the docket entry
in 32%; where both do, they share a topic 85% of the time. So the docket counts rulings
completely and the text says what they were about, as advised. Published reasons are a selected
subset: across the census files, case-management orders number 6,710 in the docket against 100
published decisions on the topic, timetables 3,378 against 26 and extensions 3,216 against 80,
while injunctions (158 against 139), interventions (349 against 207), strikes (720 against 271)
and consolidations (777 against 272) are published far more often. 153 of the 1,316 files with
a published interlocutory decision show no interlocutory order in the docket; the order is
recorded under wording not yet read.

**Relation to duration** (files filed 2015 to 2022, Kaplan-Meier median days to the end of the
file): 0 interlocutory orders against 4 or more: FC IP 169 against 689; FC judicial review 134
against 624; FC other actions 138 against 1,139; FCA appeals 295 against 662. The count is not a
cause: longer files have more time to accumulate orders, so this is a description, and as a
control for complexity it should be measured at a fixed point (for example orders in the first
year) or as a rate. Not published.

*Fixed window (first year).* `file_procedure.parquet` now also carries
`n_interlocutory_orders_y1`, `n_motions_filed_y1` and `n_informal_requests_y1` (entries dated
within 365 days of filing; untagged orders interlocutory unless final). Landmark comparison:
files filed 2015 to 2023 and still open one year after filing, Kaplan-Meier median days
remaining after that year (95% bootstrap CI), by interlocutory orders in the first year:

| Group | 0 | 1 | 2-3 | 4+ |
|---|---|---|---|---|
| FC IP | 322 (229–376), n 112 | 237 (186–414), n 74 | 307 (268–368), n 174 | 284 (259–328), n 160 |
| FC judicial review | 446 (365–609), n 553 | 264 (237–336), n 507 | 274 (229–311), n 658 | 272 (233–327), n 363 |
| FC other actions | 480 (406–486), n 187 | 433 (410–467), n 365 | 623 (488–1133), n 191 | 597 (358–1449), n 65 |
| FC other | 733 (606–915), n 541 | 920 (701–1267), n 353 | 564 (487–647), n 392 | 480 (411–637), n 149 |
| FCA appeals | 160 (138–182), n 708 | 183 (164–201), n 582 | 228 (201–261), n 484 | 237 (182–325), n 136 |

Read: most of the gradient in the whole-life count was the longer-files-collect-more effect.
Measured in a fixed window, early rulings go with somewhat longer remaining time only at the FCA
and in FC actions; in judicial reviews (and the FC "other" group) a file with *no* ruling in its
first year takes longer from there, which looks like dormancy (files left idle until a status
review) rather than simplicity. Early procedural activity is therefore not a one-directional
complexity measure: as a control it needs to separate "no activity" from "light activity", and
its meaning differs by type of proceeding. Not published.

**Published (owner decision 2026-11-19):** the FC/FCA cohort tables (`s10_`) and the FC, FCA and
immigration link match rates (`link_`) are written to `site/src/data`, cells of 30 or more only.
Held back: Tax Court tables and Tax Court link rates (practitioner review), appeal-chain totals
(lower bounds), pending-file counts, and the judges table.

 The analysis that led here, as first written:


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
Kaplan-Meier median, days; computed under the end-of-file rule in force that morning, before the
marker fix, so levels differ from the cohort tables above):

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
the bias; (c) drop a file only when the court's own flag is set. The owner chose to keep all
files for now (above).

### Immigration and Tax Court links (first version 2026-11-19)

Same code, run by `courtdelay build`; per-decision rows in `data/processed/links/`.

**FC immigration decisions to Refugee Law Lab dockets (S3 to S4).** 22,973 decision x file pairs;
19,482 linked. For decisions dated 2001 to 2022, 94% to 99% link each year. 521 cited files have
no docket: 191 are 2022 files, mostly numbered above IMM-11000-22, where the Refugee Law Lab
scrape stops (last filing date 2022-11-07), so they are outside the frame rather than misses; the
other 330 could not then be told apart from the 667 files S4 dropped for sealing markers. Since
2026-11-19 S4 keeps those files (owner decision): 19,764 pairs now link and 241 cited files have
no docket, 191 of them the late-2022 files. A judgment or order entry falls on the decision date for 80% to 97% by year, and a
recorded hearing falls on the decision's hearing date for 84% to 96% (71% to 86% before the
hearing-pattern fix). Decisions after the
November 2022 scrape link to a file but have no entry to match.

- The decision header's *first* hearing date precedes the file's filing date for 12% of linked
  decisions (2,281): it is picking up another date in the header. The *last* hearing date, which
  reserve time uses, does so for under 1% (158). Reserve time is unaffected; `hearing_dates_n` and
  any multi-day measure from S3 are not reliable.
- **Coverage of published decisions is thinner for files filed 2012 to 2015.** Per file with leave
  granted (a denominator that does not use the hearing classifier), the share with a published
  decision in A2AJ is 57% to 62% for files filed 2005 to 2011, 35% to 48% for 2012 to 2015, and
  54% to 62% for 2016 to 2021. Per file with a recorded hearing the pattern is the same (75% to
  81%, then 46% to 67%, then 85% to 96%, computed before the hearing-pattern fix; the dip remains
  after it), though the 2012 figure is also pulled down by 491 files with a hearing entry and no
  leave granted, which is a classifier problem. Any series built on
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
- After the end-of-file changes above, final disposition agrees for 105 of 106.
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
