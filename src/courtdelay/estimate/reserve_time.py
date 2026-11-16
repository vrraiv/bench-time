"""Reserve time (hearing → decision) summaries from S3 decision metadata.

Population: published written decisions with a parsed hearing date, ``hearing_mode`` not
"written" and ``hearing_after_decision`` false. Durations are decision date minus the last
hearing day. Per court × decision year: n, median, p75, p90, share over 6 months, with bootstrap
percentile CIs. Bias statement attached to every row.
"""

from __future__ import annotations

import numpy as np
import polars as pl

BIAS = (
    "published written decisions only (oral and unreported decisions absent); hearing date parsed "
    "from unofficial text; last hearing day used for multi-day hearings"
)


def _boot_quantile(x: np.ndarray, q: float, rng, n_boot: int) -> tuple[float, float]:
    n = len(x)
    draws = np.empty(n_boot)
    for i in range(n_boot):
        draws[i] = np.quantile(x[rng.integers(0, n, n)], q)
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def reserve_by_court_year(
    meta: pl.DataFrame, *, min_n: int = 20, n_boot: int = 300, seed: int = 20261115
) -> pl.DataFrame:
    d = (
        meta.filter(
            pl.col("reserve_days").is_not_null()
            & (pl.col("hearing_mode").fill_null("unknown") != "written")
            & ~pl.col("hearing_after_decision").fill_null(False)
        )
        .with_columns(pl.col("decision_date").dt.year().alias("year"))
        .select(["court", "year", "reserve_days"])
    )
    rng = np.random.default_rng(seed)
    rows = []
    for (court, year), sub in d.group_by(["court", "year"], maintain_order=True):
        x = sub["reserve_days"].to_numpy().astype(float)
        if len(x) < min_n:
            continue
        row = {
            "court": court,
            "year": int(year),
            "n": int(len(x)),
            "mean_days": float(x.mean()),
            "share_over_180d": float((x > 180).mean()),
        }
        for q, name in ((0.5, "p50"), (0.75, "p75"), (0.9, "p90")):
            row[f"{name}_days"] = float(np.quantile(x, q))
            row[f"{name}_lo"], row[f"{name}_hi"] = _boot_quantile(x, q, rng, n_boot)
        row["bias_statement"] = BIAS
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None).sort(["court", "year"])


def written_share_by_court_year(meta: pl.DataFrame) -> pl.DataFrame:
    """Share of decisions disposed of in writing (no hearing) and share with a parsed hearing
    date, per court × year: the coverage statement that accompanies the reserve-time table."""
    return (
        meta.with_columns(pl.col("decision_date").dt.year().alias("year"))
        .group_by(["court", "year"])
        .agg(
            pl.len().alias("n_decisions"),
            (pl.col("hearing_mode") == "written").mean().alias("written_share"),
            pl.col("hearing_date").is_not_null().mean().alias("hearing_date_parsed_share"),
            pl.col("hearing_after_decision").fill_null(False).mean().alias("flagged_share"),
        )
        .sort(["court", "year"])
    )
