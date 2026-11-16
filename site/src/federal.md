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
const q = fcq.map(d => ({...d, date: new Date(d.period_end)}));
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

<p class="muted">Definition: Little's law, W = average pending ÷ quarterly disposal rate. Steady-state approximation of the mean, not a median. Red crosses mark quarters where the published stock does not reconcile with the published flows (gap above 1% of the stock); do not read those values. Source: Federal Court quarterly Activity Summaries, 2003–2026.</p>

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

<p class="muted">Definition: Kaplan–Meier median days from filing to the leave decision, by filing-year cohort. Files closed before a leave decision (discontinued, cancelled) are censored at their closing date; files still open in November 2022 are censored then. Medians that the curve never reaches are omitted (recent cohorts). Bias: immigration files only; events classified from docket text by pattern rules. Source: Refugee Law Lab, Luck of the Draw III (CC BY-NC 4.0).</p>

```js
display(Inputs.table(leave, {columns: ["filing_year", "n_dockets", "leave_decided_share", "grant_rate", "discontinued_share"], format: {leave_decided_share: d3.format(".0%"), grant_rate: d3.format(".0%"), discontinued_share: d3.format(".0%")}}));
```
