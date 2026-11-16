---
title: Criminal (Ontario)
---

# Criminal cases in Ontario

```js
const s1 = FileAttachment("data/s1_median_days_by_offence.csv").csv({typed: true});
const dr = FileAttachment("data/s7_ocj_provincial_disposition_monthly.csv").csv({typed: true});
const ch = FileAttachment("data/s7_ocj_courthouse_panel.csv").csv({typed: true});
```

## Median days to decision (StatCan)

```js
const geos = ["Ontario", "Canada"];
const series = s1.filter(d => d.offences === "Total Criminal Code" && geos.includes(d.geo) && d.median_days != null)
  .map(d => ({...d, year: +String(d.ref_date).slice(0, 4)}));
display(Plot.plot({
  y: {label: "median days", grid: true}, x: {label: "fiscal year (start)", tickFormat: "d"},
  color: {legend: true},
  marks: [
    Plot.ruleX([2016], {stroke: "#999", strokeDasharray: "4 3"}),
    Plot.text([2016], {x: d => d, y: 0, text: () => "Jordan (2016)", dy: -6, fill: "#777"}),
    Plot.line(series, {x: "year", y: "median_days", stroke: "geo"}),
    Plot.dot(series, {x: "year", y: "median_days", stroke: "geo", tip: true})
  ]
}));
```

<p class="muted">Definition: median days from first appearance to final decision, adult criminal court cases completed in the year, all Criminal Code offences. n (cases per year) is in the CSV. No sampling interval: a census of completed cases. Bias: completed cases only; delay cannot be attributed to Crown, defence or court. Source: Statistics Canada table 35-10-0029-01, release 2026-10-01; fetched 2026-11-16.</p>

## Ontario Court of Justice: share of cases disposed after 18 months

```js
// typed CSV parsing turns "2024-04" into a Date; accept either form
const asDate = v => v instanceof Date ? v : new Date(String(v).length === 7 ? v + "-01" : v);
const ocj = dr.filter(d => d.case_type === "all" && d.pct_over_18m != null).map(d => ({...d, date: asDate(d.month)}));
display(Plot.plot({
  y: {label: "% disposed after 18 months", percent: true, grid: true}, x: {label: null},
  marks: [Plot.lineY(ocj, {x: "date", y: "pct_over_18m", tip: true})]
}));
```

<p class="muted">Definition: monthly share of OCJ criminal cases disposed more than 18 months after first appearance (cases without bench warrants). Coverage 2015 onward in this band layout; 2012–2014 files use 8- and 12-month bands. Bias: Ministry of the Attorney General data, which the Court disclaims; completed cases only. Source: OCJ Disposition Rate Statistics; fetched 2026-11-15. 2023 provincial figures exclude Toronto (data-integrity issues after the Toronto courthouse amalgamation).</p>

## Courthouse panel

```js
const ts = v => +(v instanceof Date ? v : new Date(v));
const latestTs = d3.max(ch, d => ts(d.period_end));
const latest = new Date(latestTs).toISOString().slice(0, 10);
const rows = ch.filter(d => ts(d.period_end) === latestTs && d.disposed >= 500).sort((a, b) => d3.descending(a.avg_days_weighted, b.avg_days_weighted));
display(Plot.plot({
  marginLeft: 160, height: rows.length * 16 + 40,
  x: {label: "average days to disposition", grid: true},
  marks: [Plot.barX(rows, {y: "unit_key", x: "avg_days_weighted", sort: {y: "-x"}, tip: true})]
}));
```

<p class="muted">Definition: disposal-weighted average days to disposition across offence groups, period ending ${latest}, courthouses with at least 500 dispositions. Bias: averages, not medians; calendar years to 2019 and fiscal years from 2020 (definition break); courthouse names vary across years and are normalised; Toronto courthouses were amalgamated in 2023 and Toronto is absent from 2023 data. Source: OCJ Offence Based Statistics; fetched 2026-11-15.</p>
