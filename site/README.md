# Site (Observable Framework, local only)

```
cd ..; uv run courtdelay build          # regenerates the derived CSVs in site/src/data/ (committed)
cd site
npm install
OBSERVABLE_TELEMETRY_DISABLE=true npm run dev     # local preview
OBSERVABLE_TELEMETRY_DISABLE=true npm run build   # static output in site/dist/ (gitignored)
```

No deployment, hosting or scheduling is configured. Working title: bench-time (the repo will eventually be public). Every chart states its definition, n, uncertainty, vintage, source and bias.
