# Site (Observable Framework, local only)

```
cd ..; uv run courtdelay build          # regenerates the derived CSVs in site/src/data/ (committed)
cd site
npm install
OBSERVABLE_TELEMETRY_DISABLE=true npm run dev     # local preview
OBSERVABLE_TELEMETRY_DISABLE=true npm run build   # static output in site/dist/ (gitignored)
```

The only deployment is the restricted preview below; the public site is not hosted yet. Working title: bench-time (the repo will eventually be public). Every chart states its definition, n, uncertainty, vintage, source and bias.

## Restricted preview (Cloudflare)

`wrangler.jsonc` serves `dist/` as static assets from a Cloudflare Worker that sits behind
Cloudflare Access. The preview also shows `src/review.md`, which reads tables from
`src/review-data/`: results held back from this repository until they have been reviewed. That
folder is gitignored and is written by `uv run courtdelay build`, so the site only builds after
the pipeline has run. Deploy order (so the site is never reachable without a login) is in the
header of `wrangler.jsonc`.

Deploys run from GitHub (`.github/workflows/preview-deploy.yml`) on every push to `main` that
touches `site/`, or by hand with `gh workflow run preview-deploy.yml`. The workflow downloads the
held-back files from the private R2 bucket `docket-watch-review-data` and stops if any is
missing. After rebuilding them locally, upload them with `scripts/push_review_data.sh` and run
the workflow; a merge alone does not refresh them.
