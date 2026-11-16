"""S5: Supreme Court of Canada annual statistics (HTML "Statistical summary" pages).

Verified 2026-11-15 (docs/sources.md S5): the old /review-revue/*.aspx and /case-dossier/stat/ URLs
soft-404 to the home page. The statistics now live at
``https://www.scc-csc.ca/about-apropos/work-travail/review-retro/stat-{YYYY}/`` for 2020..2025,
each a single table "Annual Supreme Court of Canada statistics by category, {Y0}–{Y1}" with an
11-year window. Rows are grouped under section labels (Cases filed, Applications for leave,
Appeals heard, Judgments, Average time lapses (in months) …).

Outputs (data/processed/s5/):
  scc_stats_long.parquet     every cell from every page: page_year, section, item, year, value
  scc_stats.parquet          one value per (section, item, year), taken from the most recent page
  scc_time_lapses.parquet    the three average time-lapse series, 2010–2025, in months

Bias statement: averages only (no distributions), counted by file number, as published by the
Court; windows overlap and later pages may revise earlier figures (conflicts are logged).
"""

from __future__ import annotations

import logging
import re

import polars as pl
from bs4 import BeautifulSoup

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s5_scc_statistics"
BASE = "https://www.scc-csc.ca/about-apropos/work-travail/review-retro/"
PAGE_YEARS = range(2020, 2031)  # probe forward; stop on first 404 after 2025

TIME_LAPSE_ITEMS = {
    "leave_filing_to_leave_decision": re.compile(
        r"filing of application for leave.*decision", re.I
    ),
    "leave_to_hearing": re.compile(r"leave granted.*hearing", re.I),
    "hearing_to_judgment": re.compile(r"hearing and judgment", re.I),
}


def page_url(year: int) -> str:
    return f"{BASE}stat-{year}/"


# Pre-2010 extension: the Court's former statistics page, category 5 (average time lapses,
# 2002-2012), as captured by the Wayback Machine on 2013-10-01 (verified 2026-11-16). Three
# tables, one per stage, each preceded by a heading naming the stage.
ARCHIVED_CAT5 = (
    "https://web.archive.org/web/20131001232343id_/"
    "http://www.scc-csc.gc.ca/case-dossier/stat/cat5-eng.aspx"
)
ARCHIVED_STAGE_ITEMS = [
    (
        re.compile(r"filing\s+of\s+and\s+decision\s+on", re.I),
        "Between filing of application for leave and decision on application for leave",
    ),
    (
        re.compile(r"leave\s+granted.*hearing", re.I | re.S),
        "Between date leave granted (or date notice of appeal as of right filed) and hearing",
    ),
    (re.compile(r"hearing\s+of\s+appeal\s+and\s+judgment", re.I), "Between hearing and judgment"),
]


def parse_archived_cat5(html: bytes | str, url: str = ARCHIVED_CAT5) -> pl.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tb in soup.find_all("table"):
        prev = tb.find_previous(["h2", "h3", "h4", "p", "strong"])
        label = re.sub(r"\s+", " ", prev.get_text(" ", strip=True)) if prev else ""
        item = next((it for rx, it in ARCHIVED_STAGE_ITEMS if rx.search(label)), None)
        trs = tb.find_all("tr")
        if item is None or len(trs) < 2:
            continue
        years = [
            int(c.get_text(strip=True))
            for c in trs[0].find_all(["th", "td"])
            if re.fullmatch(r"\d{4}", c.get_text(strip=True))
        ]
        vals = [c.get_text(strip=True) for c in trs[1].find_all(["th", "td"])][1:]
        for y, v in zip(years, vals, strict=False):
            rows.append(
                {
                    "page_year": 2012,
                    "page_as_of": "archived 2013-10-01",
                    "source_url": url,
                    "section": "Average time lapses (in months)",
                    "item": item,
                    "year": y,
                    "value": _num(v),
                    "raw": v,
                }
            )
    return pl.DataFrame(
        rows,
        schema={
            "page_year": pl.Int32,
            "page_as_of": pl.Utf8,
            "source_url": pl.Utf8,
            "section": pl.Utf8,
            "item": pl.Utf8,
            "year": pl.Int32,
            "value": pl.Float64,
            "raw": pl.Utf8,
        },
    )


def fetch(client: Client) -> list[int]:
    """Fetch every stat-{year} page that exists, plus the archived 2002-2012 time-lapse page.
    Returns the list of years found."""
    client.get(ARCHIVED_CAT5, source=SOURCE)
    found = []
    for y in PAGE_YEARS:
        try:
            resp = client.get(page_url(y), source=SOURCE)
        except FetchError as exc:
            if y > 2025:
                break
            log.warning("S5 stat-%d: %s", y, exc)
            continue
        # the site soft-404s to the home page; detect by title
        if "statistics" not in resp.text.lower() or "home-accueil" in resp.final_url:
            log.info("S5 stat-%d: not a statistics page (soft 404); stopping", y)
            if y > 2025:
                break
            continue
        found.append(y)
    log.info("S5: statistics pages for %s", found)
    return found


def _num(s: str) -> float | None:
    s = s.replace(",", "").replace("\xa0", " ").strip()
    s = re.sub(r"\s*%$", "", s)
    if s in {"", "-", "—", "–", "n/a", "N/A"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_html(html: bytes | str, *, page_year: int, url: str = "") -> pl.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    table = None
    for tb in soup.find_all("table"):
        cap = tb.find("caption")
        if cap and "statistics by category" in cap.get_text(" ", strip=True).lower():
            table = tb
            break
    if table is None:
        raise ValueError(f"stat-{page_year}: statistics table not found")
    caption = table.find("caption").get_text(" ", strip=True)
    m = re.search(r"as of\s+([A-Za-z]+ \d{1,2}, \d{4})", caption, re.I)
    as_of = m.group(1) if m else None
    rows = table.find_all("tr")
    years: list[int] | None = None
    section = ""
    out = []
    for tr in rows:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        if years is None:
            cand = [int(c) for c in cells if re.fullmatch(r"\d{4}", c)]
            if len(cand) >= 3:
                years = cand
            continue
        label = re.sub(r"\s+", " ", cells[0]).strip()
        values = cells[1:]
        if not any(_num(v) is not None for v in values):
            section = label  # a section header row
            continue
        if len(values) != len(years):
            log.warning(
                "stat-%d row %r has %d values for %d years",
                page_year,
                label,
                len(values),
                len(years),
            )
        for y, v in zip(years, values, strict=False):
            out.append(
                {
                    "page_year": page_year,
                    "page_as_of": as_of,
                    "source_url": url,
                    "section": section,
                    "item": label,
                    "year": y,
                    "value": _num(v),
                    "raw": v,
                }
            )
    if years is None or not out:
        raise ValueError(f"stat-{page_year}: no year header / no data rows")
    return pl.DataFrame(
        out,
        schema={
            "page_year": pl.Int32,
            "page_as_of": pl.Utf8,
            "source_url": pl.Utf8,
            "section": pl.Utf8,
            "item": pl.Utf8,
            "year": pl.Int32,
            "value": pl.Float64,
            "raw": pl.Utf8,
        },
    )


def _cached_pages() -> list[tuple[int, bytes, str]]:
    import json

    raw = paths.raw_dir(SOURCE)
    pages = []
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        m = re.search(r"stat-(\d{4})/?$", meta["url"])
        if m and 200 <= meta["status"] < 300 and "home-accueil" not in meta.get("final_url", ""):
            pages.append((int(m.group(1)), (raw / meta["file"]).read_bytes(), meta["url"]))
    return sorted(pages)


def _cached_archived() -> bytes | None:
    import json

    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if meta["url"] == ARCHIVED_CAT5 and 200 <= meta["status"] < 300:
            return (raw / meta["file"]).read_bytes()
    return None


def parse(client: Client | None = None) -> pl.DataFrame:
    frames = []
    for year, html, url in _cached_pages():
        try:
            frames.append(parse_html(html, page_year=year, url=url))
        except ValueError as exc:
            log.warning("S5: %s", exc)
    if not frames:
        raise FileNotFoundError("S5: no cached statistics pages; run fetch first")
    arch = _cached_archived()
    if arch is not None:
        frames.append(parse_archived_cat5(arch))
    long = pl.concat(frames)
    out = paths.processed_dir() / "s5"
    out.mkdir(exist_ok=True)
    long.write_parquet(out / "scc_stats_long.parquet")
    # conflicts: same (section,item,year) with different non-null values across pages
    conflicts = (
        long.filter(pl.col("value").is_not_null())
        .group_by(["section", "item", "year"])
        .agg(pl.col("value").n_unique().alias("n"), pl.col("value").alias("values"))
        .filter(pl.col("n") > 1)
    )
    if conflicts.height:
        log.warning("S5: %d cells differ across pages (keeping most recent page)", conflicts.height)
    preferred = (
        long.sort("page_year", descending=True)
        .unique(subset=["section", "item", "year"], keep="first")
        .sort(["section", "item", "year"])
    )
    preferred.write_parquet(out / "scc_stats.parquet")
    tl = preferred.filter(pl.col("section").str.contains("(?i)time lapse"))
    tl = tl.with_columns(
        pl.col("item")
        .map_elements(
            lambda s: next((k for k, rx in TIME_LAPSE_ITEMS.items() if rx.search(s)), "other"),
            return_dtype=pl.Utf8,
        )
        .alias("stage")
    ).select(["stage", "item", "year", "value", "page_year", "page_as_of", "source_url"])
    tl = (
        tl.rename({"value": "months"})
        .sort("page_year", descending=True)
        .unique(subset=["stage", "year"], keep="first")
        .sort(["stage", "year"])
    )
    tl.write_parquet(out / "scc_time_lapses.parquet")
    log.info(
        "S5: %d pages, %d cells, years %d..%d, %d time-lapse rows",
        len(frames),
        long.height,
        preferred["year"].min(),
        preferred["year"].max(),
        tl.height,
    )
    return tl


def validate(tl: pl.DataFrame) -> None:
    problems = []
    stages = set(tl["stage"].unique())
    missing = set(TIME_LAPSE_ITEMS) - stages
    if missing:
        problems.append(f"time-lapse stages missing: {missing}")
    if "other" in stages:
        others = tl.filter(pl.col("stage") == "other")["item"].unique().to_list()
        problems.append(f"unrecognised time-lapse items: {others}")
    yrs = tl["year"]
    if yrs.min() > 2010 or yrs.max() < 2025:  # 2002+ when the archived page is cached
        problems.append(f"year coverage {yrs.min()}..{yrs.max()} (expected 2010..2025+)")
    vals = tl.filter(pl.col("months").is_not_null())["months"]
    if len(vals) == 0 or vals.min() < 1 or vals.max() > 24:
        problems.append(f"months out of range: {vals.min()}..{vals.max()}")
    for stage in sorted(stages):
        s = tl.filter(pl.col("stage") == stage).sort("year")
        log.info(
            "S5 %s: %d..%d, latest %s = %.1f months",
            stage,
            s["year"].min(),
            s["year"].max(),
            s["year"].max(),
            s["months"][-1],
        )
    if problems:
        raise ValueError("S5 validation failed:\n  " + "\n  ".join(problems))
