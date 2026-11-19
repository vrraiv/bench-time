---
title: Federal courts
---

# Federal Court and Federal Court of Appeal

```js
const fcq = FileAttachment("data/s8_fc_quarterly_littles_law.csv").csv({typed: true});
const km = FileAttachment("data/s4_fc_immigration_km_by_cohort.csv").csv({typed: true});
const leave = FileAttachment("data/s4_fc_immigration_leave_by_cohort.csv").csv({typed: true});
```

## Federal Court stock and flow

```js
const q = fcq.map(d => ({...d, date: d.period_end instanceof Date ? d.period_end : new Date(d.period_end)}));
display(Plot.plot({
  y: {label: "pending proceedings", grid: true}, x: {label: null},
  marks: [Plot.lineY(q, {x: "date", y: "pending", tip: true})]
}));
display(Plot.plot({
  y: {label: "implied mean time in system (days)", grid: true}, x: {label: null},
  marks: [
    Plot.dot(q.filter(d => d.identity_ok !== false), {x: "date", y: "W_days_disposal_rate", tip: true}),
    Plot.dot(q.filter(d => d.identity_ok === false), {x: "date", y: "W_days_disposal_rate", stroke: "red", symbol: "times", tip: true})
  ]
}));
```

<p class="muted">Definition: Little's law, W = average pending ÷ quarterly disposal rate. Steady-state approximation of the mean, not a median. Red crosses mark quarters where the published stock does not reconcile with the published flows (gap above 1% of the stock); do not read those values. Source: Federal Court quarterly Activity Summaries, 2003–2026; fetched 2026-11-15.</p>

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

<p class="muted">Definition: Kaplan–Meier median days from the filing date to the end of the court file, by filing year. A file ends at the entry the Registry marks "Final Decision", or at a discontinuance; files with neither are treated as still open. Census of every Federal Court of Appeal file from 2010 and every Federal Court non-immigration file from 2018, read from the courts' public file search in November 2026. Tribunal decisions and certificates registered for enforcement are excluded. Recent years are omitted until at least half the cohort has been followed long enough. Check: our yearly filing counts are within 2.5% of the courts' published counts and our disposition counts are 94–100% of theirs, so a few percent of endings are missed and upper quantiles are slightly overstated. These are our derivations, not the courts' statistics.</p>

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
