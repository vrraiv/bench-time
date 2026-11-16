// Observable Framework config. Local preview/build only; nothing here deploys anywhere.
// Telemetry: run with OBSERVABLE_TELEMETRY_DISABLE=true (see site/README.md).
export default {
  title: "Court Delay Observatory (working title)",
  root: "src",
  pages: [
    {name: "Overview", path: "/"},
    {name: "Criminal (Ontario)", path: "/criminal"},
    {name: "Federal courts", path: "/federal"},
    {name: "Appellate: SCC and ONCA", path: "/appellate"},
    {name: "Resources", path: "/resources"},
    {name: "Methods", path: "/methods"},
    {name: "Sources & limitations", path: "/sources"}
  ],
  footer: "Working draft, not published. Aggregates only; no party names or decision texts. Data vintages are shown on each chart.",
  search: false,
  linkify: true
};
