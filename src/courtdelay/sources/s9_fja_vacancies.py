"""S9: Federal judicial complement and vacancies (Commissioner for Federal Judicial Affairs).

Live page: "Number of Federally Appointed Judges in Canada" — one table per jurisdiction
(caption = jurisdiction) with columns Court | judges in office | supernumeraries | grand total |
women judges | current vacancies, under a heading "NUMBER OF FEDERALLY APPOINTED JUDGES AS OF
<Month D, YYYY>". History comes from Wayback Machine captures of the three URL variants listed in
``PAGE_VARIANTS`` (verified 2026-11-15; see docs/sources.md S9), one capture per month.

Output: data/processed/s9/judges_snapshots.parquet, long by (snapshot_date, jurisdiction, court).
Every row carries the capture timestamp and archived URL. Failed parses are listed in
data/processed/s9/parse_failures.parquet rather than dropped silently.

Caveats: monthly snapshots have gaps (Wayback coverage); "as of" dates are the page's own, not the
capture date; counts are judges, not FTE; supernumerary judges work reduced loads.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import polars as pl
from bs4 import BeautifulSoup

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s9_fja_vacancies"
LIVE_URL = "https://www.fja.gc.ca/appointments-nominations/judges-juges-eng.aspx"
PAGE_VARIANTS = [
    "fja.gc.ca/appointments-nominations/judges-juges-eng.html",
    "fja.gc.ca/appointments-nominations/judges-juges-eng.aspx",
    "fja-cmf.gc.ca/appointments-nominations/judges-juges-eng.aspx",
]
CDX = "https://web.archive.org/cdx/search/cdx"

_MONTH_NAMES = (
    "january february march april may june july august september october november december"
)
MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES.split(), start=1)}
AS_OF_RE = re.compile(
    r"as\s+of\s+(?:the\s+)?(\d{1,2})?\s*([A-Za-z]+)\s*(\d{1,2})?,?\s*(\d{4})", re.I
)

# header keyword -> canonical column
COLMAP = [
    ("vacan", "vacancies"),
    ("women", "women"),
    ("grand", "grand_total"),
    ("super", "supernumerary"),
    ("office", "in_office"),
    ("total", "grand_total"),
]


@dataclass
class Snapshot:
    as_of: str | None
    capture_ts: str
    url: str
    rows: list[dict] = field(default_factory=list)
    error: str | None = None


# -- fetch ---------------------------------------------------------------------------------


def cdx_captures(client: Client, variant: str) -> list[dict]:
    resp = client.get(
        CDX,
        source=SOURCE,
        params={
            "url": variant,
            "output": "json",
            "fl": "timestamp,original,statuscode,digest",
            "collapse": "timestamp:6",  # one per month
            "filter": "statuscode:200",
            "limit": "2000",
        },
    )
    data = resp.json()
    if not data:
        return []
    header, *rows = data
    return [dict(zip(header, r, strict=True)) for r in rows]


def fetch(client: Client) -> list[dict]:
    """Query CDX for every variant, then fetch each monthly capture (deduplicated by digest)
    plus the live page. Returns the capture list (also written to raw dir as captures.json)."""
    captures: dict[str, dict] = {}
    for v in PAGE_VARIANTS:
        rows = cdx_captures(client, v)
        log.info("S9 CDX %s: %d monthly captures", v, len(rows))
        for r in rows:
            captures.setdefault(r["digest"], r)  # same content under two hosts -> fetch once
    ordered = sorted(captures.values(), key=lambda r: r["timestamp"])
    log.info("S9: %d distinct captures to fetch", len(ordered))
    fetched = 0
    for r in ordered:
        url = f"https://web.archive.org/web/{r['timestamp']}id_/{r['original']}"
        try:
            resp = client.get(url, source=SOURCE)
            r["archive_url"], r["status"] = url, resp.status
            fetched += 1
        except FetchError as exc:
            r["archive_url"], r["status"] = url, exc.status
            log.warning("S9 capture %s failed: %s", r["timestamp"], exc)
    live = client.get(LIVE_URL, source=SOURCE, vintage=_today_month())
    ordered.append(
        {
            "timestamp": live.fetched_at.replace("-", "").replace(":", "")[:14],
            "original": LIVE_URL,
            "archive_url": LIVE_URL,
            "status": live.status,
            "digest": "live",
        }
    )
    (paths.raw_dir(SOURCE) / "captures.json").write_text(json.dumps(ordered, indent=1))
    log.info("S9: fetched %d/%d captures + live page", fetched, len(ordered) - 1)
    return ordered


def _today_month() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m")


# -- parse ---------------------------------------------------------------------------------


def parse_as_of(text: str) -> str | None:
    m = AS_OF_RE.search(text)
    if not m:
        return None
    d1, mon, d2, year = m.groups()
    day = d1 or d2
    mi = MONTHS.get(mon.lower())
    if not mi or not day:
        return None
    return f"{year}-{mi:02d}-{int(day):02d}"


def _int(s: str) -> int | None:
    s = s.replace(",", "").replace("\xa0", "").strip()
    if s in {"", "-", "—", "–", "N/A", "n/a"}:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_html(html: bytes | str, *, capture_ts: str = "", url: str = "") -> Snapshot:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    snap = Snapshot(as_of=parse_as_of(text), capture_ts=capture_ts, url=url)
    tables = soup.find_all("table")
    if not tables:
        snap.error = "no tables"
        return snap
    for tb in tables:
        header_cells = [c.get_text(" ", strip=True) for c in tb.find_all("th")]
        trs = tb.find_all("tr")
        if not trs:
            continue
        head_row = [c.get_text(" ", strip=True) for c in trs[0].find_all(["th", "td"])]
        if not any("vacan" in h.lower() for h in head_row + header_cells):
            continue
        # jurisdiction: caption, else nearest preceding heading
        cap = tb.find("caption")
        if cap:
            juris = cap.get_text(" ", strip=True)
        else:
            h = tb.find_previous(["h2", "h3", "h4", "strong"])
            juris = h.get_text(" ", strip=True) if h else "?"
        juris = re.sub(r"\s+", " ", juris).strip()
        colnames = []
        for h in head_row:
            hl = h.lower()
            name = next((c for k, c in COLMAP if k in hl), None)
            colnames.append(name)
        for tr in trs[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            court = re.sub(r"\s+", " ", cells[0]).strip()
            if not court or court.lower() in {"court", "total"} and len(cells) != len(colnames):
                continue
            row = {"jurisdiction": juris, "court": court}
            for name, val in zip(colnames[1:], cells[1:], strict=False):
                if name:
                    row[name] = _int(val)
            if any(v is not None for k, v in row.items() if k not in {"jurisdiction", "court"}):
                snap.rows.append(row)
    if not snap.rows:
        snap.error = "no judge tables recognised"
    return snap


def parse(client: Client | None = None) -> pl.DataFrame:
    raw = paths.raw_dir(SOURCE)
    captures = json.loads((raw / "captures.json").read_text())
    # map archive_url -> cached file via sidecars
    by_url: dict[str, dict] = {}
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if 200 <= meta["status"] < 300:
            by_url[meta["url"]] = meta
    snaps: list[Snapshot] = []
    failures = []
    for cap in captures:
        meta = by_url.get(cap["archive_url"])
        if meta is None:
            failures.append({**cap, "error": "not cached"})
            continue
        html = (raw / meta["file"]).read_bytes()
        snap = parse_html(html, capture_ts=cap["timestamp"], url=cap["archive_url"])
        if snap.error or snap.as_of is None:
            failures.append({**cap, "error": snap.error or "as-of date not found"})
            if snap.error:
                continue
        snaps.append(snap)
    rows = []
    for s in snaps:
        for r in s.rows:
            rows.append(
                {
                    "as_of": s.as_of,
                    "capture_ts": s.capture_ts,
                    "source_url": s.url,
                    **{
                        k: r.get(k)
                        for k in (
                            "jurisdiction",
                            "court",
                            "in_office",
                            "supernumerary",
                            "grand_total",
                            "women",
                            "vacancies",
                        )
                    },
                }
            )
    schema = {
        "as_of": pl.Utf8,
        "capture_ts": pl.Utf8,
        "source_url": pl.Utf8,
        "jurisdiction": pl.Utf8,
        "court": pl.Utf8,
        "in_office": pl.Int64,
        "supernumerary": pl.Int64,
        "grand_total": pl.Int64,
        "women": pl.Int64,
        "vacancies": pl.Int64,
    }
    df = pl.DataFrame(rows, schema=schema).unique().sort(["as_of", "jurisdiction", "court"])
    out = paths.processed_dir() / "s9"
    out.mkdir(exist_ok=True)
    df.write_parquet(out / "judges_snapshots.parquet")
    pl.DataFrame(
        failures,
        schema={
            "timestamp": pl.Utf8,
            "original": pl.Utf8,
            "statuscode": pl.Utf8,
            "digest": pl.Utf8,
            "archive_url": pl.Utf8,
            "status": pl.Int64,
            "error": pl.Utf8,
        },
    ).write_parquet(out / "parse_failures.parquet")
    log.info(
        "S9: %d captures, %d parsed, %d failures, %d snapshot dates, %d rows",
        len(captures),
        len(snaps),
        len(failures),
        df["as_of"].n_unique(),
        df.height,
    )
    return df


FEDERAL_COURTS = {
    "Supreme Court",
    "Federal Court of Appeal",
    "Federal Court",
    "Tax Court of Canada",
}
ONTARIO_COURTS = {"Court of Appeal", "Superior Court of Justice", "Family Court"}


def validate(df: pl.DataFrame) -> None:
    problems = []
    if df.height == 0:
        raise ValueError("S9: no rows")
    n_dates = df["as_of"].n_unique()
    if n_dates < 10:
        problems.append(f"only {n_dates} snapshot dates")
    if (df["vacancies"] < 0).any():
        problems.append("negative vacancies")
    tot = df.filter(
        pl.col("grand_total").is_not_null()
        & pl.col("in_office").is_not_null()
        & pl.col("supernumerary").is_not_null()
    )
    bad = tot.filter(pl.col("grand_total") != pl.col("in_office") + pl.col("supernumerary"))
    if bad.height > 0.05 * max(tot.height, 1):
        problems.append(f"{bad.height}/{tot.height} rows where grand_total != in_office + super")
    latest = df.filter(pl.col("as_of") == df["as_of"].max())
    fed = set(latest.filter(pl.col("jurisdiction") == "Canada")["court"])
    if not FEDERAL_COURTS <= fed:
        problems.append(f"latest Canada table missing courts: {FEDERAL_COURTS - fed}")
    ont = set(latest.filter(pl.col("jurisdiction") == "Ontario")["court"])
    if not ONTARIO_COURTS <= ont:
        problems.append(f"latest Ontario table missing courts: {ONTARIO_COURTS - ont}")
    per_year = (
        df.select(pl.col("as_of").str.slice(0, 4).alias("y"), "as_of")
        .unique()
        .group_by("y")
        .len()
        .sort("y")
    )
    log.info("S9 snapshots per year: %s", dict(zip(per_year["y"], per_year["len"], strict=True)))
    if problems:
        raise ValueError("S9 validation failed:\n  " + "\n  ".join(problems))
