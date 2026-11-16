"""Stock-flow (Little's law) estimates of time in system from published court tables.

W = L / λ, where L is the average stock of pending proceedings over a period and λ the flow rate
(per day). We report two versions: λ = dispositions / days (throughput view) and λ = commenced /
days (arrival view). Under stationarity they coincide; their ratio is a diagnostic of a growing or
shrinking backlog and is reported alongside. Everything here is a **steady-state approximation**
of mean time in system, not a distribution, and carries that label downstream.

Inputs are long tables with columns court, period_start, period_end, subject_matter, commenced,
dispositions, pending (S8 FC/FCA year-to-date pages; S7 OCJ annual offence-based tables).
Year-to-date flows are differenced to per-period flows first (``ytd_to_period``).

Preconditions (``identity_check``): pending_t ≈ pending_{t-1} + commenced − dispositions within
a tolerance; violations are returned, not silenced, and the caller decides whether to publish.
"""

from __future__ import annotations

from datetime import date

import polars as pl


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days + 1


def ytd_to_period(df: pl.DataFrame) -> pl.DataFrame:
    """Convert year-to-date flows (Jan 1 → quarter end) to per-quarter flows.

    Rows are keyed by (court, subject_matter, year = period_start[:4]); within a year the
    quarterly flow is the YTD value minus the previous quarter's YTD value. Pending is a stock and
    is kept as published. Adds ``q_start`` (previous period_end + 1 day or Jan 1)."""
    d = df.with_columns(pl.col("period_start").str.slice(0, 4).alias("_year")).sort(
        ["court", "subject_matter", "period_end"]
    )
    grp = ["court", "subject_matter", "_year"]
    d = d.with_columns(
        (pl.col("commenced") - pl.col("commenced").shift(1).over(grp).fill_null(0)).alias(
            "commenced_q"
        ),
        (pl.col("dispositions") - pl.col("dispositions").shift(1).over(grp).fill_null(0)).alias(
            "dispositions_q"
        ),
        pl.col("period_end")
        .shift(1)
        .over(grp)
        .str.to_date()
        .dt.offset_by("1d")
        .cast(pl.Utf8)
        .fill_null(pl.col("period_start"))
        .alias("q_start"),
    )
    return d.drop("_year")


def identity_check(df: pl.DataFrame, *, tol: int = 5, rel_tol: float = 0.01) -> pl.DataFrame:
    """For consecutive periods of each (court, subject_matter), compare the published pending
    stock with the stock implied by the previous stock plus net flow. Returns one row per
    transition with ``gap``, ``rel_gap`` and ``ok`` (|gap| <= max(tol, rel_tol * pending)).
    Small gaps are expected (reopened and transferred files); large ones mark a break in the
    published series and the adjacent Little's-law values should not be used.
    A transition spanning a missing quarter is flagged with ``spans_gap``."""
    d = df.sort(["court", "subject_matter", "period_end"])
    grp = ["court", "subject_matter"]
    d = d.with_columns(
        pl.col("pending").shift(1).over(grp).alias("pending_prev"),
        pl.col("period_end").shift(1).over(grp).alias("prev_end"),
    ).with_columns(
        (
            pl.col("pending_prev")
            + pl.col("commenced_q")
            - pl.col("dispositions_q")
            - pl.col("pending")
        ).alias("gap")
    )
    d = d.filter(pl.col("pending_prev").is_not_null())
    d = d.with_columns(
        (pl.col("gap") / pl.col("pending")).alias("rel_gap"),
        (
            (pl.col("period_end").str.to_date() - pl.col("prev_end").str.to_date()).dt.total_days()
            > 100
        ).alias("spans_gap"),
    )
    thresh = pl.max_horizontal(pl.lit(float(tol)), pl.col("pending") * rel_tol)
    return d.with_columns((pl.col("gap").abs() <= thresh).alias("ok")).select(
        [
            "court",
            "subject_matter",
            "prev_end",
            "period_end",
            "pending_prev",
            "commenced_q",
            "dispositions_q",
            "pending",
            "gap",
            "rel_gap",
            "spans_gap",
            "ok",
        ]
    )


def littles_law(df: pl.DataFrame) -> pl.DataFrame:
    """Mean time in system (days) per row from per-period flows and the average stock.

    L = mean(pending_prev, pending) when the previous stock is known, else pending.
    W_disp = L / (dispositions_q / days); W_arr = L / (commenced_q / days).
    ``backlog_ratio`` = commenced_q / dispositions_q (>1: backlog growing)."""
    d = df.sort(["court", "subject_matter", "period_end"])
    grp = ["court", "subject_matter"]
    d = d.with_columns(pl.col("pending").shift(1).over(grp).alias("pending_prev"))
    d = d.with_columns(
        pl.struct(["q_start", "period_end"])
        .map_elements(lambda s: _days(s["q_start"], s["period_end"]), return_dtype=pl.Int64)
        .alias("days"),
        pl.when(pl.col("pending_prev").is_not_null())
        .then((pl.col("pending_prev") + pl.col("pending")) / 2)
        .otherwise(pl.col("pending"))
        .alias("L"),
    )
    d = d.with_columns(
        pl.when(pl.col("dispositions_q") > 0)
        .then(pl.col("L") / (pl.col("dispositions_q") / pl.col("days")))
        .otherwise(None)
        .alias("W_days_disposal_rate"),
        pl.when(pl.col("commenced_q") > 0)
        .then(pl.col("L") / (pl.col("commenced_q") / pl.col("days")))
        .otherwise(None)
        .alias("W_days_arrival_rate"),
        pl.when(pl.col("dispositions_q") > 0)
        .then(pl.col("commenced_q") / pl.col("dispositions_q"))
        .otherwise(None)
        .alias("backlog_ratio"),
    )
    return d.with_columns(
        pl.lit("steady-state approximation (Little's law); mean, not median").alias(
            "bias_statement"
        )
    )


def annual_rollup(d: pl.DataFrame) -> pl.DataFrame:
    """Sum quarterly flows to years and recompute W on annual totals (less noisy)."""
    y = (
        d.with_columns(pl.col("period_end").str.slice(0, 4).alias("year"))
        .group_by(["court", "subject_matter", "year"])
        .agg(
            pl.col("commenced_q").sum().alias("commenced"),
            pl.col("dispositions_q").sum().alias("dispositions"),
            pl.col("pending").last().alias("pending_end"),
            pl.col("pending_prev").first().alias("pending_start"),
            pl.col("days").sum().alias("days"),
            pl.len().alias("n_periods"),
            *(
                [pl.col("identity_ok").fill_null(True).all().alias("identity_ok")]
                if "identity_ok" in d.columns
                else [pl.lit(True).alias("identity_ok")]
            ),
        )
        .sort(["court", "subject_matter", "year"])
    )
    y = y.with_columns(
        pl.when(pl.col("pending_start").is_not_null())
        .then((pl.col("pending_start") + pl.col("pending_end")) / 2)
        .otherwise(pl.col("pending_end"))
        .alias("L")
    )
    return y.with_columns(
        pl.when(pl.col("dispositions") > 0)
        .then(pl.col("L") / (pl.col("dispositions") / pl.col("days")))
        .otherwise(None)
        .alias("W_days_disposal_rate"),
        pl.when(pl.col("commenced") > 0)
        .then(pl.col("L") / (pl.col("commenced") / pl.col("days")))
        .otherwise(None)
        .alias("W_days_arrival_rate"),
        pl.when(pl.col("dispositions") > 0)
        .then(pl.col("commenced") / pl.col("dispositions"))
        .otherwise(None)
        .alias("backlog_ratio"),
        pl.lit("steady-state approximation (Little's law); mean, not median").alias(
            "bias_statement"
        ),
        # publishable only with a full year of quarters that all reconcile (docs/methods.md E2)
        ((pl.col("n_periods") == 4) & pl.col("identity_ok")).alias("publishable"),
    )
