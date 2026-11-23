"""S1: Statistics Canada Integrated Criminal Court Survey (ICCS) tables (full-table zip downloads).

Tables (verified 2026-11-15; see docs/sources.md):
  35-10-0029-01  Adult criminal courts, cases by median elapsed time in days
  35-10-0027-01  Adult criminal courts, number of cases and charges by type of decision
  35-10-0173-01  Adult criminal courts, key indicators (annual)
  35-10-0174-01  Youth courts, key indicators (annual)
  35-10-0172-01  Adult criminal courts, preliminary quarterly indicators
  35-10-0176-01  Youth courts, preliminary quarterly indicators

Outputs: data/processed/s1/<pid>.parquet (Canada + Ontario rows, all dimensions) and
data/processed/s1/tables.parquet (fetch time and raw hash per table).

Bias statement (carry onto every chart): completed cases only; elapsed time runs from first
appearance to final decision and cannot be attributed to Crown, defence or court.
"""

from __future__ import annotations

import logging

import polars as pl

from courtdelay.common import paths, statcan
from courtdelay.common.http import Client

log = logging.getLogger(__name__)

SOURCE = "s1_statcan_iccs"

TABLES: dict[int, str] = {
    35100029: "adult_median_elapsed_time",
    35100027: "adult_cases_by_decision",
    35100173: "adult_key_indicators_annual",
    35100174: "youth_key_indicators_annual",
    35100172: "adult_preliminary_quarterly",
    35100176: "youth_preliminary_quarterly",
}

GEOS = ("Canada", "Ontario")


def fetch(client: Client, *, vintage: str = "") -> dict[int, dict]:
    """Download the full-table zip for every table. Returns {pid: {meta, zip_path, fetched_at}}."""
    out: dict[int, dict] = {}
    for pid in TABLES:
        resp = statcan.fetch_table_zip(client, pid, source=SOURCE, vintage=vintage)
        headers = statcan.cached_meta(resp).get("response_headers", {})
        meta = statcan.table_meta(resp.content, pid, release_time=headers.get("last-modified", ""))
        log.info(
            "S1 %s %s: %s..%s released %s (%d bytes%s)",
            pid,
            meta.title_en,
            meta.start,
            meta.end,
            meta.release_time,
            len(resp.content),
            ", cached" if resp.from_cache else "",
        )
        out[pid] = {"meta": meta, "zip_path": resp.path, "fetched_at": resp.fetched_at}
    return out


def parse(client: Client | None = None) -> dict[int, pl.DataFrame]:
    """Parse cached zips into tidy frames and write parquet. Returns {pid: frame}."""
    frames: dict[int, pl.DataFrame] = {}
    meta_rows = []
    out_dir = paths.processed_dir() / "s1"
    out_dir.mkdir(exist_ok=True)
    for pid, name in TABLES.items():
        zip_path, meta = statcan.latest_cached_zip(SOURCE, pid)
        df = statcan.read_table_zip(zip_path.read_bytes(), pid)
        tidy = statcan.tidy(df, pid, geos=GEOS).with_columns(
            pl.lit(meta["fetched_at"]).alias("fetched_at"),
            pl.lit(meta["sha256"]).alias("raw_sha256"),
        )
        tidy.write_parquet(out_dir / f"{pid}_{name}.parquet")
        frames[pid] = tidy
        meta_rows.append(
            {
                "product_id": str(pid),
                "name": name,
                "rows_all_geo": df.height,
                "rows_kept": tidy.height,
                "fetched_at": meta["fetched_at"],
                "raw_sha256": meta["sha256"],
                "dimensions": ", ".join(statcan.dimension_columns(df)),
            }
        )
    pl.DataFrame(meta_rows).write_parquet(out_dir / "tables.parquet")
    return frames


def validate(frames: dict[int, pl.DataFrame]) -> None:
    problems = []
    for pid, df in frames.items():
        if df.height == 0:
            problems.append(f"{pid}: no rows")
            continue
        geos = set(df["geo"].unique().to_list())
        if "Ontario" not in geos:
            problems.append(f"{pid}: no Ontario rows (geos={geos})")
        share_null = df["value"].null_count() / df.height
        if share_null > 0.9:
            problems.append(f"{pid}: {share_null:.0%} of VALUE null")
        years = df["ref_date"].str.extract(r"^(\d{4})").cast(pl.Int32, strict=False)
        lo, hi = years.min(), years.max()
        if lo is None or lo < 1990 or hi is None or hi > 2030:
            problems.append(f"{pid}: ref_date range {lo}..{hi} implausible")
        log.info("S1 %s: %d rows, %s..%s, %.0f%% null", pid, df.height, lo, hi, 100 * share_null)
    if 35100029 in frames:
        # Headline cell must be plausible: Ontario, Total Criminal Code, all ages/sexes, total
        # cases, Median. (Sparse cells such as companies legitimately show medians > 10 years.)
        head = frames[35100029].filter(
            (pl.col("geo") == "Ontario")
            & (pl.col("offences") == "Total Criminal Code")
            & pl.col("age of accused").str.starts_with("Total")
            & pl.col("sex of accused").str.starts_with("Total")
            & (pl.col("type of case") == "Total cases")
            & (pl.col("statistics") == "Median")
            & pl.col("value").is_not_null()
        )
        if head.height == 0:
            problems.append("35100029: headline Ontario median series missing")
        elif head["value"].min() < 30 or head["value"].max() > 1000:
            problems.append(
                f"35100029: headline Ontario median out of range "
                f"{head['value'].min()}..{head['value'].max()} days"
            )
        else:
            latest = head.sort("ref_date").tail(1)
            log.info(
                "S1 headline: Ontario median days to disposition %s = %.0f",
                latest["ref_date"][0],
                latest["value"][0],
            )
    if problems:
        raise ValueError("S1 validation failed:\n  " + "\n  ".join(problems))
