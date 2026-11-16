"""Court × month resource panel: judicial complement and vacancies (S9) aligned to a monthly grid,
with federal filings/pending (S8) for the FC, FCA and TCC.

S9 snapshots are irregular (one per Wayback capture, sometimes months apart). We build a monthly
grid and carry each snapshot forward until the next one, recording ``snapshot_as_of`` and
``months_since_snapshot`` so stale values are visible. Ontario courts: Court of Appeal, Superior
Court of Justice, Family Court (as named on the FJA page); federal: Supreme Court, Federal Court
of Appeal, Federal Court, Tax Court of Canada.
"""

from __future__ import annotations

import polars as pl

COURT_MAP = {
    ("Canada", "Supreme Court"): "SCC",
    ("Canada", "Federal Court of Appeal"): "FCA",
    ("Canada", "Federal Court"): "FC",
    ("Canada", "Tax Court of Canada"): "TCC",
    ("Ontario", "Court of Appeal"): "ONCA",
    ("Ontario", "Superior Court of Justice"): "ONSC",
    ("Ontario", "Family Court"): "ONSC-Family",
}


def monthly_vacancy_panel(snapshots: pl.DataFrame) -> pl.DataFrame:
    """From S9 judges_snapshots (as_of, jurisdiction, court, in_office, supernumerary, grand_total,
    women, vacancies) to a court × month panel with carry-forward."""
    s = (
        snapshots.filter(pl.col("as_of").is_not_null())
        .with_columns(
            pl.struct(["jurisdiction", "court"])
            .map_elements(
                lambda r: COURT_MAP.get((r["jurisdiction"], r["court"])), return_dtype=pl.Utf8
            )
            .alias("court_code"),
            pl.col("as_of").str.to_date().alias("as_of_date"),
        )
        .filter(pl.col("court_code").is_not_null())
        .with_columns(pl.col("as_of_date").dt.truncate("1mo").alias("month"))
        # several snapshots in one month: keep the latest
        .sort(["court_code", "as_of_date"])
        .unique(subset=["court_code", "month"], keep="last")
    )
    frames = []
    for (code,), sub in s.group_by(["court_code"], maintain_order=True):
        sub = sub.sort("month")
        grid = pl.DataFrame(
            {
                "month": pl.date_range(
                    sub["month"].min(), sub["month"].max(), interval="1mo", eager=True
                )
            }
        ).with_columns(pl.lit(code).alias("court_code"))
        joined = grid.join(
            sub.select(
                [
                    "court_code",
                    "month",
                    "as_of",
                    "in_office",
                    "supernumerary",
                    "grand_total",
                    "women",
                    "vacancies",
                ]
            ),
            on=["court_code", "month"],
            how="left",
        ).sort("month")
        filled = joined.with_columns(
            [
                pl.col(c).fill_null(strategy="forward").alias(c)
                for c in (
                    "as_of",
                    "in_office",
                    "supernumerary",
                    "grand_total",
                    "women",
                    "vacancies",
                )
            ]
        )
        filled = filled.with_columns(
            (
                (pl.col("month").dt.year() - pl.col("as_of").str.to_date().dt.year()) * 12
                + (pl.col("month").dt.month() - pl.col("as_of").str.to_date().dt.month())
            ).alias("months_since_snapshot"),
            (pl.col("vacancies") / (pl.col("in_office") + pl.col("vacancies"))).alias(
                "vacancy_rate"
            ),
            pl.col("as_of").alias("snapshot_as_of"),
        ).drop("as_of")
        frames.append(filled)
    out = pl.concat(frames) if frames else pl.DataFrame()
    return out.with_columns(
        pl.lit(
            "FJA snapshots carried forward between irregular Wayback captures; judges counted as "
            "persons, not FTE; supernumerary judges carry reduced loads"
        ).alias("bias_statement")
    )


def federal_quarterly_panel(
    vacancy_panel: pl.DataFrame, fc_quarterly: pl.DataFrame
) -> pl.DataFrame:
    """Join the FC total quarterly flows (from stock_flow.littles_law output filtered to the total
    row) to the vacancy panel averaged over each quarter."""
    v = (
        vacancy_panel.filter(pl.col("court_code") == "FC")
        .with_columns(pl.col("month").dt.truncate("1q").alias("quarter"))
        .group_by("quarter")
        .agg(
            pl.col("in_office").mean().alias("judges_in_office_avg"),
            pl.col("vacancies").mean().alias("vacancies_avg"),
            pl.col("vacancy_rate").mean().alias("vacancy_rate_avg"),
            pl.col("months_since_snapshot").max().alias("max_months_since_snapshot"),
        )
    )
    f = fc_quarterly.with_columns(
        pl.col("period_end").str.to_date().dt.truncate("1q").alias("quarter")
    )
    return f.join(v, on="quarter", how="left").sort("period_end")
