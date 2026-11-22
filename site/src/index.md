---
title: Overview
toc: false
---

# Docket Watch (preview)

<p class="muted">Working draft on a restricted preview. How long cases take in Ontario's courts and the federal courts, read as a court-resourcing question: how much of the wait is the institution's?</p>

```js
const s1 = FileAttachment("data/s1_median_days_by_offence.csv").csv({typed: true});
const s5 = FileAttachment("data/s5_scc_time_lapses.csv").csv({typed: true});
const s6 = FileAttachment("data/s6_onca_annual_report_tables.csv").csv({typed: true});
const fc = FileAttachment("data/s8_fc_annual_littles_law.csv").csv({typed: true});
const cohorts = FileAttachment("data/s10_fc_fca_km_by_cohort.csv").csv({typed: true});
```

```js
const onMedian = s1.filter(d => d.geo === "Ontario" && d.offences === "Total Criminal Code").sort((a, b) => d3.ascending(a.ref_date, b.ref_date)).at(-1);
const scc = s5.filter(d => d.stage === "hearing_to_judgment").sort((a, b) => a.year - b.year).at(-1);
const onca = s6.find(d => d.table === "timeline_filing_to_decision" && d.year === 2024 && d.column === "civil");
const fcLast = fc.filter(d => d.n_periods === 4).sort((a, b) => d3.ascending(a.year, b.year)).at(-1);
const latest = group => cohorts.filter(d => d.proceeding_group === group && d.p50_days != null).sort((a, b) => a.docket_year - b.docket_year).at(-1);
const fca = latest("FCA: all");
const fcGen = latest("FC: all");
```

<div class="grid grid-cols-3">
  <div class="card"><h2>Federal Court of Appeal files</h2><span class="big">${fca?.p50_days} days</span><p>Median, filing to end of file, files filed in ${fca?.docket_year} (95% interval ${fca?.p50_lo?.toFixed(0)}–${fca?.p50_hi?.toFixed(0)}; ${fca?.n?.toLocaleString()} files). Our census of court files.</p></div>
  <div class="card"><h2>Federal Court, non-immigration files</h2><span class="big">${fcGen?.p50_days} days</span><p>Median, filing to end of file, files filed in ${fcGen?.docket_year} (95% interval ${fcGen?.p50_lo?.toFixed(0)}–${fcGen?.p50_hi?.toFixed(0)}; ${fcGen?.n?.toLocaleString()} files). Our census of court files.</p></div>
  <div class="card"><h2>Federal Court pending</h2><span class="big">${fcLast?.pending_end?.toLocaleString()}</span><p>Proceedings pending at end of ${fcLast?.year}; commenced ÷ disposed = ${fcLast?.backlog_ratio?.toFixed(2)}. Court-published.</p></div>
  <div class="card"><h2>Ontario adult criminal cases</h2><span class="big">${onMedian?.median_days} days</span><p>Median, first appearance to decision, ${onMedian?.ref_date}. StatCan ICCS, completed cases only.</p></div>
  <div class="card"><h2>SCC hearing → judgment</h2><span class="big">${scc?.months} months</span><p>Average, ${scc?.year}. Court-published.</p></div>
  <div class="card"><h2>ONCA civil appeals</h2><span class="big">${onca?.value?.toFixed(0)} days</span><p>Average filing → decision, 2024 filings heard on the merits. ONCA annual report.</p></div>
</div>

## What is new on this draft

- **A census of court files.** Every Federal Court of Appeal file from 2010, every Federal Court non-immigration file from 2018 and every Tax Court file from 2018, read from the courts' public file searches in November 2026 and refreshed weekly. Results are on [Federal courts](./federal).
- **Checked against the courts' own statistics.** Federal Court (non-immigration): our yearly filing counts are within 2.5% of the Court's published counts and our counts of files ended are 95–102% of its for 2022–2025. Federal Court of Appeal: filings are within 2.5% and our counts of files ended are 94–100% of the court's, once its "preliminary applications" (motions brought before an appeal exists, which are not appeal files) are set aside.
- **Decisions linked to files.** Published decisions are matched to their court files by file number (99.8% link inside the census), which separates final from interlocutory decisions and checks hearing dates against the court record.
- **[Results under review](./review).** Tax Court durations, the wait for a Tax Court hearing, appeal chains, Supreme Court leave applications (every file opened from 2010) and judges against the judicial complement are shown there with their open questions. They are provisional.

## What is held back, and why

These results exist but are not in the public repository. On this preview they appear only on [Results under review](./review).

| Held back | Why |
|---|---|
| Tax Court: time from filing to the end of the file, and how files end | Waiting on practitioner answers about files held in abeyance and what several entry labels mean. The figures could move materially. |
| Tax Court: share of files that reach a hearing | The entry used to mark a hearing is sometimes a motion or status hearing, not the trial. Our count of hearings runs above the court's own. |
| Tax Court decisions matched to files | Held with the other Tax Court results so that everything about that court is reviewed together. |
| Appeal chains: filing in the court below to the end of the appeal, and the Supreme Court leg | The totals are lower bounds, not a trend, because files in the courts below only go back to 2018. The Supreme Court tables (leave applications by court appealed from, stages of heard appeals, the Federal Court of Appeal chain through leave) were built on 20 November 2026 and have not been reviewed. |
| Judges deciding against the judicial complement | No judge is named and small groups are withheld, but whether to publish this at all is still to be decided. |
| Counts of pending files from our census | Some file endings are missed, so our pending counts can run above the courts' own (by about 110 Federal Court of Appeal files for 2025; the Federal Court non-immigration count now agrees with the Court's). The comparison is on the review page. Pending totals shown on this site are the courts' figures. |

One further question is open and affects what may be published: 18 Federal Court files and 25 immigration files mention a publication ban. They are included in the aggregate figures for now, pending advice on whether they should be.

## What the data can and cannot say

- **Most published series measure total elapsed time.** They cannot separate waiting for the court from Crown, defence or party delay. Measures closer to institutional delay on this site: reserve time (hearing → decision), leave-granted → hearing in the Federal Court, and the ONCA "ready → hearing" phase.
- **Distributions where we have files, averages where courts publish them.** Court files and published decisions give medians and tails; StatCan, OCJ and court tables give medians or averages only.
- **Recent years are incomplete by design.** A median is shown only once at least half of a filing year's files have been followed long enough; until then the cell is blank.
- **Known gaps:** no Superior Court of Justice timing series (those sources are not used); OCJ courthouse panel starts in 2012; Supreme Court leave and appeal stages are built but under review; a few percent of file endings are missed, so the longest durations are slightly overstated.

See [Sources & limitations](./sources) and [Methods](./methods).
