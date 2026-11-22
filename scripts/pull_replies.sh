#!/usr/bin/env bash
# Copy the replies left on the preview's "Questions for review" page into the project.
#
#   scripts/pull_replies.sh            writes data/review/replies.json (gitignored) and prints a summary
#
# Replies are stored in the Cloudflare D1 database docket-watch-replies (see site/worker/). They
# carry the reviewer's sign-in email, so they stay out of the repository.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/data/review"
cd "$ROOT/site"
npx wrangler d1 execute docket-watch-replies --remote --json \
  --command "SELECT id, issue, author, status, body, created_at FROM replies ORDER BY id" \
  > "$ROOT/data/review/replies.raw.json"
cd "$ROOT"
uv run --no-sync python - <<'EOF'
import json, collections
raw = json.load(open("data/review/replies.raw.json", encoding="utf-8"))
rows = raw[0]["results"] if isinstance(raw, list) else raw["results"]
json.dump(rows, open("data/review/replies.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
by = collections.Counter(r["issue"] for r in rows)
print(f"{len(rows)} replies on {len(by)} questions:", ", ".join(f"{k} ({v})" for k, v in sorted(by.items())))
EOF
rm -f "$ROOT/data/review/replies.raw.json"
