"""S6: Court of Appeal for Ontario Annual Report 2023–2024 — statistical appendix tables.

Verified 2026-11-16 (docs/sources.md S6): ``https://www.ontariocourts.ca/coa/files/annual-reports/
2023-2024-EN.pdf`` (92 pages). The charts on pp. 70–73 carry no numbers in the text layer, but the
same series are printed as tables in the statistical appendix (pp. 75–91), which we parse. Each
table is a year × column grid for 2014–2024.

Output: data/processed/s6/onca_tables.parquet, long: table, year, column, value, page.
Bias statement: court-published averages by filing year (timelines) or counts by calendar year;
timelines cover appeals heard and decided on their merits only.
"""

from __future__ import annotations

import io
import json
import logging
import re

import pdfplumber
import polars as pl

from courtdelay.common import paths
from courtdelay.common.http import Client

log = logging.getLogger(__name__)

SOURCE = "s6_onca_annual_report"
URL = "https://www.ontariocourts.ca/coa/files/annual-reports/2023-2024-EN.pdf"

# (table id, title regex matched against the page text, column names in order)
TABLES: list[tuple[str, str, list[str]]] = [
    ("appeals_filed", r"Number of Appeals Filed", ["civil", "criminal", "total"]),
    (
        "incoming_by_subject",
        r"Subject Matter of Incoming Appeals",
        ["total", "civil_excl_family", "family", "criminal_excl_inmate", "inmate"],
    ),
    (
        "motions_filed",
        r"Number of Motions Filed",
        [
            "mla_civil",
            "mla_criminal",
            "mla_total",
            "other_civil",
            "other_criminal",
            "other_total",
            "all_total",
        ],
    ),
    (
        "civil_mla_dispositions",
        r"Dispositions of Civil Motions for Leave",
        ["filed", "abandoned", "granted", "dismissed", "total_disposed"],
    ),
    (
        "criminal_mla_dispositions",
        r"Dispositions of Criminal Motions for Leave",
        ["filed", "abandoned", "granted", "dismissed", "total_disposed"],
    ),
    (
        "civil_appeal_dispositions",
        r"Dispositions of Civil Appeals",
        ["abandoned_or_admin_dismissed", "allowed", "dismissed_on_merits", "other", "settled"],
    ),
    (
        "criminal_appeal_dispositions",
        r"Dispositions of Criminal Appeals",
        ["abandoned_or_admin_dismissed", "allowed", "dismissed_on_merits", "other"],
    ),
    ("merits_hearings", r"Appeals Heard on Their Merits", ["civil", "criminal", "total"]),
    (
        "bench_reserved",
        r"Bench and Reserved Decisions",
        [
            "civil_bench",
            "criminal_bench",
            "total_bench",
            "civil_reserved",
            "criminal_reserved",
            "total_reserved",
        ],
    ),
    (
        "timeline_filing_to_decision",
        r"Appeal Timeline: From Filing to Decision",
        ["civil", "criminal_excl_inmate", "inmate", "average_total"],
    ),
    (
        "timeline_filing_to_ready",
        r"Phase #1: Filing to Scheduling Readiness\s*\nYear",
        ["civil", "criminal_excl_inmate", "inmate", "average_total"],
    ),
    (
        "timeline_ready_to_hearing",
        r"Phase #2: Scheduling Readiness to Hearing Date\s*\nYear",
        ["civil", "criminal_excl_inmate", "inmate", "average_total"],
    ),
    (
        "timeline_hearing_to_decision",
        r"Phase #3: Hearing Date to Decision Release\s*\nYear",
        ["civil", "criminal_excl_inmate", "inmate", "average_total"],
    ),
]
ROW_RE = re.compile(r"^(20\d{2})\s+((?:-?[\d.,]+%?\s*)+)$")


def fetch(client: Client) -> str:
    r = client.get(URL, source=SOURCE)
    return str(r.path)


def _num(s: str) -> float | None:
    s = s.replace(",", "").rstrip("%")
    try:
        return float(s)
    except ValueError:
        return None


def parse_page(text: str, page_no: int) -> list[dict]:
    rows = []
    for tid, title, cols in TABLES:
        m = re.search(title, text, re.I)
        if not m:
            continue
        # rows after the title until the table ends (the next title on the same page, if any)
        after = text[m.end() :]
        nxt = [re.search(t, after, re.I) for _, t, _ in TABLES if t != title]
        cut = min((x.start() for x in nxt if x), default=len(after))
        for line in after[:cut].splitlines():
            rm = ROW_RE.match(line.strip())
            if not rm:
                continue
            vals = [_num(v) for v in rm.group(2).split()]
            if len(vals) != len(cols):
                continue
            for c, v in zip(cols, vals, strict=True):
                rows.append(
                    {
                        "table": tid,
                        "year": int(rm.group(1)),
                        "column": c,
                        "value": v,
                        "page": page_no,
                    }
                )
    return rows


def parse(client: Client | None = None) -> pl.DataFrame:
    raw = paths.raw_dir(SOURCE)
    meta = None
    for mf in raw.glob("*.meta.json"):
        m = json.loads(mf.read_text())
        if m["url"] == URL and 200 <= m["status"] < 300:
            meta = m
    if meta is None:
        raise FileNotFoundError("S6: report not cached; run fetch first")
    rows = []
    with pdfplumber.open(io.BytesIO((raw / meta["file"]).read_bytes())) as pdf:
        for i in range(70, len(pdf.pages)):
            rows.extend(parse_page(pdf.pages[i].extract_text() or "", i + 1))
    df = (
        pl.DataFrame(rows)
        .unique()
        .sort(["table", "column", "year"])
        .with_columns(
            pl.lit(URL).alias("source_url"),
            pl.lit(meta["sha256"]).alias("raw_sha256"),
            pl.lit(meta["fetched_at"]).alias("fetched_at"),
        )
    )
    out = paths.processed_dir() / "s6"
    out.mkdir(exist_ok=True)
    df.write_parquet(out / "onca_tables.parquet")
    log.info("S6: %d cells from %d tables", df.height, df["table"].n_unique())
    return df


BENCHMARKS_2024_CIVIL = {  # docs/HANDOFF.md section 4, days
    "timeline_filing_to_ready": 140,
    "timeline_ready_to_hearing": 192,
    "timeline_hearing_to_decision": 65,
    "timeline_filing_to_decision": 397,
}


def validate(df: pl.DataFrame) -> None:
    problems = []
    found = set(df["table"].unique())
    missing = {t for t, _, _ in TABLES} - found
    if missing:
        problems.append(f"tables not parsed: {sorted(missing)}")
    for tid in (t for t, _, _ in TABLES if t in found):
        sub = df.filter(pl.col("table") == tid)
        if sub["year"].n_unique() != 11:
            problems.append(f"{tid}: {sub['year'].n_unique()} years (expected 11, 2014-2024)")
    for tid, bench in BENCHMARKS_2024_CIVIL.items():
        v = df.filter(
            (pl.col("table") == tid) & (pl.col("year") == 2024) & (pl.col("column") == "civil")
        )
        if v.height != 1 or abs(v["value"][0] - bench) > 1:
            problems.append(f"{tid} 2024 civil = {v['value'].to_list()} (benchmark ~{bench})")
    af = df.filter(pl.col("table") == "appeals_filed").pivot(
        on="column", index="year", values="value"
    )
    if af.height and (af["civil"] + af["criminal"] - af["total"]).abs().max() > 0:
        problems.append("appeals_filed: civil + criminal != total")
    if problems:
        raise ValueError("S6 validation failed:\n  " + "\n  ".join(problems))
    log.info("S6: all %d tables parsed; 2024 civil timelines match handoff benchmarks", len(found))
