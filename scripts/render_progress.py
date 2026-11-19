"""Render the local progress tracker: progress/plan.json -> progress/plan.html (+ plan.png).

Usage: uv run --no-sync python scripts/render_progress.py [--png]

Cards flow left-to-right, top-to-bottom, grouped by phase, colour-coded by status
(done / in progress / to do / blocked). Steps with "status": "auto" and a "crawl" key take their
status and progress bar from the crawlers' progress files under data/raw/, so docket-crawl cards are
live each time this runs. --png also saves a screenshot via headless Edge or Chrome.
Everything under progress/ is gitignored (local tracker; owner request 2026-11-17).
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "progress"
RAW = ROOT / "data" / "raw"
BROWSERS = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
]


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def crawl_progress(kind: str) -> dict:
    """Return {fraction, label} for a crawl group from its progress files."""
    if kind == "tcc":
        years = list(range(2018, 2027))
        done, partial, label_now = 0, 0.0, ""
        for y in years:
            rows = _jsonl(RAW / "s12_tcc_dockets" / f"progress_{y}.jsonl")
            if any(r.get("done") for r in rows):
                done += 1
            elif rows:
                last = rows[-1]
                files = last.get("files") or 0
                got = last.get("entries_fetched") or 0
                partial = got / files if files else 0
                label_now = f"{y}: {got:,} of {files:,} files"
        frac = (done + partial) / len(years)
        label = f"{done} of {len(years)} years done" + (f" · {label_now}" if label_now else "")
        return {"fraction": frac, "label": label}

    base = RAW / "s10_fc_fca_dockets"
    prefix, years = {
        "fca": ("FCA", range(2010, 2027)),
        "imm": ("IMM", range(2023, 2027)),
        "fct": ("FCT", range(2018, 2027)),
    }[kind]
    done, partial, label_now, last_size = 0, 0.0, "", None
    for y in years:
        rows = _jsonl(base / f"progress_{prefix}-{y}.jsonl")
        fin = [r for r in rows if r.get("done")]
        if fin:
            done += 1
            last_size = fin[-1].get("last_n_probed") or fin[-1].get("tried")
        elif rows:
            last = rows[-1]
            if "n" in last:  # census: estimate from the previous year's size
                n = last["n"]
                denom = last_size or max(n * 1.5, 1)
                partial = min(n / denom, 0.95)
                label_now = f"{y}: at number {n:,}, {last.get('found', 0):,} files found"
            else:  # sample
                found = last.get("found", 0)
                partial = found / 1000
                label_now = f"{y}: {found:,} of 1,000 sampled"
    total = len(years)
    frac = (done + partial) / total
    label = f"{done} of {total} years done" + (f" · {label_now}" if label_now else "")
    return {"fraction": frac, "label": label}


STATUS = {
    "done": ("Done", "var(--done)"),
    "in_progress": ("In progress", "var(--prog)"),
    "todo": ("To do", "var(--todo)"),
    "blocked": ("Blocked", "var(--block)"),
}


def card(step: dict) -> str:
    status = step["status"]
    bar = ""
    if status == "auto":
        p = crawl_progress(step["crawl"])
        f = p["fraction"]
        status = "done" if f >= 0.999 else "in_progress" if f > 0 else "todo"
        bar = (
            f'<div class="bar"><span style="width:{f * 100:.1f}%"></span></div>'
            f'<div class="barlabel">{f * 100:.0f}% · {html.escape(p["label"])}</div>'
        )
    label, colour = STATUS[status]
    link = (
        f'<a href="{html.escape(step["link"])}">open</a>' if step.get("link") else ""
    )
    return (
        f'<article class="card" style="--c:{colour}">'
        f'<div class="pill">{label}</div>'
        f'<h3>{html.escape(step["title"])}</h3>'
        f'<p>{html.escape(step.get("detail", ""))} {link}</p>{bar}</article>'
    ), status


def render(plan: dict) -> tuple[str, dict]:
    counts = {k: 0 for k in STATUS}
    sections = []
    for phase in plan["phases"]:
        cards = []
        for step in phase["steps"]:
            c, st = card(step)
            counts[st] += 1
            cards.append(c)
        sections.append(f'<h2>{html.escape(phase["name"])}</h2>' + "".join(cards))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    legend = "".join(
        f'<span class="leg" style="--c:{c}"><i></i>{lab} · {counts[k]}</span>'
        for k, (lab, c) in STATUS.items()
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(plan["title"])}</title>
<style>
:root {{ --bg:#f6f7f9; --fg:#1d2433; --muted:#5b6475; --card:#fff; --line:#e3e6ec;
  --done:#2e8b57; --prog:#e0a100; --todo:#8a94a6; --block:#c2453d; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171c; --fg:#e7eaf0; --muted:#9aa3b2;
  --card:#1d2128; --line:#2c323c; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
header {{ max-width:1400px; margin:0 auto 8px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.meta {{ color:var(--muted); margin-bottom:10px; }}
.leg {{ display:inline-flex; align-items:center; gap:6px; margin-right:16px; color:var(--muted); }}
.leg i {{ width:12px; height:12px; border-radius:3px; background:var(--c); display:inline-block; }}
main {{ max-width:1400px; margin:0 auto; display:grid; gap:12px;
  grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); }}
h2 {{ grid-column:1/-1; font-size:15px; margin:18px 0 0; padding-bottom:4px;
  border-bottom:1px solid var(--line); }}
.card {{ background:var(--card); border:1px solid var(--line); border-left:6px solid var(--c);
  border-radius:8px; padding:10px 12px 12px; }}
.card h3 {{ font-size:14px; margin:6px 0 4px; }}
.card p {{ margin:0; color:var(--muted); font-size:13px; }}
.pill {{ display:inline-block; font-size:11px; font-weight:600; letter-spacing:.02em;
  color:#fff; background:var(--c); border-radius:999px; padding:1px 8px; }}
.bar {{ height:8px; background:var(--line); border-radius:999px; margin-top:10px;
  overflow:hidden; }}
.bar span {{ display:block; height:100%; background:var(--c); }}
.barlabel {{ font-size:12px; color:var(--muted); margin-top:4px; }}
a {{ color:inherit; }}
</style></head><body>
<header><h1>{html.escape(plan["title"])}</h1>
<div class="meta">Updated {now} · crawl cards read live progress files</div>
<div>{legend}</div></header>
<main>{"".join(sections)}</main></body></html>"""
    return page, counts


ARTIFACT_CSS = """
:root { --bg:#f6f7f9; --fg:#1d2433; --muted:#5b6475; --card:#ffffff; --line:#e3e6ec;
  --done:#2e8b57; --prog:#b98500; --todo:#7c8799; --block:#c2453d; --pill:#ffffff; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#14171c;
  --fg:#e7eaf0; --muted:#9aa3b2; --card:#1d2128; --line:#2c323c; --done:#3aa76d; --prog:#d9a520;
  --todo:#8a94a6; --block:#d9574f; --pill:#14171c; color-scheme: dark } }
:root[data-theme="dark"] { --bg:#14171c; --fg:#e7eaf0; --muted:#9aa3b2; --card:#1d2128;
  --line:#2c323c; --done:#3aa76d; --prog:#d9a520; --todo:#8a94a6; --block:#d9574f;
  --pill:#14171c; color-scheme: dark }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); padding-block:24px;
  padding-left:max(16px, env(safe-area-inset-left, 0px));
  padding-right:max(16px, env(safe-area-inset-right, 0px));
  font:14px/1.45 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
header { max-width:1400px; margin:0 auto 8px; }
h1 { font-size:22px; margin:0 0 4px; text-wrap:balance; }
.meta { color:var(--muted); margin-bottom:10px; }
.legend { display:flex; flex-wrap:wrap; gap:6px 16px; }
.leg { display:inline-flex; align-items:center; gap:6px; color:var(--muted);
  font-variant-numeric:tabular-nums; }
.leg i { width:12px; height:12px; border-radius:3px; background:var(--c); display:inline-block; }
main { max-width:1400px; margin:0 auto; display:grid; gap:12px;
  grid-template-columns:repeat(auto-fill,minmax(min(260px,100%),1fr)); }
h2 { grid-column:1/-1; font-size:15px; margin:18px 0 0; padding-bottom:4px;
  border-bottom:1px solid var(--line); }
.card { background:var(--card); border:1px solid var(--line); border-left:6px solid var(--c);
  border-radius:8px; padding:10px 12px 12px; min-width:0; overflow-wrap:anywhere; }
.card h3 { font-size:14px; margin:6px 0 4px; }
.card p { margin:0; color:var(--muted); font-size:13px; }
.pill { display:inline-block; font-size:11px; font-weight:600; letter-spacing:.02em;
  color:var(--pill); background:var(--c); border-radius:999px; padding:1px 8px; }
.bar { height:8px; background:var(--line); border-radius:999px; margin-top:10px; overflow:hidden; }
.bar span { display:block; height:100%; background:var(--c); }
.barlabel { font-size:12px; color:var(--muted); margin-top:4px; }
a { color:inherit; }
"""


def artifact_page(page: str) -> str:
    """Same cards as plan.html, as a fragment for publishing as a Claude artifact (the publisher
    adds the document skeleton; colours are theme tokens so it reads in light and dark)."""
    body = page.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    body = body.replace("<div>" + '<span class="leg"', '<div class="legend"><span class="leg"', 1)
    body = body.replace(" · crawl cards read live progress files", "")
    return (
        "<title>Bench-time Progress Tracker</title>\n"
        '<meta name="claude:viewport-fit-sides" content="cover">\n'
        f"<style>{ARTIFACT_CSS}</style>\n{body}\n"
    )


def screenshot(html_path: Path, png_path: Path) -> bool:
    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser is None:
        return False
    subprocess.run(
        [
            str(browser),
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1400,2000",
            f"--screenshot={png_path}",
            html_path.as_uri(),
        ],
        check=False,
        capture_output=True,
        timeout=60,
    )
    return png_path.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", action="store_true", help="also save progress/plan.png")
    args = ap.parse_args()
    plan = json.loads((OUT / "plan.json").read_text(encoding="utf-8"))
    page, counts = render(plan)
    out = OUT / "plan.html"
    out.write_text(page, encoding="utf-8")
    # fragment published as a Claude artifact (owner request 2026-11-19); republish after each run
    (OUT / "tracker.html").write_text(artifact_page(page), encoding="utf-8")
    print(f"wrote {out}  {counts}")
    if args.png:
        png = OUT / "plan.png"
        if png.exists():
            png.unlink()
        print("png:", png if screenshot(out, png) else "screenshot failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
