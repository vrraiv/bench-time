---
title: Results under review
---

# Results under review

<div class="warning" label="Not for citation">
These tables are provisional. They are shown only on the access-restricted preview, are not in the public repository, and will change after practitioner review. Please do not quote or forward the figures.
</div>

```js
const tccKm = FileAttachment("review-data/s12_tcc_km_by_cohort.csv").csv({typed: true});
const tccWait = FileAttachment("review-data/s12_tcc_hearing_wait_by_cohort.csv").csv({typed: true});
const chains = FileAttachment("review-data/link_appeal_chains_by_year.csv").csv({typed: true});
const judges = FileAttachment("review-data/link_judges_vs_complement_by_court_year.csv").csv({typed: true});
```

## Federal Court: published workload figures against court-file records

```js
const fcBench = FileAttachment("review-data/s8_fc_benchmark_vs_court_files.csv").csv({typed: true});
```

```js
const immPend = fcBench.filter(d => d.component === "immigration" && d.measure === "pending at period end")
  .map(d => ({...d, date: new Date(d.period_end)}));
display(Plot.plot({
  y: {label: "immigration proceedings pending", grid: true}, x: {label: null},
  color: {legend: true, domain: ["Court's published figure", "Our estimate from sampled files (95% interval)"]},
  marks: [
    Plot.ruleX(immPend, {x: "date", y1: "ours_lo", y2: "ours_hi", stroke: () => "Our estimate from sampled files (95% interval)", strokeOpacity: 0.5}),
    Plot.dot(immPend, {x: "date", y: "ours", stroke: () => "Our estimate from sampled files (95% interval)", tip: true}),
    Plot.lineY(immPend, {x: "date", y: "court_published", stroke: () => "Court's published figure"})
  ]
}));
```

```js
const benchPick = view(Inputs.select(
  [...new Set(fcBench.map(d => `${d.component}: ${d.measure}`))],
  {label: "Component", value: "immigration: pending at period end"}
));
```

```js
display(Inputs.table(fcBench.filter(d => `${d.component}: ${d.measure}` === benchPick), {
  columns: ["period_end", "court_published", "ours", "ours_lo", "ours_hi", "ratio", "basis"],
  header: {period_end: "Period end", court_published: "Court's figure", ours: "Ours", ours_lo: "95% low", ours_hi: "95% high", ratio: "Ours ÷ court's", basis: "Our count is from"},
  format: {period_end: d => typeof d === "string" ? d : d.toISOString().slice(0, 10), ratio: d3.format(".3f")},
  layout: "auto", width: {basis: 380}
}));
```

<p class="muted">Pending review: a check on the pending-proceedings chart of the Federal courts page, which shows the Court's own count. Flows are year to date. Filings agree closely: Refugee Law Lab dockets give 99.8–100.6% of the Court's yearly immigration filings for 2003–2021; our sample of immigration files (about 1,000 per filing year from 2023) reproduces year-to-date filings within its sampling interval in 14 of 15 quarters (June 2026 is 9% above the Court's count). The jump in the third quarter of 2026 is in the filing dates too: 13,600 immigration filings in that quarter by the Court's count, about 12,200 by ours, against about 7,000 to 8,400 in each of the two quarters before. Our census of other files gives 101–103% of non-immigration filings. The immigration pending estimate follows the same rise and sits above the Court's figure, by 5% at end-2024, 10% at end-2025 and 5% at September 2026. Two things are behind this. First, a correction on our side: from January 2026 the Registry writes final decisions in a new form that our rules did not recognise, so no 2026 decision was ending a file; with that fixed (21 November 2026) we find 96% of the Court's non-immigration dispositions for 2026 and all of its immigration dispositions, and the September 2026 gap fell from 15% to 5%. Second, a real difference in what is counted: from March 2025 to July 2026 the Registry was giving files their number days to weeks after the filing date, and the Court counts a file once it is opened while we count from the filing date. The option "files numbered by then" in the menu leaves out files that had not yet been numbered; on that basis our estimate is within sampling error of the Court's in every quarter from September 2023 to September 2025, and 5–9% above it from December 2025. That remaining step comes from the last quarter of 2025, when the Court reports 4,559 immigration dispositions and our sample supports about 3,550 (±610); we have not found the reason. It is not older files closing: a sample of 660 immigration files opened before 2022 (drawn 22 November 2026 from those still open in the Refugee Law Lab data) shows none ending in that quarter. Non-immigration: our open files run 13% above the Court's pending at September 2026, and 6% once files ended by an order made in a lead file are counted (381 files, mostly two lists of actions against the Crown dismissed in 2020 and struck in 2023; the copy placed on each file carries no final-decision marker). The published cohort tables do not yet count those endings. That accounts for the level of the difference, not its growth since 2024, which sits in judicial review files (about 110 open files have a 2025 or 2026 judgment entry with no final-decision marker; not yet read) and in extra filings in the Crown litigation group. Limits: every count here comes from the same registry as the Court's statistics, so this shows the statistics agree with the Court's file system, not that an outside count confirms them; the estimate omits immigration files opened before 2022; the top file number in the sample stands in for the number of files opened in a year; the "not yet numbered" count is a lower bound.</p>

## Tax Court: time from filing to the end of the file

```js
const tg = ["General", "Informal", "Application"];
const tk = tccKm.filter(d => tg.includes(d.procedure_group) && d.p50_days != null);
display(Plot.plot({
  y: {label: "median days (95% bootstrap CI)", grid: true}, x: {label: "file year", tickFormat: "d"},
  color: {legend: true, domain: tg},
  marks: [
    Plot.ruleX(tk, {x: "docket_year", y1: "p50_lo", y2: "p50_hi", stroke: "procedure_group", strokeOpacity: 0.5}),
    Plot.lineY(tk, {x: "docket_year", y: "p50_days", stroke: "procedure_group"}),
    Plot.dot(tk, {x: "docket_year", y: "p50_days", stroke: "procedure_group", tip: {channels: {files: "n"}}})
  ]
}));
```

<p class="muted">Pending review: how to treat files held in abeyance, which entry marks the trial, and what several entry labels mean (questions sent to the practitioner). Census of Tax Court files from 2018 from the court's public file search; end of file follows the court's own status field. Kaplan–Meier, censored at the scrape date.</p>

## Tax Court: share of files with a hearing within two years of filing

```js
const tw = tccWait.filter(d => ["General", "Informal"].includes(d.procedure_group) && d.event_by_730d != null);
display(Plot.plot({
  y: {label: "share with a first hearing entry within two years (%)", grid: true, percent: true}, x: {label: "file year", tickFormat: "d"},
  color: {legend: true},
  marks: [
    Plot.ruleX(tw, {x: "docket_year", y1: "event_by_730d_lo", y2: "event_by_730d_hi", stroke: "procedure_group", strokeOpacity: 0.5}),
    Plot.lineY(tw, {x: "docket_year", y: "event_by_730d", stroke: "procedure_group"}),
    Plot.dot(tw, {x: "docket_year", y: "event_by_730d", stroke: "procedure_group", tip: {channels: {files: "n", "within one year": "event_by_365d"}}})
  ]
}));
```

<p class="muted">Pending review: the first "Minutes of Hearing" entry is used, and it is sometimes a motion or status hearing, not the trial. Most files end without a hearing, so this is a cumulative incidence with "ended without a hearing" as the competing outcome, not a waiting-time median.</p>

## Appeal chains: from filing in the court below to the end of the appeal

```js
display(Inputs.table(chains, {
  columns: ["origin", "fca_year", "n_appeals", "n_complete_chains", "filing_to_appeal_days_p50", "fca_days_p50", "total_days_p50", "total_days_p90"],
  header: {origin: "Appealed from", fca_year: "Appeal filed", n_appeals: "Appeals", n_complete_chains: "Chains complete", filing_to_appeal_days_p50: "Filing to notice of appeal (median days)", fca_days_p50: "Appeal (median days)", total_days_p50: "Total (median days)", total_days_p90: "Total (90th pct)"},
  format: {fca_year: d3.format("d")},
  layout: "auto", width: {origin: 230}
}));
```

<p class="muted">Pending review: these totals are lower bounds, not a trend. Files in the court below start in 2018, so early appeal years can only link to quick files. About a third of appeals do not name the file appealed from and are not linked. The Supreme Court stage is shown separately below.</p>

## Supreme Court leg: appeals from the Federal Court of Appeal that were heard

```js
const sccLeg = FileAttachment("review-data/link_scc_leg_from_fca.csv").csv({typed: true});
```

```js
display(Inputs.table(sccLeg, {
  columns: ["scc_judgment_period", "leg", "n", "p25_days", "p50_days", "p75_days", "p90_days"],
  header: {scc_judgment_period: "Supreme Court judgment", leg: "Stage", n: "Cases", p25_days: "25th pct (days)", p50_days: "Median (days)", p75_days: "75th pct", p90_days: "90th pct"},
  layout: "auto", width: {leg: 300}
}));
```

<p class="muted">Pending review: this covers only appeals the Supreme Court heard and decided, 95 since 2010. Cases refused leave, which are most of them, are covered by the tables below, built from the Supreme Court's own case pages. Federal Court of Appeal files start in 2010, so the FCA stage for the earlier period rests on its quicker files. Published decisions (A2AJ) joined to FCA court files by the judgment each Supreme Court decision says it is appealed from.</p>

## Supreme Court: applications for leave to appeal, by court appealed from

```js
const sccLeave = FileAttachment("review-data/s13_scc_leave_by_origin.csv").csv({typed: true});
const sccCheck = FileAttachment("review-data/s13_scc_vs_court_statistics.csv").csv({typed: true});
const sccStages = FileAttachment("review-data/s13_scc_appeal_stages_by_origin.csv").csv({typed: true});
const sccFca = FileAttachment("review-data/link_scc_leave_fca_chain.csv").csv({typed: true});
```

```js
const sccPeriod = view(Inputs.select(["2010-2026", "2010-2014", "2015-2019", "2020-2026"], {label: "Leave application filed", value: "2010-2026"}));
```

```js
display(Inputs.table(sccLeave.filter(d => d.filing_period === sccPeriod), {
  columns: ["origin", "n", "granted_share", "p50_days", "p50_lo", "p50_hi", "p90_days", "filing_to_complete_days_p50", "filing_to_complete_days_p90", "first_ruling_to_appeal_judgment_days_p50"],
  header: {origin: "Court appealed from", n: "Files", granted_share: "Leave granted", p50_days: "Filing to leave decision (median days)", p50_lo: "95% low", p50_hi: "95% high", p90_days: "90th pct", filing_to_complete_days_p50: "Filing to application complete (median days)", filing_to_complete_days_p90: "90th pct", first_ruling_to_appeal_judgment_days_p50: "First ruling to appeal judgment below (median days)"},
  format: {granted_share: d3.format(".0%")},
  layout: "auto", width: {origin: 250}
}));
```

<p class="muted">Pending review. Every Supreme Court file opened from 2010 (about 9,100 files), read from the court's case information pages in November 2026. Unit is the file. Leave times are within a few weeks of each other across courts appealed from; applications from the Court of Appeal of Quebec take consistently longer (median 160 days against 142 to 156 elsewhere). Measured from first filing, the median has grown from 125 days (2010–2014) to 177 days (2020–2026); the court's own average, which starts when the application is complete, has stayed near four months, so the growth is in the time applications take to become complete. The last column is the time between the first ruling listed for the case and the appeal judgment below. It describes only cases that went on to seek leave, a selected group, and says nothing about those courts in general. Files carrying a sealing or publication-ban note (7% of files) are included.</p>

## Supreme Court: our figures against the court's published statistics

```js
const sccMeasure = view(Inputs.select([...new Set(sccCheck.map(d => d.measure))], {label: "Measure"}));
```

```js
display(Inputs.table(sccCheck.filter(d => d.measure === sccMeasure), {
  columns: ["year", "ours", "court_published", "our_median", "our_p90"],
  header: {year: "Year", ours: "Ours", court_published: "Court's figure", our_median: "Our median (months)", our_p90: "Our 90th pct (months)"},
  format: {year: d3.format("d")},
  layout: "auto"
}));
```

<p class="muted">Pending review. A check on the data: counts of appeals heard and of judgments match the court's within one or two a year, and average hearing-to-judgment times match to within 0.3 months. The court's leave average runs from the date the application was complete; the same interval from first filing is shown as a separate measure and has no court figure. Medians and 90th percentiles are ours; the court publishes averages only. The average from hearing to judgment sits below the median because judgments given from the bench count as zero days.</p>

## Supreme Court: stages of appeals that were heard

```js
display(Inputs.table(sccStages, {
  columns: ["origin", "leg", "n", "p25_days", "p50_days", "p75_days", "p90_days"],
  header: {origin: "Court appealed from", leg: "Stage", n: "Files", p25_days: "25th pct (days)", p50_days: "Median (days)", p75_days: "75th pct", p90_days: "90th pct"},
  layout: "auto", width: {origin: 250, leg: 330}
}));
```

<p class="muted">Pending review. Completed intervals, files opened 2010 to 2026 pooled. "Ready for hearing" is the Registry's entry that the appeal is perfected. Appeals as of right have no leave stage and appear only in the hearing rows.</p>

## Federal Court of Appeal files through the leave stage

```js
display(Inputs.table(sccFca.filter(d => d.table === "link status"), {
  columns: ["group", "n", "share"],
  header: {group: "Match to our Federal Court of Appeal files", n: "Supreme Court files", share: "Share"},
  format: {share: d3.format(".0%")},
  layout: "auto"
}));
display(Inputs.table(sccFca.filter(d => d.table === "intervals"), {
  columns: ["group", "leg", "n", "p25_days", "p50_days", "p75_days", "p90_days"],
  header: {group: "Leave result", leg: "Stage", n: "Files", p25_days: "25th pct (days)", p50_days: "Median (days)", p75_days: "75th pct", p90_days: "90th pct"},
  layout: "auto", width: {group: 260, leg: 300}
}));
```

<p class="muted">Pending review. Supreme Court files that name the Federal Court of Appeal, matched to our census of its files by file number, then by citation. For most litigants the leave decision is the end of the road: a median of 629 days after the appeal was filed in the Federal Court of Appeal, of which about 210 days are the leave stage (60 days to apply, about 150 for the decision). Where leave was granted, the Supreme Court judgment came a median of 1,094 days after the Federal Court of Appeal filing, in line with the 1,103 days found from published decisions above. Applications for leave are a selected group of appeals.</p>

## Judges deciding against the judicial complement

```js
const jc = view(Inputs.select(["FC", "TCC"], {label: "Court", value: "FC"}));
```

```js
display(Inputs.table(judges.filter(d => d.court === jc && d.year >= 2010), {
  columns: ["year", "n_decisions", "n_judges_deciding", "complement_in_office", "complement_supernumerary", "decisions_per_judge_p50", "judge_reserve_p50_p10", "judge_reserve_p50_p50", "judge_reserve_p50_p90"],
  header: {year: "Year", n_decisions: "Published decisions", n_judges_deciding: "Judges deciding", complement_in_office: "Judges in office", complement_supernumerary: "Supernumerary", decisions_per_judge_p50: "Decisions per judge (median)", judge_reserve_p50_p10: "Reserve days: 10th pct judge", judge_reserve_p50_p50: "Median judge", judge_reserve_p50_p90: "90th pct judge"},
  format: {year: d3.format("d"), complement_in_office: d3.format(".1f"), complement_supernumerary: d3.format(".1f")},
  layout: "auto"
}));
```

<p class="muted">Pending review: whether this table should be published at all. No individual is named or identifiable by design: figures are counts or distributions across judges, and a distribution over fewer than five judges is withheld. Published decisions only; Federal Court and Tax Court, where one judge decides; associate judges excluded; complement from Federal Judicial Affairs snapshots.</p>
