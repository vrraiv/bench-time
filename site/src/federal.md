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

<div class="chart-note">
<p><strong>Definition:</strong> proceedings pending at each quarter end, all subject matters, as published by the Federal Court. <strong>This is the Court's own count, not our derivation;</strong> we copy the total row of each quarterly Activity Summary (93 quarters; September 2007 and June 2021 were not published). Immigration leave applications are 87% of the stock at 30 September 2026 (37,873 of 43,536).</p>
<p><strong>Checks:</strong> the subject rows sum to the total in every quarter from 2019 (to within 9 files), and the stock at end-2019 plus published filings minus dispositions comes within 2.5% of the stock published for September 2026. Yearly filings rebuilt from court-file records are within 4% of the Court's count for non-immigration files (2018–2026) and within 1% for immigration files (2003–2021).</p>
<p><strong>Source:</strong> Federal Court quarterly Activity Summaries, 2003–2026; fetched ${vintage.s8}.</p>
</div>

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

<div class="chart-note">
<p><strong>Definition:</strong> Little's law, W = average pending ÷ quarterly disposal rate. <strong>Steady-state approximation of the mean, not a median.</strong></p>
<ul>
<li><strong>Filled dots</strong> are usable quarters (${usable.length} of ${q.length}).</li>
<li><strong>Hollow grey dots</strong> mark quarters where filings and dispositions differ by more than a quarter (ratio outside 0.8–1.25), so the steady-state assumption fails: this includes every quarter from 2025, when filings ran 1.3 to 3 times dispositions, and those values overstate the time a file takes.</li>
<li><strong>Red crosses</strong> mark quarters where the published stock does not reconcile with the published flows (gap above 1% of the stock).</li>
</ul>
<p><strong>Read neither grey dots nor red crosses.</strong></p>
<p><strong>Source:</strong> Federal Court quarterly Activity Summaries, 2003–2026; fetched ${vintage.s8}.</p>
</div>

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

<div class="chart-note">
<p><strong>Definition:</strong> Kaplan–Meier median days from filing to the leave decision, by filing-year cohort. Files closed before a leave decision (discontinued, cancelled) are censored at their closing date; files still open in November 2022 are censored then. Medians that the curve never reaches are omitted (recent cohorts).</p>
<p><strong>Bias:</strong> immigration files only; events classified from docket text by pattern rules.</p>
<p><strong>Source:</strong> Refugee Law Lab, Luck of the Draw III (CC BY-NC 4.0), scraped November 2022; fetched 2026-11-15.</p>
</div>

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

<div class="chart-note">
<p><strong>Definition:</strong> Kaplan–Meier median days from the filing date to the end of the court file, by filing year. <strong>These are our derivations, not the courts' statistics.</strong> Recent years are omitted until at least half the cohort has been followed long enough.</p>

<h4>When a file ends</h4>
<p>At the entry the Registry marks "Final Decision", or at a discontinuance. Since 22 November 2026 a file also ends in three cases where its own entries carry no such mark:</p>
<ul>
<li>one order made in a lead file dismissed or struck a list of files and a copy was placed on it (377 Federal Court files, 72 appeal files);</li>
<li>a copy of a notice of discontinuance filed in another file was placed on it and nothing but correspondence follows (78 and 23);</li>
<li>a 2026 judgment carries no qualifier and nothing but correspondence follows (30 files).</li>
</ul>
<p>This lowered the upper quantiles for 2018–2021. Files with none of these are treated as still open. From January 2026 the Registry writes final decisions in a new form; these tables recognise it as of 21 November 2026 (before that, no 2026 decision was ending a file).</p>

<h4>Population</h4>
<p>Census of every Federal Court of Appeal file from 2010 and every Federal Court non-immigration file from 2018, read from the courts' public file search in November 2026. The tables follow what each court counts as a proceeding, as far as we can tell.</p>
<ul>
<li><strong>Left out of the Federal Court tables:</strong> tribunal decisions and certificates registered for enforcement (about 3,200 files), and the Crown's tax-collection matters (about 370 files: Income Tax Act and excise applications, jeopardy collection orders, search warrants). The Court publishes no definition; the second exclusion is inferred from its yearly filing counts, which match ours to within 12 files once those matters are left out.</li>
<li><strong>Left out of the appeal tables:</strong> the appeal court's "preliminary applications", which are motions brought before an appeal exists and have no appeal file.</li>
</ul>

<h4>Check against the courts' counts</h4>
<ul>
<li><strong>Federal Court:</strong> filing counts within 1% of the Court's published counts (2019–2026); disposition counts 95–101% of its for 2022–2025.</li>
<li><strong>Federal Court of Appeal:</strong> filing counts within 2.5%; disposition counts 94–100% of that court's (2019–2026).</li>
<li>About 2% of appeal endings a year are still missed, so <strong>the appeal upper quantiles are slightly overstated.</strong></li>
</ul>
</div>

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

<p class="chart-note">Blank cells are not yet estimable: too many files in that cohort are still open.</p>
