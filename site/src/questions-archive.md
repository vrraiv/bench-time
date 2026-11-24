---
title: Questions for review — earlier rounds
---

# Questions for review: earlier rounds

<div class="warning" label="Not for citation">
These questions quote provisional figures. They are shown only on this access-restricted preview and are not in the public repository. Please do not forward them.
</div>

Each round's questions, with the replies given on the [Questions for review](./questions) page, frozen when the round closed. Nothing here can be edited; where we needed more, the question was carried into the current round as a follow-up (marked below).

```js
const r1 = FileAttachment("review-data/questions-archive-round1.json").json();
const current = FileAttachment("review-data/questions.json").json();
```

```js
const STATUS = {answer: "Answer", partial: "Partial answer", "dont-know": "Don't know", discuss: "Let's discuss", comment: "Comment"};
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
};
const followUp = new Map(
  current.issues.flatMap((q) => [q.follows, ...(q.also_follows || [])].filter(Boolean).map((f) => [f, q.id]))
);

function table(t) {
  const tb = el("table");
  const tr = tb.createTHead().insertRow();
  for (const h of t.header) tr.append(el("th", {textContent: h}));
  const body = tb.createTBody();
  for (const row of t.rows) {
    const r = body.insertRow();
    for (const c of row) r.insertCell().textContent = c;
  }
  return tb;
}

function round(a) {
  const root = el("div");
  root.append(el("h2", {textContent: `Round ${a.round} (closed ${a.closed})`}));
  const n = a.issues.length;
  const fu = a.issues.filter((q) => followUp.has(q.id)).length;
  root.append(el("p", {className: "muted", textContent: `${n} questions; ${fu} carried into the current round as follow-ups.`}));
  for (const g of a.groups) {
    const qs = a.issues.filter((q) => q.group === g.id);
    root.append(el("h3", {textContent: g.title}));
    const intro = el("details", {}, el("summary", {textContent: "Background given with these questions"}));
    for (const p of (g.intro || "").split("\n\n").filter(Boolean)) intro.append(el("p", {textContent: p}));
    for (const t of g.tables || []) intro.append(table(t));
    root.append(intro);
    for (const q of qs) {
      const card = el("section", {className: "card question", id: q.id});
      const h = el("h4", {}, el("span", {className: "qid", textContent: q.id}));
      if (followUp.has(q.id)) {
        const a = el("a", {href: `./questions#${followUp.get(q.id)}`, textContent: `follow-up ${followUp.get(q.id)}`});
        h.append(" ", el("span", {className: "tag"}, a));
      }
      card.append(h);
      if (q.context) card.append(el("p", {className: "muted", textContent: q.context}));
      card.append(el("p", {className: "q-text", textContent: q.question}));
      const ul = el("ul", {className: "replies"});
      for (const r of q.replies || []) {
        ul.append(el("li", {},
          el("div", {className: "muted", textContent: `${STATUS[r.status] || r.status} · ${r.created_at.slice(0, 16).replace("T", " ")} UTC`}),
          el("div", {className: "reply-body", textContent: r.body})));
      }
      if (!(q.replies || []).length) ul.append(el("li", {className: "muted", textContent: "No reply."}));
      card.append(ul);
      root.append(card);
    }
  }
  return root;
}
display(round(r1));
```

<style>
.question { margin: 1rem 0; max-width: 960px; padding: 0.75rem 1.25rem; }
#observablehq-main .question h4 { margin: 0 0 0.25rem; }
.qid { font-size: 13px; font-weight: 600; color: var(--theme-foreground-muted); }
.q-text { font-size: 16px; max-width: 720px; margin: 0.25rem 0; }
.tag { font-size: 0.75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; background: var(--theme-foreground-faintest); }
.replies { list-style: none; padding-left: 0; }
.replies li { border-left: 3px solid #2e8b57; padding: 2px 0 2px 10px; margin: 8px 0; }
.reply-body { white-space: pre-wrap; }
</style>
