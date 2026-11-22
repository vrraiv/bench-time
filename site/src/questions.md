---
title: Questions for review
---

# Questions for review

<div class="warning" label="Not for citation">
These questions quote provisional figures. They are shown only on this access-restricted preview and are not in the public repository. Please do not forward them.
</div>

These are the questions we need a practitioner's reading on, collected from the review lists. Answer any of them in the box under the question, choose the kind of reply (a reply marks the question answered only when you choose **Answer** or **Don't know**), and press **Send**. A short answer is fine, and "don't know" is a useful answer. Replies are saved at once, can be seen by everyone who can open this preview, and show the email address you signed in with. You can reply more than once; nothing is overwritten.

```js
const data = FileAttachment("review-data/questions.json").json();
```

```js
const me = await fetch("/api/me").then((r) => (r.ok ? r.json() : null)).catch(() => null);
const loaded = me ? await fetch("/api/replies").then((r) => r.json()).catch(() => []) : [];
```

```js
display(
  me
    ? html`<p class="muted">Signed in as ${me.email}.</p>`
    : html`<div class="caution" label="Replies unavailable">The reply service did not answer, so replies cannot be shown or sent from this copy of the page. Open the page on the preview site, or reload it.</div>`
);
```

```js
const groupPick = view(
  Inputs.select(
    new Map([["All topics", ""], ...data.groups.map((g) => [g.title, g.id])]),
    {label: "Topic"}
  )
);
const onlyOpen = view(Inputs.toggle({label: "Hide questions already answered", value: false}));
```

```js
const STATUS = {
  answer: "Answer",
  partial: "Partial answer",
  "dont-know": "Don't know",
  discuss: "Let's discuss",
  comment: "Comment"
};
const byIssue = d3.group(loaded, (r) => r.issue);
const answered = (id) =>
  (byIssue.get(id) || []).some((r) => r.status === "answer" || r.status === "dont-know");

function replyItem(r) {
  const li = document.createElement("li");
  const head = document.createElement("div");
  head.className = "muted";
  head.textContent = `${STATUS[r.status] || r.status} · ${r.author} · ${r.created_at.replace("T", " ").replace("Z", " UTC")}`;
  const body = document.createElement("div");
  body.className = "reply-body";
  body.textContent = r.body;
  li.append(head, body);
  return li;
}

function table(t) {
  const el = document.createElement("table");
  const tr = el.createTHead().insertRow();
  for (const h of t.header) tr.append(Object.assign(document.createElement("th"), {textContent: h}));
  const tb = el.createTBody();
  for (const row of t.rows) {
    const r = tb.insertRow();
    for (const c of row) r.insertCell().textContent = c;
  }
  return el;
}

function issueCard(q) {
  const card = document.createElement("section");
  card.className = "card question";
  card.id = q.id;
  const h = document.createElement("h3");
  // a heading of its own when the list gave one; otherwise just the number (the question follows)
  const ownTitle = q.title !== q.question && !q.title.endsWith("…");
  h.textContent = ownTitle ? `${q.id}. ${q.title}` : q.id;
  const tag = document.createElement("span");
  tag.className = answered(q.id) ? "tag tag-done" : "tag";
  tag.textContent = answered(q.id) ? "answered" : "open";
  h.append(" ", tag);
  card.append(h);
  card.append(Object.assign(document.createElement("p"), {textContent: q.question}));
  if (q.context) card.append(Object.assign(document.createElement("p"), {className: "muted", textContent: q.context}));
  if (q.answer_in_word) card.append(Object.assign(document.createElement("p"), {className: "muted", textContent: `Answer already given in the Word list: ${q.answer_in_word}`}));

  const list = document.createElement("ul");
  list.className = "replies";
  for (const r of byIssue.get(q.id) || []) list.append(replyItem(r));
  card.append(list);

  if (me) {
    const form = document.createElement("form");
    form.className = "reply-form";
    const sel = document.createElement("select");
    for (const [k, v] of Object.entries(STATUS)) sel.append(new Option(v, k));
    sel.value = "comment"; // a reply counts as an answer only when chosen
    const ta = document.createElement("textarea");
    ta.rows = 3;
    ta.maxLength = 20000;
    ta.placeholder = "Your reply";
    const btn = Object.assign(document.createElement("button"), {type: "submit", textContent: "Send"});
    const msg = Object.assign(document.createElement("span"), {className: "muted"});
    form.append(ta, sel, btn, msg);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!ta.value.trim()) return;
      btn.disabled = true;
      msg.textContent = " Sending…";
      try {
        const r = await fetch("/api/replies", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({issue: q.id, status: sel.value, body: ta.value})
        });
        const out = await r.json();
        if (!r.ok) throw new Error(out.error || r.status);
        list.append(replyItem(out));
        ta.value = "";
        msg.textContent = " Saved.";
      } catch (err) {
        msg.textContent = ` Not saved: ${err.message}. Your text is still in the box.`;
      } finally {
        btn.disabled = false;
      }
    });
    card.append(form);
  }
  return card;
}

const root = document.createElement("div");
for (const g of data.groups) {
  if (groupPick && g.id !== groupPick) continue;
  const qs = data.issues.filter((q) => q.group === g.id && !(onlyOpen && answered(q.id)));
  if (!qs.length) continue;
  root.append(Object.assign(document.createElement("h2"), {textContent: g.title}));
  for (const para of (g.intro || "").split("\n\n").filter(Boolean))
    root.append(Object.assign(document.createElement("p"), {textContent: para}));
  for (const t of g.tables || []) {
    const d = document.createElement("details");
    d.append(Object.assign(document.createElement("summary"), {textContent: "Reference table"}), table(t));
    root.append(d);
  }
  root.append(Object.assign(document.createElement("p"), {className: "muted", textContent: `From: ${g.source}`}));
  for (const q of qs) root.append(issueCard(q));
}
display(root);
```

<style>
.question { margin: 1rem 0; max-width: 960px; }
.question h3 { margin-top: 0; }
.tag { font-size: 0.75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; background: var(--theme-foreground-faintest); vertical-align: middle; }
.tag-done { background: #2e8b57; color: white; }
.replies { list-style: none; padding-left: 0; }
.replies li { border-left: 3px solid var(--theme-foreground-faint); padding: 2px 0 2px 10px; margin: 8px 0; }
.reply-body { white-space: pre-wrap; }
.reply-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; }
.reply-form textarea { flex: 1 1 100%; font: inherit; }
</style>
