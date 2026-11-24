"""Collect the practitioner's open questions from the Word review lists into one file for the
"Questions for review" page on the preview site.

    uv run --no-project --with python-docx python scripts/import_review_questions.py <folder>

<folder> is the folder that holds the review lists (pass it on the command line; do not write it
into any file). Writes data/review/questions.json (gitignored: the questions quote provisional
figures). Run again after a Word list changes: issues keep their ids, and any status, answer or
note already set in data/review/questions.json is kept.

Round 1 (the Word lists) closed 2026-11-23 and is frozen in
data/review/questions-archive-round1.json
(scripts/archive_review_round.py). From round 2 the current list is written by hand, so this
script refuses to overwrite a list whose "round" is 2 or more.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "review" / "questions.json"

# (file name, group id, group title, id prefix)
LISTS = [
    (
        "Federal Court statistics what the courts count review list.docx",
        "fc-statistics",
        "What the federal courts count in their published statistics",
        "FS",
    ),
    (
        "Federal Court files with confidentiality markers review list.docx",
        "fc-confidential",
        "Federal Court files with confidentiality markers",
        "FM",
    ),
    (
        "Supreme Court leave applications review list.docx",
        "scc-leave",
        "Supreme Court leave applications",
        "SC",
    ),
    (
        "Tax Court 2018 files without a procedure letter review list NEW.docx",
        "tcc",
        "Tax Court: files without a procedure letter, and what entry labels mean",
        "TC",
    ),
]


def _clean(t: str) -> str:
    return " ".join((t or "").split())


def _title(text: str, n: int = 90) -> str:
    first = re.split(r"(?<=[.?])\s", text, maxsplit=1)[0]
    return first if len(first) <= n else first[: n - 1].rsplit(" ", 1)[0] + "…"


def _intro(doc) -> str:
    """The paragraphs under the first 'Why...' / 'What this is' heading."""
    out, on = [], False
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            if on:
                break
            on = bool(re.match(r"(why|what this is)", p.text.strip(), re.I))
            continue
        if on and p.text.strip():
            out.append(_clean(p.text))
    return "\n\n".join(out)


def _intro_fallback(doc) -> str:
    """Lists written with bold lead-ins instead of headings: everything after the title lines
    up to the paragraph that reads "Questions"."""
    out = []
    for p in doc.paragraphs[2:]:
        t = _clean(p.text)
        if t.lower() == "questions":
            break
        if t:
            out.append(t)
    return "\n\n".join(out)


def _reference_tables(doc) -> list[dict]:
    """Tables that are not question tables (the kinds of entry, the list of files): kept whole
    so the questions that refer to them can be read on the page."""
    out = []
    for table in doc.tables:
        rows = [[_clean(c.text) for c in r.cells] for r in table.rows]
        if "question" in [h.lower() for h in rows[0]]:
            continue
        out.append({"header": rows[0], "rows": rows[1:]})
    return out


def _from_numbered_paragraphs(doc) -> list[dict]:
    """'1.  Question' paragraphs (one-paragraph form) or 'N. Heading' + text + 'Answer:'."""
    items, cur = [], None
    for p in doc.paragraphs:
        t = _clean(p.text)
        if not t:
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", t)
        if m:
            if cur:
                items.append(cur)
            cur = {"n": int(m.group(1)), "head": m.group(2), "body": [], "answer": ""}
            continue
        if cur is None:
            continue
        if p.style.name.startswith("Heading"):
            items.append(cur)
            cur = None
            continue
        if t.lower().startswith("answer:"):
            cur["answer"] = _clean(t[7:])
            continue
        cur["body"].append(t)
    if cur:
        items.append(cur)
    return items


def _from_tables(doc) -> list[dict]:
    items = []
    for table in doc.tables:
        head = [_clean(c.text).lower() for c in table.rows[0].cells]
        if "question" not in head:
            continue
        qi, ai = head.index("question"), head.index("answer") if "answer" in head else None
        li = next((i for i, h in enumerate(head) if h.startswith("entry label")), None)
        ni = next((i for i, h in enumerate(head) if h == "entries"), None)
        ri = next((i for i, h in enumerate(head) if h.startswith("how we read")), None)
        for row in table.rows[1:]:
            cells = [_clean(c.text) for c in row.cells]
            q = cells[qi]
            if not q:
                continue
            context = []
            if li is not None:
                context.append(f"Entry label: {cells[li]}")
            if ni is not None and cells[ni]:
                context.append(f"Entries: {cells[ni]}")
            if ri is not None and cells[ri]:
                context.append(f"How we read it now: {cells[ri]}")
            items.append(
                {
                    "head": None,
                    "body": [q],
                    "context": " ".join(context),
                    "answer": cells[ai] if ai is not None else "",
                }
            )
    return items


def main(folder: str) -> None:
    folder = Path(folder)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"issues": []}
    if old.get("round", 1) >= 2:
        sys.exit(
            f"{OUT} holds round {old['round']} follow-ups written by hand; not overwriting. "
            "Archive the round first (scripts/archive_review_round.py) if a new Word round starts."
        )
    keep = {i["id"]: i for i in old.get("issues", [])}
    groups, issues = [], []
    for fname, gid, gtitle, prefix in LISTS:
        path = folder / fname
        if not path.exists():
            print(f"missing, skipped: {fname}")
            continue
        doc = Document(path)
        groups.append(
            {
                "id": gid,
                "title": gtitle,
                "source": fname,
                "intro": _intro(doc) or _intro_fallback(doc),
                "tables": _reference_tables(doc),
            }
        )
        found = _from_tables(doc) + [
            {**x, "context": ""} for x in _from_numbered_paragraphs(doc) if not doc.tables
        ]
        if doc.tables and not any(x for x in found):
            found = [{**x, "context": ""} for x in _from_numbered_paragraphs(doc)]
        for k, x in enumerate(found, 1):
            iid = f"{prefix}-{k}"
            body = " ".join(x["body"]) if x["body"] else x["head"]
            title = x["head"] if (x.get("head") and x["body"]) else _title(body)
            prev = keep.get(iid, {})
            issues.append(
                {
                    "id": iid,
                    "group": gid,
                    "title": title,
                    "question": body,
                    "context": x.get("context", ""),
                    "status": prev.get("status", "answered" if x.get("answer") else "open"),
                    "answer_in_word": x.get("answer", ""),
                    "note": prev.get("note", ""),
                    "opened": prev.get("opened", str(date.today())),
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"groups": groups, "issues": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for g in groups:
        n = sum(i["group"] == g["id"] for i in issues)
        print(f"{g['id']}: {n} questions")


if __name__ == "__main__":
    main(sys.argv[1])
