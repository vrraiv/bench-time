---
title: Appellate - SCC and ONCA
---

# Supreme Court of Canada and Court of Appeal for Ontario

```js
const s5 = FileAttachment("data/s5_scc_time_lapses.csv").csv({typed: true});
const s6 = FileAttachment("data/s6_onca_annual_report_tables.csv").csv({typed: true});
const rt = FileAttachment("data/s3_reserve_time_by_court_year.csv").csv({typed: true});
```

## SCC average time lapses (court-published)

```js
display(Plot.plot({
  y: {label: "average months", grid: true}, x: {label: "year", tickFormat: "d"}, color: {legend: true},
  marks: [Plot.line(s5, {x: "year", y: "months", stroke: "stage"}), Plot.dot(s5, {x: "year", y: "months", stroke: "stage", tip: true})]
}));
```

<p class="muted">Averages by file number as published by the Court, 2002–2025 (2002–2009 from the Court's former statistics page via the Internet Archive). No distributions are published.</p>

## ONCA appeal phases (court-published averages, by filing year)

```js
const phases = s6.filter(d => d.table.startsWith("timeline_") && d.table !== "timeline_filing_to_decision" && d.column !== "average_total");
display(Plot.plot({
  fx: {label: null}, y: {label: "average days", grid: true}, x: {label: "filing year", tickFormat: "d"}, color: {legend: true},
  facet: {data: phases, x: "table"},
  marks: [Plot.line(phases, {x: "year", y: "value", stroke: "column", fx: "table"})]
}));
```

<p class="muted">Phases: filing → ready for scheduling (largely party-driven), ready → hearing (waiting for a hearing date: closest to institutional delay), hearing → decision (reserve). Appeals heard and decided on their merits only. Source: ONCA Annual Report 2023–2024, statistical appendix.</p>

## Reserve time from published decisions (hearing → decision)

```js
const courts = ["SCC", "ONCA", "FCA", "FC", "TCC"];
display(Plot.plot({
  fy: {label: null, domain: courts}, y: {label: "median days (95% CI)", grid: true}, x: {label: "decision year", tickFormat: "d"},
  height: 600,
  marks: [
    Plot.ruleX(rt.filter(d => d.year >= 2005), {x: "year", y1: "p50_lo", y2: "p50_hi", fy: "court"}),
    Plot.dot(rt.filter(d => d.year >= 2005), {x: "year", y: "p50_days", fy: "court", tip: {channels: {n: "n", p90: "p90_days"}}})
  ]
}));
```

<p class="muted">Definition: median days from the last hearing day to the decision, per decision year, with 95% bootstrap CIs; p90 and n in tooltips. Bias: published written decisions only; oral rulings and unreported decisions are absent; matters decided in writing are excluded; hearing dates are parsed from unofficial texts (coverage by court-year in the CSV). Source: A2AJ Canadian Case Law (derived fields only).</p>
