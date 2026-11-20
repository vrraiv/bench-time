---
title: Methods
---

# Methods (summary)

The full definitions live in `docs/methods.md` in the repository. In short:

## Durations from court files

- **Estimator.** Kaplan–Meier by filing-year cohort. Files still open are censored at the date we last read them. Medians, 75th and 90th percentiles carry bootstrap 95% intervals.
- **When a file ends.** Federal Court and Federal Court of Appeal: at the entry the Registry marks "Final Decision", otherwise at a discontinuance. Files with neither are treated as still open. Tax Court: the court's own status field decides whether a file is open.
- **What is left out.** Tribunal decisions and certificates registered with the Federal Court for enforcement are not proceedings the court decides, and are excluded (about 3,200 files).
- **Cohorts still filling.** A quantile is blanked when fewer than half of the cohort's files have been followed long enough to reach it, or when too few files remain at risk.
- **Files with confidentiality markers are kept.** Files in which a document was filed under seal or under a confidentiality order remain in the census; the markers are counted. No entry text, party name or file number is published.

## Checks

- **Against the courts' statistics.** Federal Court of Appeal, 2014–2025: our filings are 99–103% of the court's count each year and our files ended are 94–99.5%. Federal Court non-immigration, 2023–2025: filings 101–102%, files ended 97–100%. Tax Court, 2018-19 to 2022-23: filings 92–97%; that gap is unexplained.
- **Against published decisions.** Of the file numbers cited by published decisions inside the census, 12 of 8,179 were not found. A court-file hearing entry falls on the hearing date printed in the decision for 88% of Federal Court of Appeal decisions and 83% of Federal Court decisions.
- **Between sources.** A random sample of 300 immigration files from 2022 was compared with the Refugee Law Lab series: every stage date the two share agrees.

## Other measures

- **Waiting for a hearing.** Where most files end without a hearing, the share heard by a given time is a cumulative incidence with "ended without a hearing" as the competing outcome, not a waiting-time median.
- **Age of pending cases from stock–flow tables.** Little's law, W = L / λ, a steady-state approximation of the mean; shown only where the stock–flow identity reconciles within 1% of the stock.
- **Reserve time.** Last hearing day to decision date from published decisions; medians and 90th percentiles with bootstrap intervals; written dispositions excluded. A decision is final when the Registry's final-decision marker falls within a week of it.
- **Court-published figures** (StatCan medians, SCC and ONCA averages, OCJ averages) are reported as published and labelled as such.
- **Judges and vacancies.** Irregular snapshots of the judicial complement are carried forward monthly, with the snapshot date shown. Nothing on this site names or identifies an individual judge; any distribution across fewer than five judges is withheld.

## Small numbers and updates

- Cohorts under 30 files are not shown.
- The court-file census is refreshed weekly (new filings, and a rotating quarter of the open files) and the tables are rebuilt monthly.

Every chart states its definition, n, uncertainty, data vintage, source and bias.
