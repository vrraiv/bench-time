// Observable Framework config. The built site (dist/) is served as static assets by a Cloudflare
// Worker behind Cloudflare Access (see wrangler.jsonc): a restricted preview, not a public site.
// Telemetry: run with OBSERVABLE_TELEMETRY_DISABLE=true (see site/README.md).
export default {
  title: "Docket Watch (preview)",
  root: "src",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Criminal (Ontario)", path: "/criminal"},
    {name: "Federal courts", path: "/federal"},
    {name: "Appellate: SCC and ONCA", path: "/appellate"},
    {name: "Resources", path: "/resources"},
    {name: "Results under review", path: "/review"},
    {name: "Questions for review", path: "/questions"},
    {name: "Methods", path: "/methods"},
    {name: "Sources & limitations", path: "/sources"}
  ],
  footer: "Working draft on a restricted preview: please do not forward. Aggregates only; no party names or decision texts. Each caption names its source and vintage.",
  search: false,
  linkify: true
};
