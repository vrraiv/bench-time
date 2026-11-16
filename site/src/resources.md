---
title: Resources
---

# Judicial complement and vacancies

```js
const v = FileAttachment("data/s9_vacancy_panel_monthly.csv").csv({typed: true});
const pick = view(Inputs.select(["FC", "FCA", "TCC", "SCC", "ONCA", "ONSC", "ONSC-Family"], {label: "Court", value: "ONSC"}));
```

```js
const s = v.filter(d => d.court_code === pick).map(d => ({...d, date: new Date(d.month)}));
display(Plot.plot({
  y: {label: "vacancies", grid: true}, x: {label: null},
  marks: [
    Plot.areaY(s, {x: "date", y: "vacancies", fillOpacity: 0.25, curve: "step-after"}),
    Plot.lineY(s, {x: "date", y: "vacancies", curve: "step-after"}),
    Plot.dot(s.filter(d => d.months_since_snapshot === 0), {x: "date", y: "vacancies", r: 2, tip: true})
  ]
}));
```

<p class="muted">Definition: vacancies on the Commissioner for Federal Judicial Affairs page "Number of federally appointed judges as of …". Dots mark months with a captured snapshot; the step line carries the last snapshot forward. Snapshots come from the Internet Archive (2009–2026) and are irregular before 2015. Bias: counts of judges, not FTE; supernumerary judges carry reduced loads; the page's own "as of" date is used.</p>

Whether delay rises when vacancies rise is the headline question; the court-by-month linkage to delay measures is the next milestone and will be shown with lags and an explicit reverse-causality caveat.
