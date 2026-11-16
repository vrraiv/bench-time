"""``courtdelay build``: turn processed source parquet into the small derived tables the site uses.

Everything written here is an aggregate (no names, no texts). Each table carries a
``bias_statement`` column or an accompanying note, plus vintage columns where available.
Outputs go to data/processed/derived/ (parquet) and site/data/ (CSV, gitignored until M2 decides
what is published).
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from courtdelay.common import paths
from courtdelay.estimate import panel, reserve_time, stock_flow, survival

log = logging.getLogger(__name__)


def _out_dirs() -> tuple[Path, Path]:
    derived = paths.processed_dir() / "derived"
    derived.mkdir(exist_ok=True)
    site = paths.REPO_ROOT / "site" / "data"
    site.mkdir(parents=True, exist_ok=True)
    return derived, site


def _write(df: pl.DataFrame, name: str, derived: Path, site: Path) -> None:
    df.write_parquet(derived / f"{name}.parquet")
    df.write_csv(site / f"{name}.csv")
    log.info("build: %s (%d rows)", name, df.height)


def build_s1(derived: Path, site: Path) -> None:
    p = paths.processed_dir() / "s1" / "35100029_adult_median_elapsed_time.parquet"
    if not p.exists():
        return
    df = pl.read_parquet(p)
    head = (
        df.filter(
            pl.col("age of accused").str.starts_with("Total")
            & pl.col("sex of accused").str.starts_with("Total")
            & (pl.col("type of case") == "Total cases")
            & pl.col("value").is_not_null()
        )
        .pivot(on="statistics", index=["ref_date", "geo", "offences", "fetched_at"], values="value")
        .rename({"Median": "median_days", "Count": "n_cases"})
        .with_columns(
            pl.lit(
                "StatCan ICCS completed adult cases; first appearance to final decision; cannot "
                "attribute delay to Crown, defence or court"
            ).alias("bias_statement")
        )
        .sort(["geo", "offences", "ref_date"])
    )
    _write(head, "s1_median_days_by_offence", derived, site)


def build_s5(derived: Path, site: Path) -> None:
    p = paths.processed_dir() / "s5" / "scc_time_lapses.parquet"
    if p.exists():
        df = pl.read_parquet(p).with_columns(
            pl.lit("court-published annual averages, counted by file number").alias(
                "bias_statement"
            )
        )
        _write(df, "s5_scc_time_lapses", derived, site)


def build_s8(derived: Path, site: Path) -> dict[str, pl.DataFrame]:
    out = {}
    for court, fname, total_rx in (
        ("FC", "fc_activity.parquet", r"(?i)^(grand total|total federal court|total)$"),
        ("FCA", "fca_activity.parquet", r"(?i)^total$"),
    ):
        p = paths.processed_dir() / "s8" / fname
        if not p.exists():
            continue
        df = pl.read_parquet(p).filter(pl.col("subject_matter").str.contains(total_rx))
        df = df.with_columns(pl.lit("TOTAL").alias("subject_matter"))
        q = stock_flow.ytd_to_period(df)
        chk = stock_flow.identity_check(q)
        bad = chk.filter(~pl.col("ok"))
        log.info(
            "build S8 %s: %d transitions, %d violate the stock-flow identity (tol 5)",
            court,
            chk.height,
            bad.height,
        )
        _write(chk, f"s8_{court.lower()}_identity_check", derived, site)
        w = stock_flow.littles_law(q).join(
            chk.select(["court", "subject_matter", "period_end", "ok", "spans_gap"]).rename(
                {"ok": "identity_ok"}
            ),
            on=["court", "subject_matter", "period_end"],
            how="left",
        )
        _write(w, f"s8_{court.lower()}_quarterly_littles_law", derived, site)
        y = stock_flow.annual_rollup(w)
        _write(y, f"s8_{court.lower()}_annual_littles_law", derived, site)
        out[court] = w
    return out


def build_s9(derived: Path, site: Path) -> pl.DataFrame | None:
    p = paths.processed_dir() / "s9" / "judges_snapshots.parquet"
    if not p.exists():
        return None
    v = panel.monthly_vacancy_panel(pl.read_parquet(p))
    _write(v, "s9_vacancy_panel_monthly", derived, site)
    return v


def build_s3(derived: Path, site: Path) -> None:
    p = paths.processed_dir() / "s3" / "decisions_meta.parquet"
    if not p.exists():
        return
    meta = pl.read_parquet(p)
    _write(reserve_time.reserve_by_court_year(meta), "s3_reserve_time_by_court_year", derived, site)
    _write(
        reserve_time.written_share_by_court_year(meta), "s3_coverage_by_court_year", derived, site
    )


def build_s4(derived: Path, site: Path) -> None:
    p = paths.processed_dir() / "s4" / "dockets.parquet"
    if not p.exists():
        return
    d = pl.read_parquet(p).filter(pl.col("filing_year") >= 1997)
    tables = []
    for start, event, label in (
        ("date_filed", "leave_decision_date", "filing -> leave decision"),
        ("date_filed", "final_disposition_date", "filing -> final disposition"),
        ("leave_decision_date", "hearing_date", "leave granted -> hearing"),
        ("hearing_date", "judgment_date", "hearing -> judgment"),
    ):
        sub = d if start == "date_filed" else d.filter(pl.col("leave_result") == "granted")
        t = survival.cohort_table(
            sub,
            cohort_col="filing_year",
            start_col=start,
            event_col=event,
            censor_col="scraped",
            n_boot=200,
            label=label,
        )
        if t.height:
            tables.append(t)
    if tables:
        _write(
            pl.concat(tables, how="diagonal_relaxed"),
            "s4_fc_immigration_km_by_cohort",
            derived,
            site,
        )
    leave = (
        d.group_by("filing_year")
        .agg(
            pl.len().alias("n_dockets"),
            pl.col("leave_decision_date").is_not_null().mean().alias("leave_decided_share"),
            (pl.col("leave_result") == "granted").sum().alias("leave_granted"),
            (pl.col("leave_result") == "dismissed").sum().alias("leave_dismissed"),
            pl.col("discontinuance_date").is_not_null().mean().alias("discontinued_share"),
        )
        .with_columns(
            (pl.col("leave_granted") / (pl.col("leave_granted") + pl.col("leave_dismissed"))).alias(
                "grant_rate"
            ),
            pl.lit("FC immigration dockets as of Nov 2022; regex-classified entries").alias(
                "bias_statement"
            ),
        )
        .sort("filing_year")
    )
    _write(leave, "s4_fc_immigration_leave_by_cohort", derived, site)


def build_s7(derived: Path, site: Path) -> None:
    p = paths.processed_dir() / "s7" / "offence_based.parquet"
    if p.exists():
        ob = pl.read_parquet(p)
        prov = (
            ob.filter((pl.col("unit_type") == "province") & (pl.col("offence_type") == "TOTAL"))
            .select(
                [
                    "period_start",
                    "period_end",
                    "case_type",
                    "offence_group",
                    "received",
                    "disposed",
                    "avg_days",
                    "avg_appearances",
                    "pending",
                ]
            )
            .with_columns(
                pl.lit(
                    "OCJ/MAG counts; calendar years to 2019, fiscal years from 2020 "
                    "(definition break); averages exclude bench warrants"
                ).alias("bias_statement")
            )
            .sort(["case_type", "offence_group", "period_start"])
        )
        _write(prov, "s7_ocj_provincial_by_offence_group", derived, site)
        ch = (
            ob.filter(
                (pl.col("unit_type") == "courthouse")
                & (pl.col("offence_type") == "TOTAL")
                & (pl.col("case_type") == "all")
            )
            .group_by(["unit_key", "period_start", "period_end"])
            .agg(
                pl.col("received").sum(),
                pl.col("disposed").sum(),
                pl.col("pending").sum(),
                # disposal-weighted average days across offence groups
                ((pl.col("avg_days") * pl.col("disposed")).sum() / pl.col("disposed").sum()).alias(
                    "avg_days_weighted"
                ),
            )
            .sort(["unit_key", "period_start"])
        )
        _write(ch, "s7_ocj_courthouse_panel", derived, site)
    p = paths.processed_dir() / "s7" / "disposition_rate_monthly.parquet"
    if p.exists():
        dr = (
            pl.read_parquet(p)
            .filter(pl.col("unit_type") == "province")
            .sort(["case_type", "month"])
        )
        _write(dr, "s7_ocj_provincial_disposition_monthly", derived, site)


def build_all() -> None:
    derived, site = _out_dirs()
    build_s1(derived, site)
    build_s5(derived, site)
    fed = build_s8(derived, site)
    v = build_s9(derived, site)
    if v is not None and "FC" in fed:
        _write(
            panel.federal_quarterly_panel(v, fed["FC"]), "s9_s8_fc_quarterly_panel", derived, site
        )
    build_s3(derived, site)
    build_s4(derived, site)
    build_s7(derived, site)
