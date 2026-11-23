// Observable Framework config. The built site (dist/) is served as static assets by a Cloudflare
// Worker behind Cloudflare Access (see wrangler.jsonc): a restricted preview, not a public site.
// Telemetry: run with OBSERVABLE_TELEMETRY_DISABLE=true (see site/README.md).
const FONTS = [
  ["ibm-plex-sans-latin-400-normal", "IBM Plex Sans", "400", "normal"],
  ["ibm-plex-sans-latin-400-italic", "IBM Plex Sans", "400", "italic"],
  ["ibm-plex-sans-latin-500-normal", "IBM Plex Sans", "500", "normal"],
  ["ibm-plex-sans-latin-600-normal", "IBM Plex Sans", "600", "normal"],
  ["ibm-plex-sans-latin-700-normal", "IBM Plex Sans", "700", "normal"],
  ["ibm-plex-mono-latin-400-normal", "IBM Plex Mono", "400", "normal"]
];

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
  style: "style.css",
  // No external stylesheets: this drops Framework's default Google Fonts link (Source Serif 4).
  globalStylesheets: [],
  // Fonts: IBM Plex, self-hosted from src/fonts/ (see fonts/README.txt). Framework copies files named
  // in <link href> and rewrites the paths, but cannot follow url() inside CSS, so the fonts are
  // preloaded here and registered with the FontFace API from those links.
  // Theme: light by default; dark only if the reader chose it with the header toggle. Runs before
  // paint so there is no flash of the wrong theme. The system colour-scheme setting is not followed.
  head: `${FONTS.map(([file, family, weight, style]) =>
    `<link rel="preload" as="font" type="font/woff2" crossorigin href="/fonts/${file}.woff2" data-family="${family}" data-weight="${weight}" data-style="${style}">`
  ).join("\n")}
<script>
(() => {
  for (const l of document.querySelectorAll("link[data-family]")) {
    try {
      const f = new FontFace(l.dataset.family, "url(" + l.href + ")", {weight: l.dataset.weight, style: l.dataset.style, display: "swap"});
      document.fonts.add(f);
      f.load().catch(() => {});
    } catch {}
  }
})();
(() => {
  const KEY = "docket-watch-theme";
  const root = document.documentElement;
  const set = (t) => {
    root.dataset.theme = t;
    const b = document.getElementById("theme-toggle");
    if (b) b.setAttribute("aria-pressed", String(t === "dark"));
  };
  let t = "light";
  try { if (localStorage.getItem(KEY) === "dark") t = "dark"; } catch {}
  set(t);
  document.addEventListener("DOMContentLoaded", () => set(root.dataset.theme));
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#theme-toggle")) return;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    set(next);
    try { localStorage.setItem(KEY, next); } catch {}
  });
})();
</script>`,
  header: `<button id="theme-toggle" type="button" aria-label="Dark mode" aria-pressed="false" title="Switch between light and dark mode"></button>`,
  footer:"Working draft on a restricted preview: please do not forward. Aggregates only; no party names or decision texts. Each caption names its source and vintage.",
  search: false,
  linkify: true
};
