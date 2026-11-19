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

<p class="muted">Pending review: these totals are lower bounds, not a trend. Files in the court below start in 2018, so early appeal years can only link to quick files. About a third of appeals do not name the file appealed from and are not linked. The Supreme Court leg is not built.</p>

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
