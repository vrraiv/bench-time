---
title: Open issues
---

# Open issues

<div class="warning" label="Not for citation">
Shown only on this access-restricted preview. Please do not forward.
</div>

Questions we need answered before we rely on the results they touch. Each is settled (by the Registry, a court, or an expert) or, failing that, disclosed next to the results with the wording drafted below. The list started with the [questions for review](./questions) that could not be answered; see also the [earlier rounds](./questions-archive).

```js
const log = FileAttachment("review-data/open-issues.json").json();
```

```js
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
};
const root = el("div");
root.append(el("p", {className: "muted", textContent: `Updated ${log.updated}. ${log.issues.filter((i) => i.status === "open").length} open of ${log.issues.length}.`}));
for (const i of log.issues) {
  const card = el("section", {className: "card issue", id: i.id});
  card.append(el("h3", {},
    el("span", {className: "qid", textContent: `${i.id} · from ${i.from} · opened ${i.opened}`}), " ",
    el("span", {className: i.status === "open" ? "tag" : "tag tag-done", textContent: i.status})));
  card.append(el("p", {className: "q-text", textContent: i.issue}));
  const dl = el("dl", {className: "entry"});
  dl.append(el("dt", {textContent: "Affects"}), el("dd", {textContent: i.touches}));
  dl.append(el("dt", {textContent: "Who could settle it"}), el("dd", {textContent: i.routes.join("; ")}));
  dl.append(el("dt", {textContent: "If unresolved, we say"}), el("dd", {textContent: i.disclaimer}));
  if (i.progress) dl.append(el("dt", {textContent: "Progress"}), el("dd", {textContent: i.progress}));
  if (i.resolution) dl.append(el("dt", {textContent: "Resolution"}), el("dd", {textContent: i.resolution}));
  card.append(dl);
  root.append(card);
}
display(root);
```

<style>
.issue { margin: 1rem 0; max-width: 960px; padding: 0.75rem 1.25rem; }
#observablehq-main .issue h3 { margin: 0 0 0.25rem; font-size: 15px; }
.qid { font-size: 13px; font-weight: 600; color: var(--theme-foreground-muted); }
.q-text { font-size: 17px; max-width: 720px; margin: 0.5rem 0; }
.entry { display: grid; grid-template-columns: max-content 1fr; gap: 0.3rem 1rem; padding: 0.5rem 0.75rem; font-size: 15px; background: var(--theme-background-alt); border-radius: 6px; max-width: 720px; }
.entry dt { font-weight: 600; color: var(--theme-foreground-muted); }
.entry dd { margin: 0; }
.tag { font-size: 0.75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; background: var(--theme-foreground-faintest); }
.tag-done { background: #2e8b57; color: white; }
</style>
