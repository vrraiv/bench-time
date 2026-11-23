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
  style: "style.css",
  // IBM Plex Sans (text) and Plex Mono (code), replacing Framework's default Source Serif 4; same
  // Google Fonts mechanism as before.
  globalStylesheets: [
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap"
  ],
  // Light by default; dark only if the reader chose it with the header toggle. Runs before paint
  // so there is no flash of the wrong theme. The system colour-scheme setting is not followed.
  head: `<script>
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
