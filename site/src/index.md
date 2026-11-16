---
title: Overview
toc: false
---

# bench-time

<p class="muted">Working draft (local build). How long cases take in Ontario's courts and the federal courts, read as a court-resourcing question: how much of the wait is the institution's?</p>

```js
const s1 = FileAttachment("data/s1_median_days_by_offence.csv").csv({typed: true});
const s5 = FileAttachment("data/s5_scc_time_lapses.csv").csv({typed: true});
const s6 = FileAttachment("data/s6_onca_annual_report_tables.csv").csv({typed: true});
const fc = FileAttachment("data/s8_fc_annual_littles_law.csv").csv({typed: true});
```

```js
const onMedian = s1.filter(d => d.geo === "Ontario" && d.offences === "Total Criminal Code").sort((a, b) => d3.ascending(a.ref_date, b.ref_date)).at(-1);
const scc = s5.filter(d => d.stage === "hearing_to_judgment").sort((a, b) => a.year - b.year).at(-1);
const onca = s6.find(d => d.table === "timeline_filing_to_decision" && d.year === 2024 && d.column === "civil");
const fcLast = fc.filter(d => d.n_periods === 4).sort((a, b) => d3.ascending(a.year, b.year)).at(-1);
```

<div class="grid grid-cols-4">
  <div class="card"><h2>Ontario adult criminal cases</h2><span class="big">${onMedian?.median_days} days</span><p>Median, first appearance to decision, ${onMedian?.ref_date}. StatCan ICCS, completed cases only.</p></div>
  <div class="card"><h2>SCC hearing → judgment</h2><span class="big">${scc?.months} months</span><p>Average, ${scc?.year}. Court-published.</p></div>
  <div class="card"><h2>ONCA civil appeals</h2><span class="big">${onca?.value?.toFixed(0)} days</span><p>Average filing → decision, 2024 filings heard on the merits. ONCA annual report.</p></div>
  <div class="card"><h2>Federal Court pending</h2><span class="big">${fcLast?.pending_end?.toLocaleString()}</span><p>Proceedings pending at end of ${fcLast?.year}; commenced ÷ disposed = ${fcLast?.backlog_ratio?.toFixed(2)}.</p></div>
</div>

## What the data can and cannot say

- **Most published series measure total elapsed time.** They cannot separate waiting for the court from Crown, defence or party delay. Measures closer to institutional delay on this site: reserve time (hearing → decision), leave-granted → hearing in the Federal Court, and the ONCA "ready → hearing" phase.
- **Distributions where we have files, averages where courts publish them.** Federal Court immigration dockets (1997–2022) and published decisions give medians and tails; StatCan, OCJ and court tables give medians or averages only.
- **Known gaps:** no Superior Court of Justice timing series (Tier 3 sources not used); OCJ courthouse panel starts in 2012; Tax Court pending-status table not found; Federal Court of Appeal and Tax Court dockets not yet collected.

See [Sources & limitations](./sources) and [Methods](./methods).
