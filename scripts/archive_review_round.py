"""Freeze one round of the practitioner's questions and her replies for the archive page on the
preview site ("Questions for review: earlier rounds").

    uv run --no-sync python scripts/archive_review_round.py <round> <closed YYYY-MM-DD>

Reads data/review/questions.json (the round's questions) and data/review/replies.json (written by
scripts/pull_replies.sh) and writes data/review/questions-archive-round<round>.json. Replies are
kept with their kind, text and time; the sign-in email is dropped. Everything under data/review/
is gitignored (the questions quote provisional figures); `courtdelay build` and
scripts/push_review_data.sh copy the archive files to site/src/review-data/ with the question list.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "data" / "review"


def main(round_no: str, closed: str) -> None:
    q = json.loads((REVIEW / "questions.json").read_text(encoding="utf-8"))
    replies = json.loads((REVIEW / "replies.json").read_text(encoding="utf-8"))
    ids = {i["id"] for i in q["issues"]}
    by: dict[str, list] = {}
    for r in replies:
        if r["issue"] in ids:
            by.setdefault(r["issue"], []).append(
                {"status": r["status"], "body": r["body"], "created_at": r["created_at"]}
            )
    for i in q["issues"]:
        i["replies"] = by.get(i["id"], [])
    out = REVIEW / f"questions-archive-round{round_no}.json"
    out.write_text(
        json.dumps(
            {
                "round": int(round_no),
                "closed": closed,
                "groups": q["groups"],
                "issues": q["issues"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    n = sum(bool(i["replies"]) for i in q["issues"])
    print(f"wrote {out.name}: {len(q['issues'])} questions, {n} with replies")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
