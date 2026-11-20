"""S2: Statistics Canada Civil Court Survey tables via WDS (counts, and elapsed-time bands).

  35-10-0112-01  Civil court cases, by level of court and type of case (counts)
  35-10-0114-01  Civil court active cases, by level of court and type of action
  35-10-0116-01  Active civil court cases, by elapsed time from initiation to first disposition
  35-10-0117-01  Inactive civil court cases, by fiscal years since initiation

Same mechanics as S1; see courtdelay.common.statcan. Ontario + Canada rows kept.
"""

from __future__ import annotations

import logging

import polars as pl

from courtdelay.common import paths, statcan
from courtdelay.common.http import Client
from courtdelay.sources import s1_statcan_iccs as s1

log = logging.getLogger(__name__)

SOURCE = "s2_statcan_civil"
TABLES: dict[int, str] = {
    35100112: "civil_cases_by_type",
    35100114: "civil_active_cases_by_type",
    # timing, by level of court (added 2026-11-19): the only series that separates the
    # Superior Court of Justice in civil and family matters
    35100116: "civil_active_cases_by_elapsed_time",
    35100117: "civil_inactive_cases_by_years_since_initiation",
}


def fetch(client: Client, *, vintage: str = "") -> dict[int, dict]:
    out = {}
    for pid in TABLES:
        meta = statcan.cube_metadata(client, pid, source=SOURCE, vintage=vintage)
        resp = statcan.fetch_full_table(client, pid, source=SOURCE, vintage=vintage)
        log.info(
            "S2 %s %s: %s..%s released %s",
            pid,
            meta.title_en,
            meta.start,
            meta.end,
            meta.release_time,
        )
        out[pid] = {"meta": meta, "zip_path": resp.path}
    return out


def parse(client: Client | None = None) -> dict[int, pl.DataFrame]:
    frames = {}
    out_dir = paths.processed_dir() / "s2"
    out_dir.mkdir(exist_ok=True)
    for pid, name in TABLES.items():
        zip_path, meta = statcan.latest_cached_zip(SOURCE, pid)
        df = statcan.read_table_zip(zip_path.read_bytes(), pid)
        tidy = statcan.tidy(df, pid, geos=s1.GEOS).with_columns(
            pl.lit(meta["fetched_at"]).alias("fetched_at"),
            pl.lit(meta["sha256"]).alias("raw_sha256"),
        )
        tidy.write_parquet(out_dir / f"{pid}_{name}.parquet")
        frames[pid] = tidy
    return frames


def validate(frames: dict[int, pl.DataFrame]) -> None:
    problems = []
    for pid, df in frames.items():
        if df.height == 0:
            problems.append(f"{pid}: no rows")
        elif "Ontario" not in set(df["geo"].unique().to_list()):
            problems.append(f"{pid}: no Ontario rows")
        else:
            log.info("S2 %s: %d rows", pid, df.height)
    if problems:
        raise ValueError("S2 validation failed:\n  " + "\n  ".join(problems))
