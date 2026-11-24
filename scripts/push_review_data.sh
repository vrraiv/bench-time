#!/usr/bin/env bash
# Upload the preview's held-back files to the private R2 bucket the deploy workflow reads from.
#
#   scripts/push_review_data.sh            uploads site/src/review-data/* and a manifest
#
# The files in site/src/review-data/ (held-back tables and the question list) are gitignored so
# they stay out of the public repository. The GitHub workflow .github/workflows/preview-deploy.yml
# downloads them from the bucket before it builds. Run this after rebuilding them locally
# (uv run courtdelay build, or a re-import of the question lists), then trigger the workflow
# (gh workflow run preview-deploy.yml) or deploy by hand.
set -euo pipefail
BUCKET=docket-watch-review-data
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/site/src/review-data"
# the question list is kept in data/review/; copy the current one in first
if [ -f "$ROOT/data/review/questions.json" ]; then
  cp "$ROOT/data/review/questions.json" "$SRC/questions.json"
fi
# earlier rounds (scripts/archive_review_round.py) and the open-issues log, for their pages
for f in "$ROOT"/data/review/questions-archive-round*.json "$ROOT"/data/review/open-issues.json; do
  if [ -f "$f" ]; then cp "$f" "$SRC/"; fi
done
cd "$ROOT/site"
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
n=0
for f in "$SRC"/*; do
  name="$(basename "$f")"
  npx wrangler r2 object put "$BUCKET/$name" --file "$f" --remote > /dev/null
  echo "$name" >> "$MANIFEST"
  n=$((n + 1))
done
if [ "$n" -eq 0 ]; then
  echo "no files in $SRC; nothing uploaded" >&2
  exit 1
fi
npx wrangler r2 object put "$BUCKET/MANIFEST.txt" --file "$MANIFEST" --content-type text/plain --remote > /dev/null
echo "uploaded $n files and MANIFEST.txt to r2://$BUCKET"
