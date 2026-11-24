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

<div class="chart-note">

<p><span class="status">Pending review</span> A check on the pending-proceedings chart of the Federal courts page, which shows the Court's own count. Flows are year to date.</p>

<h4>Filings agree closely</h4>
<ul>
<li><strong>Immigration, 2003–2021:</strong> Refugee Law Lab dockets give 99.8–100.6% of the Court's yearly immigration filings.</li>
<li><strong>Immigration, from 2023:</strong> our sample (about 1,000 files per filing year) reproduces year-to-date filings within its sampling interval in 14 of 15 quarters (June 2026 is 9% above the Court's count).</li>
<li><strong>The Q3 2026 jump is real</strong> and in the filing dates too: 13,600 immigration filings in that quarter by the Court's count, about 12,200 by ours, against about 7,000 to 8,400 in each of the two quarters before.</li>
<li><strong>Non-immigration:</strong> our census of other files gives 101–103% of the Court's filings.</li>
</ul>

<h4>Immigration pending: above the Court's figure</h4>
<p>Our estimate follows the same rise and sits above the Court's figure, by <strong>5% at end-2024, 10% at end-2025 and 5% at September 2026</strong>. Two things are behind this:</p>
<ul>
<li><strong>A correction on our side.</strong> From January 2026 the Registry writes final decisions in a new form that our rules did not recognise, so no 2026 decision was ending a file. With that fixed (21 November 2026) we find 96% of the Court's non-immigration dispositions for 2026 and all of its immigration dispositions, and the September 2026 gap fell from 15% to 5%.</li>
<li><strong>A real difference in what is counted.</strong> From March 2025 to July 2026 the Registry was giving files their number days to weeks after the filing date; the Court counts a file once it is opened, while we count from the filing date. The menu option "files numbered by then" leaves out files not yet numbered. On that basis our estimate is within sampling error of the Court's in every quarter from September 2023 to September 2025, and 5–9% above it from December 2025.</li>
</ul>
<p><strong>Unexplained:</strong> that remaining step comes from the last quarter of 2025, when the Court reports 4,559 immigration dispositions and our sample supports about 3,550 (±610). It is not older files closing: a sample of 660 immigration files opened before 2022 (drawn 22 November 2026 from those still open in the Refugee Law Lab data) shows none ending in that quarter.</p>

<h4>Non-immigration pending</h4>
<ul>
<li><strong>13% above</strong> the Court's pending at September 2026, and <strong>6%</strong> once files ended by an order made in a lead file are counted (381 files, mostly two lists of actions against the Crown dismissed in 2020 and struck in 2023; the copy placed on each file carries no final-decision marker).</li>
<li>Those endings are counted in the published cohort tables from 22 November 2026, with copies of a notice of discontinuance placed on a file (78 files) and 2026 judgments that carry no qualifier (30 files).</li>
<li><strong>Tax-collection files left out.</strong> These rows leave out the Crown's tax-collection files, which the Court appears not to count: our extra filings matched them year for year (303 against 302 over 2019–2026), and without them filings agree to within 11 a year.</li>
<li><strong>"Counting group endings"</strong> (menu option) adds companions of a group whose lead file has ended (209 files, an inference no table uses). On that basis our open files are <strong>0.91</strong> of the Court's pending at end-2022 and <strong>0.99</strong> at September 2026 (0.92 and 1.02 without the group endings).</li>
<li><strong>Unexplained:</strong> the rise that remains comes from older files leaving the Court's stock and from judicial review, where we still find 1–3% fewer dispositions than the Court in 2024–2026.</li>
</ul>

<h4>Federal Court of Appeal (choose it in the menu)</h4>
<ul>
<li>The court's total includes <strong>"preliminary applications"</strong>, motions brought before an appeal exists, which have no appeal file and are not in our census.</li>
<li>With those set aside our filings are within 2.5% of the court's and our endings 94–100% of its in every year from 2019.</li>
<li>Our open files are still <strong>about 110 above its pending (18–22%)</strong>, a gap already 59 files in 2019 that grows by about 8 a year: appeal files that go dormant with no ending entry.</li>
</ul>

<h4>Definitions and limits</h4>
<ul>
<li>The courts administration service's annual reports define a disposition as a proceeding "concluded by way of judgment, discontinuance or other documents" and list consolidated and stayed files as pending; neither court publishes which file types its counts leave out.</li>
<li><strong>Same registry:</strong> every count here comes from the same registry as the Court's statistics, so this shows the statistics agree with the Court's file system, not that an outside count confirms them.</li>
<li>The estimate omits immigration files opened before 2022; the top file number in the sample stands in for the number of files opened in a year; the "not yet numbered" count is a lower bound.</li>
</ul>

</div>

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

<div class="chart-note"><p><span class="status">Pending review</span> How to treat files held in abeyance and when the clock should start for files that began as extension applications (follow-up questions with the practitioner). Confirmed by the practitioner: a file is held in abeyance only at a party's request, and a file "bound by a lead case" is not paused. Census of Tax Court files from 2018 from the court's public file search; end of file follows the court's own status field. Kaplan–Meier, censored at the scrape date.</p></div>

## Tax Court: share of files with a trial sitting within two years of filing

```js
const tw = tccWait.filter(d => ["General", "Informal"].includes(d.procedure_group) && d.event_by_730d != null);
display(Plot.plot({
  y: {label: "share with a first trial sitting within two years (%)", grid: true, percent: true}, x: {label: "file year", tickFormat: "d"},
  color: {legend: true},
  marks: [
    Plot.ruleX(tw, {x: "docket_year", y1: "event_by_730d_lo", y2: "event_by_730d_hi", stroke: "procedure_group", strokeOpacity: 0.5}),
    Plot.lineY(tw, {x: "docket_year", y: "event_by_730d", stroke: "procedure_group"}),
    Plot.dot(tw, {x: "docket_year", y: "event_by_730d", stroke: "procedure_group", tip: {channels: {files: "n", "within one year": "event_by_365d"}}})
  ]
}));
```

<div class="chart-note"><p><span class="status">Changed 24 November 2026</span> <strong>Only trial sittings now count.</strong> The practitioner told us "Minutes of Hearing" is kept for motions, status hearings and conference calls as well as the hearing of the appeal, and the files bear that out: more than half of the 16,061 sitting days follow a case management or trial management conference, a motion, or a status or show-cause hearing.</p>
<ul>
<li><strong>The rule (ours, now with the practitioner for review):</strong> a sitting is the trial when its minutes carry an exhibit list or a decision was reserved that day, or when the appeal had been scheduled for hearing and no conference, motion or status hearing was waiting for its minutes. 45% of sittings are trials, 50% something else, 5% cannot be told and are not counted.</li>
<li><strong>Effect:</strong> General procedure, files of 2018: 1.6% reach a trial sitting within two years, where the earlier chart showed 12%. Informal procedure: 30%, where it showed 41%.</li>
<li><strong>It misses some trials, so the shares are lower bounds.</strong> Among files with a sitting and a judgment that was not on consent, we find no trial sitting in 16% of General procedure files and 2% of Informal ones (some of those judgments decide motions, not the appeal). If every one were a missed trial, General procedure trial counts would be about 5% higher: not enough to change the picture.</li>
<li><strong>Check:</strong> a judgment follows within 45 days after 39% of the sittings we call trials and 4% of the others.</li>
<li><strong>Against the court's own count:</strong> the Tax Court publishes "files prepared for hearing and heard in court" by fiscal year. Our files with a trial sitting: 741 against the court's 713 in 2022–23, 279 against 166 in 2021–22, 229 against 273 in 2020–21, and 1,343 against 883 in 2019–20. Counting every sitting gave 1,251 to 1,820 in those years. The court's definition is not published and our census leaves out files opened before 2018, so this is a rough check: the new measure is the right order of magnitude; the old one was not.</li>
<li>Most files end without a trial, so this is a cumulative incidence with "ended without one" as the competing outcome, not a waiting-time median.</li>
</ul></div>

```js
const tccMix = FileAttachment("review-data/s12_tcc_file_outcomes_by_cohort.csv").csv({typed: true});
```

```js
display(Inputs.table(tccMix.filter(d => ["General", "Informal"].includes(d.procedure_group)), {
  columns: ["procedure_group", "docket_year", "n_files", "any_sitting_share", "hearing_held_share", "unclassified_sitting_share", "closed_share"],
  header: {procedure_group: "Procedure", docket_year: "File year", n_files: "Files", any_sitting_share: "Any sitting", hearing_held_share: "Trial sitting", unclassified_sitting_share: "Sitting we cannot classify", closed_share: "File ended"},
  format: {docket_year: d3.format("d"), any_sitting_share: d3.format(".1%"), hearing_held_share: d3.format(".1%"), unclassified_sitting_share: d3.format(".1%"), closed_share: d3.format(".0%")},
  layout: "auto"
}));
```

<div class="chart-note"><p>Share of each year's files with any sitting on record, and with a sitting read as the trial, at any time up to the date we read the file. Recent years are incomplete.</p>
<p><strong>Coverage note.</strong> From about 19 to 23 November 2026 the Tax Court's public file list returned only about 4,700 of its 29,700 files. It was complete again on 24 November, apparently after a site update. Our census was not affected: it keeps every file the court has ever listed.</p></div>

## Appeal chains: from filing in the court below to the end of the appeal

```js
display(Inputs.table(chains, {
  columns: ["origin", "fca_year", "n_appeals", "n_complete_chains", "filing_to_appeal_days_p50", "fca_days_p50", "total_days_p50", "total_days_p90"],
  header: {origin: "Appealed from", fca_year: "Appeal filed", n_appeals: "Appeals", n_complete_chains: "Chains complete", filing_to_appeal_days_p50: "Filing to notice of appeal (median days)", fca_days_p50: "Appeal (median days)", total_days_p50: "Total (median days)", total_days_p90: "Total (90th pct)"},
  format: {fca_year: d3.format("d")},
  layout: "auto", width: {origin: 230}
}));
```

<div class="chart-note"><p><span class="status">Pending review</span> <strong>These totals are lower bounds, not a trend.</strong> Files in the court below start in 2018, so early appeal years can only link to quick files. About a third of appeals do not name the file appealed from and are not linked. The Supreme Court stage is shown separately below.</p></div>

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

<div class="chart-note"><p><span class="status">Pending review</span> <strong>This covers only appeals the Supreme Court heard and decided, 95 since 2010.</strong> Cases refused leave, which are most of them, are covered by the tables below, built from the Supreme Court's own case pages. Federal Court of Appeal files start in 2010, so the FCA stage for the earlier period rests on its quicker files. Published decisions (A2AJ) joined to FCA court files by the judgment each Supreme Court decision says it is appealed from.</p></div>

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
  columns: ["origin", "n", "granted_share", "p50_days", "p50_lo", "p50_hi", "p90_days", "filing_to_complete_days_p50", "filing_to_complete_days_p90", "complete_to_decision_days_p50", "complete_to_decision_days_p90", "first_ruling_to_appeal_judgment_days_p50"],
  header: {origin: "Court appealed from", n: "Files", granted_share: "Leave granted", p50_days: "Clock 1: filing to leave decision (median days)", p50_lo: "95% low", p50_hi: "95% high", p90_days: "90th pct", filing_to_complete_days_p50: "Filing to application complete (median days)", filing_to_complete_days_p90: "90th pct", complete_to_decision_days_p50: "Clock 2: application complete to leave decision (median days)", complete_to_decision_days_p90: "90th pct", first_ruling_to_appeal_judgment_days_p50: "First ruling to appeal judgment below (median days)"},
  format: {granted_share: d3.format(".0%")},
  layout: "auto", width: {origin: 250}
}));
```

<div class="chart-note"><p><span class="status">Pending review</span> Every Supreme Court file opened from 2010 (about 9,100 files), read from the court's case information pages in November 2026. Unit is the file.</p>
<ul>
<li><strong>Similar across courts:</strong> leave times are within a few weeks of each other across courts appealed from; applications from the Court of Appeal of Quebec take consistently longer (median 160 days against 142 to 156 elsewhere).</li>
<li><strong>Two clocks, on the practitioner's advice:</strong> from first filing the median has grown from 125 days (2010–2014) to 177 days (2020–2026). From the date the Registry marked the application complete it moved from 112 to 126 days. <strong>Most of the growth is in the time applications take to become complete</strong> (median 0 days in 2010–2014, 20 days in 2020–2026), and she tells us that wait can be the applicant's, the Registry's, or both. Clock 1 is a Kaplan–Meier median; clock 2 covers decided files only.</li>
<li><strong>Last column:</strong> the time between the first ruling listed for the case and the appeal judgment below. It describes only cases that went on to seek leave, a selected group, and says nothing about those courts in general.</li>
<li>Files carrying a sealing or publication-ban note (7% of files) are included.</li>
</ul></div>

```js
const sccOutcomes = FileAttachment("review-data/s13_scc_leave_outcomes.csv").csv({typed: true});
```

```js
display(Inputs.table(sccOutcomes.filter(d => d.filing_period === sccPeriod), {
  columns: ["outcome", "n", "share_of_files"],
  header: {outcome: "How the leave stage ended", n: "Files", share_of_files: "Share of files"},
  format: {share_of_files: d3.format(".1%")},
  layout: "auto"
}));
```

<div class="chart-note"><p><span class="status">Changed 24 November 2026</span> Each way the leave stage can end is now shown. The practitioner's view is that a remand to the court below and an order for an oral hearing are quite different from leave being granted; they are no longer folded into "not granted". Unit is the file, at its latest leave judgment; 43 files with leave judgments on more than one date are a follow-up question.</p></div>

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

<div class="chart-note"><p><span class="status">Pending review</span> A check on the data: counts of appeals heard and of judgments match the court's within one or two a year, and average hearing-to-judgment times match to within 0.3 months. The court's leave average runs from the date the application was complete; the same interval from first filing is shown as a separate measure and has no court figure. Medians and 90th percentiles are ours; the court publishes averages only. The average from hearing to judgment sits below the median because judgments given from the bench count as zero days; the same average for reserved judgments only is a separate measure with no court figure.</p></div>

## Supreme Court: stages of appeals that were heard

```js
display(Inputs.table(sccStages, {
  columns: ["origin", "leg", "n", "p25_days", "p50_days", "p75_days", "p90_days"],
  header: {origin: "Court appealed from", leg: "Stage", n: "Files", p25_days: "25th pct (days)", p50_days: "Median (days)", p75_days: "75th pct", p90_days: "90th pct"},
  layout: "auto", width: {origin: 250, leg: 330}
}));
```

<div class="chart-note"><p><span class="status">Pending review</span> Completed intervals, files opened 2010 to 2026 pooled. "Ready for hearing" is the Registry's entry that the appeal is perfected; the practitioner agrees the wait from that entry to the hearing is the court's time, not the parties'. Appeals as of right have no leave stage and appear only in the hearing rows.</p></div>

## Supreme Court: judgments from the bench and reserved judgments

```js
const sccBench = FileAttachment("review-data/s13_scc_bench_judgments.csv").csv({typed: true});
```

```js
display(Inputs.table(sccBench, {
  columns: ["judgment_period", "n_judgments", "n_from_bench", "bench_share", "n_reasons_later", "n_reserved", "reserved_p50_days", "reserved_p75_days", "reserved_p90_days", "all_p50_days"],
  header: {judgment_period: "Judgment given", n_judgments: "Judgments", n_from_bench: "From the bench", bench_share: "Share from the bench", n_reasons_later: "Bench judgments with written reasons later", n_reserved: "Reserved", reserved_p50_days: "Reserved: hearing to judgment (median days)", reserved_p75_days: "75th pct", reserved_p90_days: "90th pct", all_p50_days: "All judgments (median days)"},
  format: {bench_share: d3.format(".0%")},
  layout: "auto"
}));
```

<div class="chart-note"><p><span class="status">New 24 November 2026</span> On the practitioner's advice, judgments given at the hearing are reported apart from reserved ones.</p>
<ul>
<li><strong>A quarter of judgments are from the bench</strong> (241 of 941), and the share is rising: 17% in 2010–2014, 31% in 2020–2026.</li>
<li><strong>Reserved judgments take longer than the pooled figure suggests:</strong> median 205 days from hearing to judgment, against 178 days when bench judgments are counted as zero. The reserved median has moved from 186 days (2010–2014) to 220 days (2020–2026).</li>
<li><strong>Reasons after a bench judgment:</strong> the case pages record written reasons later for 36 of the 241 bench judgments, a median of about 122 days after the hearing. Where no such entry exists we cannot tell whether reasons were given orally or not at all.</li>
<li>From the bench = judgment dated the day of the hearing. 2010–2014 misses judgments in files opened before 2010.</li>
</ul></div>

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

<div class="chart-note"><p><span class="status">Pending review</span> Supreme Court files that name the Federal Court of Appeal, matched to our census of its files by file number, then by citation.</p><p><strong>For most litigants the leave decision is the end of the road:</strong> a median of 629 days after the appeal was filed in the Federal Court of Appeal, of which about 210 days are the leave stage (60 days to apply, about 150 for the decision).</p><p>Where leave was granted, the Supreme Court judgment came a median of 1,094 days after the Federal Court of Appeal filing, in line with the 1,103 days found from published decisions above. Applications for leave are a selected group of appeals.</p></div>

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

<div class="chart-note"><p><span class="status">Pending review</span> <strong>Whether this table should be published at all.</strong></p><p>No individual is named or identifiable by design: figures are counts or distributions across judges, and a distribution over fewer than five judges is withheld. Published decisions only; Federal Court and Tax Court, where one judge decides; associate judges excluded; complement from Federal Judicial Affairs snapshots.</p></div>
