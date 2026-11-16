# Site (Observable Framework, local only)

```
cd ..; uv run courtdelay build          # writes derived CSVs to site/src/data/ (gitignored)
cd site
npm install
OBSERVABLE_TELEMETRY_DISABLE=true npm run dev     # local preview
OBSERVABLE_TELEMETRY_DISABLE=true npm run build   # static output in site/dist/ (gitignored)
```

No deployment, hosting or scheduling is configured. The site name is a placeholder until the owner
chooses one. Every chart states its definition, n, uncertainty, vintage, source and bias.
