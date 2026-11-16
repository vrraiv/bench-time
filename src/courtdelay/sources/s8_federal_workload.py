"""S8: Federal court workload (stock–flow) tables: FC, FCA, TCC, plus CAS annual reports (raw only).

Verified 2026-11-15 (docs/sources.md S8). All three court sites moved off *.gc.ca:
  FC   https://www.fct-cf.ca/en/pages/about-the-court/reports-and-statistics/statistics
       -> quarterly "Activity Summary" pages
          statistics-{march-31|june-30|september-30|december-31}-{YYYY} (2003–2026), one table:
          subject matter x proceedings commenced / dispositions / pending.
  FCA  https://www.fca-caf.ca/en/pages/about-the-court/statistics  (one page, one table per
       year-to-date quarter since 2019, same shape).
  TCC  https://www.tcc-cci.ca/en/pages/about/reports-and-statistics (one workload table, fiscal
       years 2018-19..2022-23). The handoff's status-at-March-31 table was not found.
  CAS  https://www.cas-satj.gc.ca/en/pages/publications/ar/annual-report-{Y}-{Y+1} (HTML annual
       reports with a "statistics at a glance" section; fetched and cached, parsed later).

Outputs (data/processed/s8/): fc_activity.parquet, fca_activity.parquet, tcc_workload.parquet.
Rows are the published figures per reporting period; periods are year-to-date (Jan 1 → quarter
end), so quarterly flows must be differenced downstream. "Pending" is a stock at period end.

Bias statement: counts of proceedings, not cases; categories change across years; the court
publishes these without a methodology note. Little's-law durations derived from them are
steady-state approximations.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

import polars as pl
from bs4 import BeautifulSoup

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s8_federal_workload"
FC_INDEX = "https://www.fct-cf.ca/en/pages/about-the-court/reports-and-statistics/statistics"
FCA_STATS = "https://www.fca-caf.ca/en/pages/about-the-court/statistics"
TCC_STATS = "https://www.tcc-cci.ca/en/pages/about/reports-and-statistics"
CAS_AR = "https://www.cas-satj.gc.ca/en/pages/publications/ar/annual-report-{a}-{b}"
CAS_YEARS = range(2013, 2026)

FC_QUARTER_RE = re.compile(r"statistics-(march-31|june-30|september-30|december-31)-(\d{4})/?$")
_MONTH_NAMES = (
    "january february march april may june july august september october november december"
)
MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES.split(), start=1)}
SCHEMA = {
    "court": pl.Utf8,
    "period_start": pl.Utf8,
    "period_end": pl.Utf8,
    "subject_matter": pl.Utf8,
    "commenced": pl.Int64,
    "dispositions": pl.Int64,
    "pending": pl.Int64,
    "leave_granted": pl.Int64,
    "source_url": pl.Utf8,
}


# -- fetch ---------------------------------------------------------------------------------


def fc_quarter_urls(index_html: bytes | str, base: str = FC_INDEX) -> list[str]:
    soup = BeautifulSoup(index_html, "lxml")
    urls = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        if FC_QUARTER_RE.search(href):
            urls.add(href.rstrip("/"))
    return sorted(urls, key=lambda u: (FC_QUARTER_RE.search(u).group(2), u))


def fetch(client: Client) -> dict:
    idx = client.get(FC_INDEX, source=SOURCE)
    urls = fc_quarter_urls(idx.content)
    log.info("S8 FC: %d quarterly pages listed", len(urls))
    ok = 0
    for u in urls:
        try:
            client.get(u, source=SOURCE)
            ok += 1
        except FetchError as exc:
            log.warning("S8 FC %s: %s", u, exc)
    client.get(FCA_STATS, source=SOURCE)
    client.get(TCC_STATS, source=SOURCE)
    cas = []
    for y in CAS_YEARS:
        u = CAS_AR.format(a=y, b=y + 1)
        try:
            client.get(u, source=SOURCE)
            cas.append(y)
        except FetchError as exc:
            log.info("S8 CAS %d-%d: %s", y, y + 1, exc.status)
    log.info("S8: FC %d/%d pages, CAS reports for %s", ok, len(urls), cas)
    (paths.raw_dir(SOURCE) / "fc_urls.json").write_text(json.dumps(urls, indent=1))
    return {"fc_pages": ok, "cas_years": cas}


# -- parse helpers -------------------------------------------------------------------------


def _int(s: str) -> int | None:
    s = s.replace(",", "").replace("\xa0", "").strip()
    if not re.fullmatch(r"-?\d+", s):
        return None
    return int(s)


def _date_from_text(text: str) -> tuple[str | None, str | None]:
    """'January 1, 2026 to March 31, 2026' / 'January 1st to December 31 2010' / 'From January 1 to
    June 30, 2026' -> (start, end) ISO dates."""
    t = re.sub(r"(\d)(st|nd|rd|th)", r"\1", text)
    m = re.search(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})?\s*(?:to|-|–|and)\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})",
        t,
    )
    if not m:
        return None, None
    m1, d1, y1, m2, d2, y2 = m.groups()
    if m1.lower() not in MONTHS or m2.lower() not in MONTHS:
        return None, None
    y1 = y1 or y2
    import calendar

    def _iso(y: str, mon: str, d: str) -> str:
        # the court occasionally publishes impossible dates ("June 31, 2009"): clamp to month end
        mi = MONTHS[mon.lower()]
        day = min(int(d), calendar.monthrange(int(y), mi)[1])
        return f"{y}-{mi:02d}-{day:02d}"

    return _iso(y1, m1, d1), _iso(y2, m2, d2)


def _colmap(header_cells: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    seen = set()
    for i, h in enumerate(header_cells):
        hl = h.lower()
        name = None
        if "commenc" in hl or "institut" in hl or "filed" in hl:
            name = "commenced"
        elif "disposition" in hl:
            name = "dispositions"
        elif "pending" in hl:
            name = "pending"
        elif "leave" in hl:
            name = "leave_granted"
        if name and name not in seen:
            out[i] = name
            seen.add(name)
    return out


def parse_activity_table(table, *, court: str, period_text: str, url: str) -> list[dict]:
    """Parse one FC/FCA activity-summary table into rows of SCHEMA."""
    start, end = _date_from_text(period_text)
    trs = table.find_all("tr")
    header_idx = None
    colmap: dict[int, str] = {}
    for i, tr in enumerate(trs):
        # expand colspans so header indices line up with data cells
        cells = []
        for c in tr.find_all(["th", "td"]):
            span = int(c.get("colspan", 1) or 1)
            cells.extend([c.get_text(" ", strip=True)] * span)
        cm = _colmap(cells)
        if {"commenced", "dispositions"} <= set(cm.values()):
            header_idx, colmap = i, cm
            # a second header row may carry the pending date ("31/03/2026")
            break
    if header_idx is None:
        return []
    # Multi-row headers: the first data row may still be header fragments (dates). Skip rows whose
    # first cell is empty or purely a date.
    rows = []
    for tr in trs[header_idx + 1 :]:
        tds = tr.find_all(["td", "th"])
        cells = [c.get_text(" ", strip=True) for c in tds]
        if not cells:
            continue
        label = re.sub(r"\s+", " ", cells[0]).strip()
        if not label or re.fullmatch(r"[\d/–-]+", label) or label.lower().startswith("pending"):
            continue
        # header cells may have colspans in the data; align by index when lengths match,
        # otherwise take the first numeric cells in column order.
        vals = cells[1:]
        row = {
            "court": court,
            "period_start": start,
            "period_end": end,
            "subject_matter": label,
            "commenced": None,
            "dispositions": None,
            "pending": None,
            "leave_granted": None,
            "source_url": url,
        }
        if len(cells) >= max(colmap) + 1:
            for i, name in colmap.items():
                row[name] = _int(cells[i])
        else:
            nums = [_int(v) for v in vals]
            for name, v in zip(("commenced", "dispositions", "pending"), nums, strict=False):
                row[name] = v
        if any(row[k] is not None for k in ("commenced", "dispositions", "pending")):
            rows.append(row)
    return rows


def parse_fc_page(html: bytes | str, url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    text_candidates = []
    for tb in soup.find_all("table"):
        if tb.find("table"):  # archived pages wrap the real table in a layout table
            continue
        cap = tb.find("caption")
        prev = tb.find_previous(["h1", "h2", "h3", "h4", "p", "strong"])
        for cand in (
            cap.get_text(" ", strip=True) if cap else "",
            prev.get_text(" ", strip=True) if prev else "",
        ):
            if cand and _date_from_text(cand) != (None, None):
                text_candidates.append((tb, cand))
                break
        else:
            # fall back to the page title / URL
            m = FC_QUARTER_RE.search(url)
            if m:
                q, y = m.groups()
                month, day = q.split("-")
                text_candidates.append((tb, f"January 1, {y} to {month} {day}, {y}"))
    rows = []
    for tb, period in text_candidates:
        rows.extend(parse_activity_table(tb, court="FC", period_text=period, url=url))
    # pages sometimes duplicate the table (archived-content wrapper): dedupe
    uniq = {json.dumps(r, sort_keys=True): r for r in rows}
    return list(uniq.values())


def parse_fca_page(html: bytes | str, url: str = FCA_STATS) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tb in soup.find_all("table"):
        if tb.find("table"):
            continue
        h = tb.find_previous(["h2", "h3", "h4"])
        period = h.get_text(" ", strip=True) if h else ""
        if _date_from_text(period) == (None, None):
            cap = tb.find("caption")
            period = cap.get_text(" ", strip=True) if cap else period
        rows.extend(parse_activity_table(tb, court="FCA", period_text=period, url=url))
    return rows


def parse_tcc_page(html: bytes | str, url: str = TCC_STATS) -> pl.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tb in soup.find_all("table"):
        trs = tb.find_all("tr")
        header = None
        for tr in trs:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            fys = [c for c in cells if re.fullmatch(r"\d{4}-\d{2,4}", c)]
            if len(fys) >= 3:
                header = cells
                break
        if header is None:
            continue
        fy_cols = {i: c for i, c in enumerate(header) if re.fullmatch(r"\d{4}-\d{2,4}", c)}
        for tr in trs:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells == header or len(cells) < 2:
                continue
            metric = re.sub(r"\s+", " ", cells[0]).strip()
            for i, fy in fy_cols.items():
                if i < len(cells) and _int(cells[i]) is not None:
                    out.append(
                        {
                            "court": "TCC",
                            "metric": metric,
                            "fiscal_year": fy,
                            "value": _int(cells[i]),
                            "source_url": url,
                        }
                    )
    return pl.DataFrame(
        out,
        schema={
            "court": pl.Utf8,
            "metric": pl.Utf8,
            "fiscal_year": pl.Utf8,
            "value": pl.Int64,
            "source_url": pl.Utf8,
        },
    )


def _cached(url: str) -> bytes | None:
    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if meta["url"].rstrip("/") == url.rstrip("/") and 200 <= meta["status"] < 300:
            return (raw / meta["file"]).read_bytes()
    return None


def parse(client: Client | None = None) -> dict[str, pl.DataFrame]:
    raw = paths.raw_dir(SOURCE)
    urls = json.loads((raw / "fc_urls.json").read_text())
    fc_rows, missing, empty = [], [], []
    for u in urls:
        html = _cached(u)
        if html is None:
            missing.append(u)
            continue
        rows = parse_fc_page(html, u)
        if not rows:
            empty.append(u)
        fc_rows.extend(rows)
    fc = pl.DataFrame(fc_rows, schema=SCHEMA).sort(["period_end", "subject_matter"])
    log.info(
        "S8 FC: %d pages, %d not cached, %d parsed to nothing, %d rows, %d periods",
        len(urls),
        len(missing),
        len(empty),
        fc.height,
        fc["period_end"].n_unique(),
    )
    for u in empty:
        log.warning("S8 FC: no table parsed from %s", u)
    fca_html = _cached(FCA_STATS)
    fca = pl.DataFrame(parse_fca_page(fca_html) if fca_html else [], schema=SCHEMA).sort(
        ["period_end", "subject_matter"]
    )
    log.info("S8 FCA: %d rows, %d periods", fca.height, fca["period_end"].n_unique())
    tcc_html = _cached(TCC_STATS)
    tcc = parse_tcc_page(tcc_html) if tcc_html else pl.DataFrame(schema={"court": pl.Utf8})
    log.info("S8 TCC: %d rows", tcc.height)
    out = paths.processed_dir() / "s8"
    out.mkdir(exist_ok=True)
    fc.write_parquet(out / "fc_activity.parquet")
    fca.write_parquet(out / "fca_activity.parquet")
    tcc.write_parquet(out / "tcc_workload.parquet")
    return {"fc": fc, "fca": fca, "tcc": tcc}


def validate(frames: dict[str, pl.DataFrame]) -> None:
    problems = []
    fc, fca, tcc = frames["fc"], frames["fca"], frames["tcc"]
    if fc["period_end"].n_unique() < 80:
        problems.append(f"FC: only {fc['period_end'].n_unique()} periods parsed (expected ~90)")
    if fc.filter(pl.col("period_start").is_null()).height:
        problems.append("FC: rows without a period")
    for name, df in (("FC", fc), ("FCA", fca)):
        neg = df.filter((pl.col("pending") < 0) | (pl.col("commenced") < 0)).height
        if neg:
            problems.append(f"{name}: {neg} negative counts")
        totals = df.filter(pl.col("subject_matter").str.to_lowercase().str.contains("total"))
        if totals.height == 0:
            problems.append(f"{name}: no total rows found")
    if fca["period_end"].n_unique() < 20:
        problems.append(f"FCA: only {fca['period_end'].n_unique()} periods parsed")
    if tcc.height == 0 or tcc["fiscal_year"].n_unique() < 5:
        problems.append("TCC: workload table not parsed")
    latest = fc.filter(pl.col("period_end") == fc["period_end"].max())
    tot = latest.filter(
        pl.col("subject_matter").str.to_lowercase().str.contains("^total$|grand total|^total ")
    )
    if tot.height:
        log.info(
            "S8 FC latest %s: %s",
            fc["period_end"].max(),
            tot.select(["subject_matter", "commenced", "dispositions", "pending"]).to_dicts()[:3],
        )
    if problems:
        raise ValueError("S8 validation failed:\n  " + "\n  ".join(problems))
