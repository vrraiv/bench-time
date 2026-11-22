---
title: Federal courts
---

# Federal Court and Federal Court of Appeal

```js
const fcq = FileAttachment("data/s8_fc_quarterly_littles_law.csv").csv({typed: true});
const km = FileAttachment("data/s4_fc_immigration_km_by_cohort.csv").csv({typed: true});
const leave = FileAttachment("data/s4_fc_immigration_leave_by_cohort.csv").csv({typed: true});
const vintage = FileAttachment("data/source_vintage.json").json();
```

## Federal Court stock and flow

```js
const q = fcq.map(d => ({...d, date: d.period_end instanceof Date ? d.period_end : new Date(d.period_end)}));
display(Plot.plot({
  y: {label: "pending proceedings", grid: true}, x: {label: null},
  marks: [Plot.lineY(q, {x: "date", y: "pending", tip: true})]
}));
```

<p class="muted">Definition: proceedings pending at each quarter end, all subject matters, as published by the Federal Court. This is the Court's own count, not our derivation; we copy the total row of each quarterly Activity Summary (93 quarters; September 2007 and June 2021 were not published). Immigration leave applications are 87% of the stock at 30 September 2026 (37,873 of 43,536). Checks: the subject rows sum to the total in every quarter from 2019 (to within 9 files), and the stock at end-2019 plus published filings minus dispositions comes within 2.5% of the stock published for September 2026. Yearly filings rebuilt from court-file records are within 4% of the Court's count for non-immigration files (2018–2026) and within 1% for immigration files (2003–2021). Source: Federal Court quarterly Activity Summaries, 2003–2026; fetched ${vintage.s8}.</p>

```js
const bad = q.filter(d => d.identity_ok === false);
const unsteady = q.filter(d => d.identity_ok !== false && d.steady_state_ok === false);
const usable = q.filter(d => d.identity_ok !== false && d.steady_state_ok !== false);
display(Plot.plot({
  y: {label: "implied mean time in system (days)", grid: true}, x: {label: null},
  marks: [
    Plot.dot(usable, {x: "date", y: "W_days_disposal_rate", fill: "currentColor", tip: true}),
    Plot.dot(unsteady, {x: "date", y: "W_days_disposal_rate", stroke: "gray", tip: {channels: {"filed ÷ disposed": "backlog_ratio"}}}),
    Plot.dot(bad, {x: "date", y: "W_days_disposal_rate", stroke: "red", symbol: "times", tip: true})
  ]
}));
```

<p class="muted">Definition: Little's law, W = average pending ÷ quarterly disposal rate. Steady-state approximation of the mean, not a median. Filled dots are usable quarters (${usable.length} of ${q.length}). Hollow grey dots mark quarters where filings and dispositions differ by more than a quarter (ratio outside 0.8–1.25), so the steady-state assumption fails: this includes every quarter from 2025, when filings ran 1.3 to 3 times dispositions, and those values overstate the time a file takes. Red crosses mark quarters where the published stock does not reconcile with the published flows (gap above 1% of the stock). Read neither. Source: Federal Court quarterly Activity Summaries, 2003–2026; fetched ${vintage.s8}.</p>

## Immigration judicial review: time to a leave decision, by filing year

```js
const est = km.filter(d => d.estimand === "filing -> leave decision" && d.p50_days != null);
display(Plot.plot({
  y: {label: "median days (95% bootstrap CI)", grid: true}, x: {label: "filing year", tickFormat: "d"},
  marks: [
    Plot.ruleX(est, {x: "filing_year", y1: "p50_lo", y2: "p50_hi"}),
    Plot.dot(est, {x: "filing_year", y: "p50_days", tip: {channels: {n: "n", censored: "censored_share"}}})
  ]
}));
```

<p class="muted">Definition: Kaplan–Meier median days from filing to the leave decision, by filing-year cohort. Files closed before a leave decision (discontinued, cancelled) are censored at their closing date; files still open in November 2022 are censored then. Medians that the curve never reaches are omitted (recent cohorts). Bias: immigration files only; events classified from docket text by pattern rules. Source: Refugee Law Lab, Luck of the Draw III (CC BY-NC 4.0), scraped November 2022; fetched 2026-11-15.</p>

```js
display(Inputs.table(leave, {columns: ["filing_year", "n_dockets", "leave_decided_share", "grant_rate", "discontinued_share"], format: {leave_decided_share: d3.format(".0%"), grant_rate: d3.format(".0%"), discontinued_share: d3.format(".0%")}}));
```

## Court files: time from filing to the end of the file

```js
const cohorts = FileAttachment("data/s10_fc_fca_km_by_cohort.csv").csv({typed: true});
const outcomes = FileAttachment("data/s10_fc_fca_file_outcomes_by_cohort.csv").csv({typed: true});
```

```js
const groups = ["FCA: all", "FC: all", "FC: judicial review", "FC: actions"];
const shown = cohorts.filter(d => groups.includes(d.proceeding_group) && d.p50_days != null);
display(Plot.plot({
  marginRight: 20,
  y: {label: "median days from filing to end of file (95% bootstrap CI)", grid: true},
  x: {label: "filing year", tickFormat: "d"},
  color: {legend: true, domain: groups},
  marks: [
    Plot.ruleX(shown, {x: "docket_year", y1: "p50_lo", y2: "p50_hi", stroke: "proceeding_group", strokeOpacity: 0.5}),
    Plot.lineY(shown, {x: "docket_year", y: "p50_days", stroke: "proceeding_group"}),
    Plot.dot(shown, {x: "docket_year", y: "p50_days", stroke: "proceeding_group", tip: {channels: {files: "n", "still open": "censored_share"}}})
  ]
}));
```

<p class="muted">Definition: Kaplan–Meier median days from the filing date to the end of the court file, by filing year. A file ends at the entry the Registry marks "Final Decision", or at a discontinuance. Since 22 November 2026 a file also ends in three cases where its own entries carry no such mark: one order made in a lead file dismissed or struck a list of files and a copy was placed on it (377 Federal Court files, 72 appeal files); a copy of a notice of discontinuance filed in another file was placed on it and nothing but correspondence follows (78 and 23); or a 2026 judgment carries no qualifier and nothing but correspondence follows (30 files). This lowered the upper quantiles for 2018–2021. Files with none of these are treated as still open. Census of every Federal Court of Appeal file from 2010 and every Federal Court non-immigration file from 2018, read from the courts' public file search in November 2026. Population: the tables follow what each court counts as a proceeding, as far as we can tell. Left out of the Federal Court tables: tribunal decisions and certificates registered for enforcement (about 3,200 files), and the Crown's tax-collection matters (about 370 files: Income Tax Act and excise applications, jeopardy collection orders, search warrants). The Court publishes no definition; the second exclusion is inferred from its yearly filing counts, which match ours to within 12 files once those matters are left out. Left out of the appeal tables: the appeal court's "preliminary applications", which are motions brought before an appeal exists and have no appeal file. Recent years are omitted until at least half the cohort has been followed long enough. Check: on these definitions Federal Court filing counts are within 1% of the Court's published counts (2019–2026) and disposition counts are 95–101% of its for 2022–2025; Federal Court of Appeal filing counts are within 2.5% and disposition counts 94–100% of that court's (2019–2026). About 2% of appeal endings a year are still missed, so the appeal upper quantiles are slightly overstated. From January 2026 the Registry writes final decisions in a new form; these tables recognise it as of 21 November 2026 (before that, no 2026 decision was ending a file). These are our derivations, not the courts' statistics.</p>

```js
const pick = view(Inputs.select([...new Set(outcomes.map(d => d.proceeding_group))].sort(), {label: "Proceeding group", value: "FC: all"}));
```

```js
display(Inputs.table(
  cohorts.filter(d => d.proceeding_group === pick).map(d => ({...d, ...outcomes.find(o => o.proceeding_group === pick && o.docket_year === d.docket_year)})),
  {
    columns: ["docket_year", "n", "p50_days", "p75_days", "p90_days", "ended_share", "discontinued_share"],
    header: {docket_year: "Filing year", n: "Files", p50_days: "Median days", p75_days: "75th pct", p90_days: "90th pct", ended_share: "Ended", discontinued_share: "Discontinued"},
    format: {docket_year: d3.format("d"), ended_share: d3.format(".0%"), discontinued_share: d3.format(".0%")}
  }
));
```

<p class="muted">Blank cells are not yet estimable: too many files in that cohort are still open.</p>
