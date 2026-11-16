"""S7: Ontario Court of Justice criminal court statistics (courthouse panel).

Verified 2026-11-15 (docs/sources.md S7). Files live at
``https://www.ontariocourts.ca/ocj/files/stats/crim/{YYYY}/{YYYY}-{Series}-{Criminal|Youth}.{pdf|xlsx}``
with Series in {Offence-Based, Disposition-Rate, Clearance-Rate}. 2012–2019 are PDF
(calendar-year periods, January–December); 2020–2026 are XLSX (fiscal-year periods, April–March).
That is a **definition break**: period_start/period_end are carried on every row so the panel can be
aligned downstream; do not splice the two regimes without saying so.

Each file has one sheet/page per reporting unit: "Provincial Overview" (or "Ontario Overview"),
one "<Region> Overview" per region, and one per courthouse (~55). Data are collected by the Ministry
of the Attorney General; the Court disclaims accuracy. Averages exclude cases with bench warrants.

Outputs (data/processed/s7/):
  offence_based.parquet          unit x offence group/type x period: received, disposed,
                                 avg_days, avg_appearances, pending, disposed before trial …
  disposition_rate_monthly.parquet  unit x month: % disposed <10, 10–15, 15–18, >18 months,
                                 avg appearances, avg days (before / at / after trial, all)
  clearance_rate_monthly.parquet unit x month: received, disposed, disposed by route, net
  parse_log.parquet              one row per file: rows parsed, units, errors

Bias statement: completed cases; "days to disposition" runs from first appearance to disposition
and cannot separate court, Crown and defence delay; youth and adult files are separate.
"""

from __future__ import annotations

import io
import json
import logging
import re
from urllib.parse import urljoin

import pdfplumber
import polars as pl
from bs4 import BeautifulSoup

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s7_ocj_statistics"
INDEX = "https://www.ontariocourts.ca/ocj/statistics/"
FILE_RE = re.compile(
    r"/ocj/files/stats/crim/(\d{4})/\d{4}-(Offence-Based|Disposition-Rate|Clearance-Rate)-"
    r"(Criminal|Youth)\.(pdf|xlsx)$",
    re.I,
)
MONTHS = {
    m: i
    for i, m in enumerate(
        "jan feb mar apr may jun jul aug sep oct nov dec".split(),
        start=1,
    )
}
PERIOD_RE = re.compile(r"([A-Za-z]+)\s+(\d{4})\s+to\s+([A-Za-z]+)\s+(\d{4})")


def _mon(name: str) -> int | None:
    return MONTHS.get(name.strip().lower()[:3])


def parse_period(text: str) -> tuple[str | None, str | None]:
    """'January 2019 to December 2019' / 'April 2025 to March 2026' -> ISO month starts/ends."""
    m = PERIOD_RE.search(text or "")
    if not m:
        return None, None
    m1, y1, m2, y2 = m.groups()
    a, b = _mon(m1), _mon(m2)
    if not a or not b:
        return None, None
    import calendar

    return f"{y1}-{a:02d}-01", f"{y2}-{b:02d}-{calendar.monthrange(int(y2), b)[1]:02d}"


def unit_type(unit: str) -> str:
    u = unit.lower()
    if u in {"provincial overview", "ontario overview", "ontario"}:
        return "province"
    if u.endswith("overview"):
        return "region"
    return "courthouse"


def _num(s) -> float | None:
    if s is None:
        return None
    if isinstance(s, int | float):
        return float(s)
    t = str(s).strip().replace(",", "").replace("\xa0", "")
    pct = t.endswith("%")
    t = t.rstrip("%").strip()
    if t in {"", "-", "–", "—", "n/a", "N/A", "*"}:
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return v / 100 if pct else v


# -- fetch ---------------------------------------------------------------------------------


def list_files(index_html: bytes | str) -> list[dict]:
    soup = BeautifulSoup(index_html, "lxml")
    out = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(INDEX, a["href"])
        m = FILE_RE.search(href)
        if m:
            year, series, kind, ext = m.groups()
            out[href] = {
                "url": href,
                "year": int(year),
                "series": series.lower().replace("-", "_"),
                "case_type": "youth" if kind.lower() == "youth" else "all",
                "ext": ext.lower(),
            }
    return sorted(out.values(), key=lambda d: (d["series"], d["case_type"], d["year"]))


def fetch(client: Client, *, series: tuple[str, ...] | None = None) -> list[dict]:
    idx = client.get(INDEX, source=SOURCE)
    files = list_files(idx.content)
    if series:
        files = [f for f in files if f["series"] in series]
    log.info("S7: %d criminal statistics files listed", len(files))
    ok = 0
    for f in files:
        try:
            r = client.get(f["url"], source=SOURCE)
            f["path"], f["sha256"] = str(r.path), None
            ok += 1
        except FetchError as exc:
            log.warning("S7 %s: %s", f["url"], exc)
            f["path"] = None
    (paths.raw_dir(SOURCE) / "files.json").write_text(json.dumps(files, indent=1))
    log.info("S7: fetched %d/%d files", ok, len(files))
    return files


# -- offence-based -------------------------------------------------------------------------

OB_COLS = [
    "received",
    "received_share",
    "disposed",
    "avg_days",
    "avg_appearances",
    "pending",
    "before_trial_total",
    "before_trial_withdrawn_stayed",
    "before_trial_guilty_plea",
    "before_trial_other",
    "at_trial_total",
    "at_trial_guilty_plea",
    "at_trial_withdrawn",
    "at_trial_other",
    "following_trial_total",
    "trial_rate",
]


def _ob_rows(grid: list[list], unit: str, period: tuple, meta: dict) -> list[dict]:
    """Rows from a header-stripped grid: [group?, type, values…]."""
    start, end = period
    out = []
    group = None
    for row in grid:
        cells = [("" if c is None else str(c)).strip() for c in row]
        if len(cells) < 6:
            continue
        g, t = cells[0], cells[1]
        if g and g.lower() not in {"offence group", ""}:
            group = re.sub(r"\s+", " ", g)
        if not t or t.lower() in {"offence type", "total"} and not group:
            continue
        vals = [_num(c) for c in cells[2:]]
        if all(v is None for v in vals[:4]):
            continue
        rec = {
            "unit": unit,
            "unit_type": unit_type(unit),
            "period_start": start,
            "period_end": end,
            "case_type": meta["case_type"],
            "source_year": meta["year"],
            "offence_group": group,
            "offence_type": re.sub(r"\s+", " ", t),
            "source_url": meta["url"],
        }
        for name, v in zip(OB_COLS, vals, strict=False):
            rec[name] = v
        out.append(rec)
    return out


def parse_offence_xlsx(data: bytes, meta: dict) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        if len(grid) < 9:
            continue
        unit = str(grid[3][0] or ws.title).strip()
        period = parse_period(str(grid[4][0] or ""))
        # header occupies rows 6-7; data from the first row whose col B is non-empty after that
        start_i = next(
            (
                i
                for i in range(6, min(12, len(grid)))
                if grid[i][1] and str(grid[i][1]).upper() == "TOTAL"
            ),
            8,
        )
        rows.extend(_ob_rows(grid[start_i:], unit, period, meta))
    return rows


def parse_offence_pdf(data: bytes, meta: dict) -> list[dict]:
    rows = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            unit = lines[3] if len(lines) > 4 else "?"
            period = parse_period(lines[4] if len(lines) > 4 else "")
            for tbl in page.extract_tables():
                body = [
                    r
                    for r in tbl
                    if r and r[1] and str(r[1]).strip().lower() not in {"offence type", ""}
                ]
                body = [r for r in body if not (str(r[0] or "").strip().lower() == "offence group")]
                rows.extend(_ob_rows(body, unit, period, meta))
    return rows


# -- disposition rate (monthly) ------------------------------------------------------------

DR_COLS = [
    "pct_under_10m",
    "pct_10_15m",
    "pct_15_18m",
    "pct_over_18m",
    "avg_appearances",
    "avg_days_before_trial",
    "avg_days_at_trial",
    "avg_days_following_trial",
    "avg_days_all",
]
MONTH_LABEL_RE = re.compile(r"^([A-Za-z]+)\s+(\d{4})$")  # "April 2024"
MONTH_SLASH_RE = re.compile(r"^(\d{4})/([A-Za-z]{3})$")  # "2018/Jan"


def _month_from_label(label) -> str | None:
    if label is None:
        return None
    if hasattr(label, "year") and hasattr(label, "month"):
        return f"{label.year}-{label.month:02d}"
    s = str(label).strip()
    m = MONTH_LABEL_RE.match(s)
    if m and _mon(m.group(1)):
        return f"{m.group(2)}-{_mon(m.group(1)):02d}"
    m = MONTH_SLASH_RE.match(s)
    if m and _mon(m.group(2)):
        return f"{m.group(1)}-{_mon(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def _monthly_rows(grid, unit: str, meta: dict, cols: list[str], table: str) -> list[dict]:
    out = []
    for row in grid:
        cells = list(row)
        if not cells:
            continue
        month = _month_from_label(cells[0])
        if month is None:
            continue
        vals = [_num(c) for c in cells[1 : 1 + len(cols)]]
        if all(v is None for v in vals):
            continue
        rec = {
            "unit": unit,
            "unit_type": unit_type(unit),
            "month": month,
            "case_type": meta["case_type"],
            "source_year": meta["year"],
            "source_url": meta["url"],
        }
        rec.update(dict(zip(cols, vals, strict=False)))
        out.append(rec)
    return out


def parse_monthly_xlsx(data: bytes, meta: dict, cols: list[str], table: str) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        if len(grid) < 9:
            continue
        unit = str(grid[3][0] or ws.title).strip()
        rows.extend(_monthly_rows(grid[6:], unit, meta, cols, table))
    return rows


def parse_monthly_pdf(data: bytes, meta: dict, cols: list[str], table: str) -> list[dict]:
    """PDF monthly tables: pdfplumber merges rows, so parse text lines like
    '2018/Jan 85.1% 8.9% 2.8% 3.3% 7.4 121 364 378 151'."""
    rows = []
    line_re = re.compile(r"^(\d{4}/[A-Za-z]{3}|[A-Za-z]{3,9}\s+\d{4})\s+(.+)$")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            unit = lines[3] if len(lines) > 4 else "?"
            grid = []
            for ln in lines:
                m = line_re.match(ln)
                if m and _month_from_label(m.group(1)):
                    grid.append([m.group(1), *m.group(2).split()])
            rows.extend(_monthly_rows(grid, unit, meta, cols, table))
    return rows


CR_COLS = [
    "received",
    "disposed",
    "before_trial_n",
    "before_trial_pct",
    "at_trial_n",
    "at_trial_pct",
    "following_trial_n",
    "following_trial_pct",
    "net_received_less_disposed",
    "net_pct",
]


# -- parse / validate ----------------------------------------------------------------------


def parse(client: Client | None = None) -> dict[str, pl.DataFrame]:
    files = json.loads((paths.raw_dir(SOURCE) / "files.json").read_text())
    ob, dr, cr, logrows = [], [], [], []
    for f in files:
        if not f.get("path"):
            logrows.append({**f, "rows": 0, "error": "not fetched"})
            continue
        data = open(f["path"], "rb").read()
        try:
            if f["series"] == "offence_based":
                rows = (
                    parse_offence_xlsx(data, f)
                    if f["ext"] == "xlsx"
                    else parse_offence_pdf(data, f)
                )
                ob.extend(rows)
            elif f["series"] == "disposition_rate":
                rows = (
                    parse_monthly_xlsx(data, f, DR_COLS, "dr")
                    if f["ext"] == "xlsx"
                    else parse_monthly_pdf(data, f, DR_COLS, "dr")
                )
                dr.extend(rows)
            else:
                rows = (
                    parse_monthly_xlsx(data, f, CR_COLS, "cr")
                    if f["ext"] == "xlsx"
                    else parse_monthly_pdf(data, f, CR_COLS, "cr")
                )
                cr.extend(rows)
            units = len({r["unit"] for r in rows})
            logrows.append({**f, "rows": len(rows), "units": units, "error": None})
            log.info(
                "S7 %s %s %s: %d rows, %d units",
                f["year"],
                f["series"],
                f["case_type"],
                len(rows),
                units,
            )
        except Exception as exc:  # noqa: BLE001 - record and continue
            logrows.append({**f, "rows": 0, "error": f"{type(exc).__name__}: {exc}"})
            log.warning("S7 %s %s: %s", f["year"], f["series"], exc)
    out = paths.processed_dir() / "s7"
    out.mkdir(exist_ok=True)
    frames = {
        "offence_based": pl.DataFrame(ob, infer_schema_length=None) if ob else pl.DataFrame(),
        "disposition_rate_monthly": pl.DataFrame(dr, infer_schema_length=None)
        if dr
        else pl.DataFrame(),
        "clearance_rate_monthly": pl.DataFrame(cr, infer_schema_length=None)
        if cr
        else pl.DataFrame(),
    }
    for name, df in frames.items():
        if df.height:
            df = df.unique()
            frames[name] = df
            df.write_parquet(out / f"{name}.parquet")
    pl.DataFrame(logrows, infer_schema_length=None).write_parquet(out / "parse_log.parquet")
    return frames


def validate(frames: dict[str, pl.DataFrame]) -> None:
    problems = []
    ob = frames["offence_based"]
    if ob.height == 0:
        problems.append("offence_based: no rows")
    else:
        years = sorted(ob["source_year"].unique().to_list())
        prov = ob.filter((pl.col("unit_type") == "province") & (pl.col("offence_type") == "TOTAL"))
        log.info(
            "S7 offence_based: %d rows, source years %s..%s, %d units",
            ob.height,
            years[0],
            years[-1],
            ob["unit"].n_unique(),
        )
        if len(years) < 10:
            problems.append(f"offence_based: only {len(years)} source years")
        if prov.height == 0:
            problems.append("offence_based: no provincial TOTAL rows")
        bad = ob.filter((pl.col("avg_days") < 0) | (pl.col("avg_days") > 2000)).height
        if bad:
            problems.append(f"offence_based: {bad} rows with implausible avg_days")
        if ob["unit"].n_unique() < 40:
            problems.append(f"offence_based: only {ob['unit'].n_unique()} units (expected ~60)")
    dr = frames["disposition_rate_monthly"]
    if dr.height == 0:
        problems.append("disposition_rate: no rows")
    else:
        months = dr["month"].unique().sort()
        log.info("S7 disposition_rate: %d rows, months %s..%s", dr.height, months[0], months[-1])
        shares = dr.select(
            pl.sum_horizontal("pct_under_10m", "pct_10_15m", "pct_15_18m", "pct_over_18m").alias(
                "s"
            )
        )
        off = shares.filter((pl.col("s") < 0.97) | (pl.col("s") > 1.03)).height
        if off > 0.05 * dr.height:
            problems.append(
                f"disposition_rate: {off}/{dr.height} rows whose shares do not sum to 1"
            )
    cr = frames["clearance_rate_monthly"]
    if cr.height == 0:
        problems.append("clearance_rate: no rows")
    else:
        log.info(
            "S7 clearance_rate: %d rows, months %s..%s",
            cr.height,
            cr["month"].min(),
            cr["month"].max(),
        )
    if problems:
        raise ValueError("S7 validation failed:\n  " + "\n  ".join(problems))
