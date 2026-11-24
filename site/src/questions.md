---
title: Questions for review
---

# Questions for review

<div class="warning" label="Not for citation">
These questions quote provisional figures. They are shown only on this access-restricted preview and are not in the public repository. Please do not forward them.
</div>

These are our follow-up questions after the first round of answers (23 November 2026). Most ask you to look at a specific file we name; each shows, folded, what we asked before and what you said. The first round's questions and answers are kept in full on the **[earlier rounds](./questions-archive)** page. The first section, **Decisions for us both**, is about whom we ask next (the Registry, an outside expert) and who does the asking. Questions nobody has been able to answer yet are tracked on the **[open issues](./open-issues)** page until they are settled or disclosed with the results.

```js
const summary = FileAttachment("review-data/status-summary.pdf");
display(html`<p>For background: <a href=${summary.href} target="_blank" rel="noopener">where the project stands (status summary, PDF)</a>. It is updated from time to time; this link always opens the latest version.</p>`);
```

- **To reply:** type in the box under the question, choose the kind of reply, and press **Send**.
- **What counts as answered:** a question is marked answered only when you choose **Answer** or **Don't know**.
- **Short is fine.** "Don't know" is a useful answer.
- **Replies are visible** to everyone who can open this preview, saved at once, and show the email address you signed in with.
- You can reply more than once; nothing is overwritten.

```js
import {linkify, richText, useRecords} from "./components/filelinks.js";
const data = FileAttachment("review-data/questions.json").json();
const round1 = FileAttachment("review-data/questions-archive-round1.json").json();
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
    for (const c of row) r.insertCell().append(...linkify(c));
  }
  return el;
}

const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
};

// Paragraph text with a short lead-in label ("Why we are asking. …") shown in bold.
function leadPara(text) {
  const m = text.match(/^([^.]{3,45}\.)\s+(.*)$/s);
  if (m && m[1].split(/\s+/).length <= 6) return el("p", {}, el("strong", {textContent: m[1]}), " ", m[2]);
  return el("p", {textContent: text});
}

// A paragraph with an inline enumeration "(1) … (2) … (3) …" or "(a) … (b) …" becomes a lead
// paragraph, a list, and any closing sentences after the last item.
function introBlock(text) {
  for (const marks of [["1", "2", "3", "4", "5"], ["a", "b", "c", "d", "e"]]) {
    const pos = [];
    let from = 0;
    for (const k of marks) {
      const i = text.indexOf(` (${k}) `, from);
      if (i < 0) break;
      pos.push(i);
      from = i + 1;
    }
    if (pos.length < 2) continue;
    const items = pos.map((p, j) => text.slice(p + 5, pos[j + 1] ?? text.length).trim());
    // the last item runs to its first full stop; what follows is a closing paragraph
    const last = items.at(-1);
    const cut = last.search(/\.\s+(?=[A-Z])/);
    const tail = cut >= 0 ? last.slice(cut + 1).trim() : "";
    if (cut >= 0) items[items.length - 1] = last.slice(0, cut + 1);
    const out = [leadPara(text.slice(0, pos[0]).trim()), el("ul", {}, ...items.map((t) => el("li", {textContent: t})))];
    if (tail) out.push(...introBlock(tail));
    return out;
  }
  return [leadPara(text)];
}

// "Entry label: … Entries: … How we read it now: …" shown as a small labelled block.
const CONTEXT_LABELS = ["Entry label", "Entries", "How we read it now"];
function contextBlock(text) {
  const re = new RegExp(`(${CONTEXT_LABELS.join("|")}):\\s`, "g");
  const parts = text.split(re);
  if (parts.length < 3 || parts[0].trim()) return null;
  const dl = el("dl", {className: "entry"});
  for (let i = 1; i < parts.length; i += 2) dl.append(el("dt", {textContent: parts[i]}), el("dd", {textContent: parts[i + 1].trim()}));
  return dl;
}

function issueCard(q) {
  const card = el("section", {className: "card question", id: q.id});
  const ctx = q.context ? contextBlock(q.context) : null;
  // a heading of its own when the list gave one, unless the entry details must come first;
  // otherwise just the number, with the whole question below
  const ownTitle = !ctx && q.title !== q.question && !q.title.endsWith("…");
  const h = el("h3", {}, el("span", {className: "qid", textContent: q.id}), ownTitle ? q.title : "");
  const tag = el("span", {className: answered(q.id) ? "tag tag-done" : "tag", textContent: answered(q.id) ? "answered" : "open"});
  h.append(" ", tag);
  card.append(h);
  if (ctx) card.append(ctx);
  // don't repeat a heading that is just the question's first sentence
  const body = ownTitle && q.question.startsWith(q.title) ? q.question.slice(q.title.length).trim() : q.question;
  if (body) card.append(richText(body));
  if (q.context && !ctx) card.append(el("p", {className: "muted", textContent: q.context}));
  // the earlier exchange this follow-up builds on
  const prev = q.follows ? round1.issues.find((p) => p.id === q.follows) : null;
  if (prev) {
    const det = el("details", {className: "earlier"}, el("summary", {textContent: `Round 1 (${prev.id}): what we asked and what you said`}));
    det.append(el("p", {className: "muted"}, ...linkify(prev.question)));
    const ul = el("ul", {className: "replies"});
    for (const r of prev.replies || []) ul.append(replyItem({...r, author: "round 1"}));
    det.append(ul);
    card.append(det);
  }
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

useRecords(data.records_folder, data.records);
const root = document.createElement("div");
for (const g of data.groups) {
  if (groupPick && g.id !== groupPick) continue;
  const qs = data.issues.filter((q) => q.group === g.id && !(onlyOpen && answered(q.id)));
  if (!qs.length) continue;
  root.append(el("h2", {textContent: g.title}));
  root.append(el("p", {className: "group-meta", textContent: `${qs.length} question${qs.length === 1 ? "" : "s"} · from ${g.source}`}));
  const intro = el("div", {className: "group-intro"});
  for (const para of (g.intro || "").split("\n\n").filter(Boolean)) intro.append(...introBlock(para));
  root.append(intro);
  for (const t of g.tables || []) root.append(el("details", {}, el("summary", {textContent: "Reference table"}), table(t)));
  for (const q of qs) root.append(issueCard(q));
}
display(root);
```

<style>
.group-meta { font-size: 14px; color: var(--theme-foreground-muted); margin-top: 0; }
.group-intro { max-width: 720px; }
.group-intro p, .group-intro ul { max-width: none; }
.question { margin: 1.25rem 0; max-width: 960px; padding: 1rem 1.25rem; }
#observablehq-main .question h3 { margin-top: 0; margin-bottom: 0.5rem; font-size: 17px; font-weight: 600; color: var(--theme-foreground); max-width: 720px; }
.qid { font-size: 13px; font-weight: 500; color: var(--theme-foreground-muted); margin-right: 0.5rem; }
.q-text { font-size: 17px; max-width: 720px; margin: 0.5rem 0; }
.q-text p { margin: 0.5rem 0; }
.q-text ul { margin: 0.25rem 0 0.5rem; padding-left: 1.25rem; }
.q-text li { margin: 0.15rem 0; }
.filelink { white-space: nowrap; }
.entry { display: grid; grid-template-columns: max-content 1fr; gap: 0.2rem 1rem; margin: 0.5rem 0 0.75rem; padding: 0.5rem 0.75rem; font-size: 15px; background: var(--theme-background-alt); border-radius: 6px; max-width: 720px; }
.entry dt { font-weight: 600; color: var(--theme-foreground-muted); }
.entry dd { margin: 0; }
.tag { font-size: 0.75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; background: var(--theme-foreground-faintest); vertical-align: middle; }
.tag-done { background: #2e8b57; color: white; }
.replies { list-style: none; padding-left: 0; }
.replies li { border-left: 3px solid var(--theme-foreground-faint); padding: 2px 0 2px 10px; margin: 8px 0; }
.reply-body { white-space: pre-wrap; }
.earlier { margin: 0.5rem 0; max-width: 720px; font-size: 15px; }
.earlier summary { cursor: pointer; color: var(--theme-foreground-muted); }
.reply-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; }
.reply-form textarea { flex: 1 1 100%; font: inherit; }
</style>
