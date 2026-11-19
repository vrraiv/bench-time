"""``courtdelay build``: turn processed source parquet into the small derived tables the site uses.

Everything written here is an aggregate (no names, no texts). Each table carries a
``bias_statement`` column or an accompanying note, plus vintage columns where available.
Outputs go to data/processed/derived/ (parquet) and site/src/data/ (CSV, gitignored until it is
decided what is published).
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from courtdelay.common import paths
from courtdelay.estimate import judges, linkage, panel, reserve_time, stock_flow, survival

log = logging.getLogger(__name__)


def _out_dirs() -> tuple[Path, Path]:
    derived = paths.processed_dir() / "derived"
    derived.mkdir(exist_ok=True)
    site = paths.REPO_ROOT / "site" / "src" / "data"
    site.mkdir(parents=True, exist_ok=True)
    return derived, site


def _write(df: pl.DataFrame, name: str, derived: Path, site: Path, *, publish: bool = True) -> None:
    """``publish=False`` keeps a table out of site/src/data (committed) until the owner decides."""
    df.write_parquet(derived / f"{name}.parquet")
    if publish:
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


def build_s6(derived: Path, site: Path) -> None:
    p = paths.processed_dir() / "s6" / "onca_tables.parquet"
    if p.exists():
        df = pl.read_parquet(p).with_columns(
            pl.lit(
                "ONCA-published; timelines are averages by filing year for appeals heard on the "
                "merits; counts by calendar year"
            ).alias("bias_statement")
        )
        _write(df, "s6_onca_annual_report_tables", derived, site)


def build_s8(derived: Path, site: Path) -> dict[str, pl.DataFrame]:
    out = {}
    for court, fname, total_rx in (
        (
            "FC",
            "fc_activity.parquet",
            r"(?i)^(grand total|total federal court|total trial division|total)$",
        ),
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
            "build S8 %s: %d transitions, %d violate the stock-flow identity (>1%% of stock)",
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
            competing_col=None if event == "final_disposition_date" else "final_disposition_date",
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


S12_BIAS = (
    "Tax Court of Canada docket census (every file number listed by the court's search), "
    "Kaplan-Meier, right-censored at the scrape date; end of file = first of file closed, "
    "judgment, discontinuance or a bare outcome entry; entry labels regex-classified; "
    "PROVISIONAL pending practitioner review of entry labels"
)


def build_s12(derived: Path, site: Path) -> None:
    """Tax Court cohort tables. Not written to site/src/data: provisional, and publishing
    aggregates from a Tier 2 docket source is an owner decision."""
    p = paths.processed_dir() / "s12" / "dockets.parquet"
    if not p.exists():
        return
    d = pl.read_parquet(p).with_columns(
        pl.col("scraped").str.to_date(strict=False).alias("scraped_date"),
        (pl.col("docket_year").cast(pl.Utf8) + "|" + pl.col("procedure_group")).alias("cohort"),
    )
    km = survival.cohort_table(
        d,
        cohort_col="cohort",
        start_col="date_filed",
        event_col="final_disposition_date",
        censor_col="scraped_date",
        n_boot=200,
        label="filing -> final disposition",
        min_at_risk=20,
        bias_statement=S12_BIAS,
    )
    if km.height:
        km = (
            km.with_columns(
                pl.col("cohort").str.split("|").list.get(0).cast(pl.Int32).alias("docket_year"),
                pl.col("cohort").str.split("|").list.get(1).alias("procedure_group"),
            )
            .drop("cohort")
            .sort(["procedure_group", "docket_year"])
        )
        km = km.select(["docket_year", "procedure_group", *km.columns[:-2]])
        km = km.with_columns(pl.lit(d["scraped_date"].max()).alias("vintage"))
        _write(km, "s12_tcc_km_by_cohort", derived, site, publish=False)
    closed = pl.col("final_disposition_date").is_not_null()
    heard = pl.col("first_hearing_date").is_not_null()
    mix = (
        d.group_by(["docket_year", "procedure_group"])
        .agg(
            pl.len().alias("n_files"),
            closed.mean().alias("closed_share"),
            heard.mean().alias("hearing_held_share"),
            (closed & ~heard).mean().alias("closed_without_hearing_share"),
            pl.col("discontinuance_date").is_not_null().mean().alias("discontinued_share"),
            pl.col("abeyance_date").is_not_null().mean().alias("abeyance_share"),
            (pl.col("n_adjournment_requests") > 0).mean().alias("adjournment_requested_share"),
            (pl.col("n_case_mgmt_conferences") > 0).mean().alias("case_managed_share"),
            pl.col("scraped_date").max().alias("vintage"),
        )
        .filter(pl.col("n_files") >= 30)
        .with_columns(pl.lit(S12_BIAS.replace("Kaplan-Meier, ", "")).alias("bias_statement"))
        .sort(["procedure_group", "docket_year"])
    )
    _write(mix, "s12_tcc_file_outcomes_by_cohort", derived, site, publish=False)
    # wait for a hearing: most files end without one, so this is a cumulative incidence with
    # "ended without a hearing" as the competing outcome, not a Kaplan-Meier median
    wait = survival.cif_table(
        d.filter(pl.col("procedure_group").is_in(["General", "Informal", "EI", "CPP"])),
        cohort_col="cohort",
        start_col="date_filed",
        event_col="first_hearing_date",
        competing_col="final_disposition_date",
        censor_col="scraped_date",
        label="filing -> first hearing entry (competing: file ended without one)",
        bias_statement=S12_BIAS
        + " The first 'Minutes of Hearing' entry is used; it is sometimes a motion or status "
        "hearing, not the trial (practitioner review pending).",
    )
    if wait.height:
        wait = (
            wait.with_columns(
                pl.col("cohort").str.split("|").list.get(0).cast(pl.Int32).alias("docket_year"),
                pl.col("cohort").str.split("|").list.get(1).alias("procedure_group"),
                pl.lit(d["scraped_date"].max()).alias("vintage"),
            )
            .drop("cohort")
            .sort(["procedure_group", "docket_year"])
        )
        _write(wait, "s12_tcc_hearing_wait_by_cohort", derived, site, publish=False)


S10_BIAS = (
    "Census of court files from the court's public file search (FCA from 2010, Federal Court "
    "non-immigration from 2018). End of file = the Registry's final-decision marker, else a "
    "discontinuance; files with neither are treated as still open, which overstates open files "
    "by a few percent (the court's own disposition counts are 1-6% higher per year). Tribunal "
    "decisions and certificates registered for enforcement are excluded. Kaplan-Meier, censored "
    "at the scrape date. A cluster of 2018 actions against the Crown with no entries since 2020 "
    "is counted as open."
)


def s10_proceeding_group() -> pl.Expr:
    nat = pl.col("nature").fill_null("")
    fca = (
        pl.when(nat.str.starts_with("Appeal (S.27 - Final)"))
        .then(pl.lit("FCA: appeal from Federal Court (final)"))
        .when(nat.str.starts_with("Appeal (S.27 - Interloc"))
        .then(pl.lit("FCA: appeal from Federal Court (interlocutory)"))
        .when(nat.str.contains("Tax Court"))
        .then(pl.lit("FCA: appeal from Tax Court"))
        .when(nat.str.starts_with("S.28"))
        .then(pl.lit("FCA: judicial review (s. 28)"))
        .otherwise(pl.lit("FCA: other"))
    )
    fc = (
        pl.when(nat.str.contains("Judicial Review"))
        .then(pl.lit("FC: judicial review"))
        .when(nat.str.contains("Citizenship"))
        .then(pl.lit("FC: citizenship"))
        .when(pl.col("proceeding_class").is_in(["Ordinary", "Simplified"]))
        .then(pl.lit("FC: actions"))
        .otherwise(pl.lit("FC: other applications"))
    )
    return pl.when(pl.col("prefix") == "A").then(fca).otherwise(fc).alias("proceeding_group")


def build_s10(derived: Path, site: Path) -> None:
    """FCA and Federal Court (non-immigration) cohort tables from the docket census. Not written
    to site/src/data until the owner decides on publishing aggregates from the docket sites."""
    p = paths.processed_dir() / "s10" / "dockets.parquet"
    if not p.exists():
        return
    d = (
        pl.read_parquet(p)
        .filter(pl.col("prefix").is_in(["A", "T"]) & ~pl.col("is_registration"))
        .with_columns(
            pl.col("scraped").str.to_date(strict=False).alias("scraped_date"),
            s10_proceeding_group(),
        )
    )
    court = pl.when(pl.col("prefix") == "A").then(pl.lit("FCA: all")).otherwise(pl.lit("FC: all"))
    both = pl.concat([d, d.with_columns(court.alias("proceeding_group"))]).with_columns(
        (pl.col("docket_year").cast(pl.Utf8) + "|" + pl.col("proceeding_group")).alias("cohort")
    )
    km = survival.cohort_table(
        both,
        cohort_col="cohort",
        start_col="date_filed",
        event_col="final_disposition_date",
        censor_col="scraped_date",
        n_boot=200,
        label="filing -> end of file",
        min_at_risk=20,
        bias_statement=S10_BIAS,
    )
    if km.height:
        km = (
            km.with_columns(
                pl.col("cohort").str.split("|").list.get(0).cast(pl.Int32).alias("docket_year"),
                pl.col("cohort").str.split("|").list.get(1).alias("proceeding_group"),
            )
            .drop("cohort")
            .sort(["proceeding_group", "docket_year"])
        )
        km = km.select(["docket_year", "proceeding_group", *km.columns[:-2]])
        km = km.with_columns(pl.lit(d["scraped_date"].max()).alias("vintage"))
        _write(km, "s10_fc_fca_km_by_cohort", derived, site, publish=False)
    ended = pl.col("final_disposition_date").is_not_null()
    mix = (
        both.group_by(["docket_year", "proceeding_group"])
        .agg(
            pl.len().alias("n_files"),
            ended.mean().alias("ended_share"),
            (pl.col("final_disposition_type") == "discontinuance")
            .fill_null(False)
            .mean()
            .alias("discontinued_share"),
            (pl.col("final_disposition_source") == "marker")
            .fill_null(False)
            .mean()
            .alias("ended_by_decision_share"),
        )
        .filter(pl.col("n_files") >= 30)
        .sort(["proceeding_group", "docket_year"])
        .with_columns(
            pl.lit(d["scraped_date"].max()).alias("vintage"),
            pl.lit(S10_BIAS).alias("bias_statement"),
        )
    )
    _write(mix, "s10_fc_fca_file_outcomes_by_cohort", derived, site, publish=False)


def build_judges(derived: Path, site: Path, complement: pl.DataFrame | None) -> None:
    """Judges deciding vs complement. Per-judge rows (names as a key) stay in
    data/processed/links/; the derived table holds counts and anonymous distributions only."""
    p = paths.processed_dir() / "s3" / "decisions_meta.parquet"
    if not p.exists():
        return
    dec = judges.judge_decisions(pl.read_parquet(p))
    out = paths.processed_dir() / "links"
    out.mkdir(exist_ok=True)
    dec.write_parquet(out / "judge_decisions_internal.parquet")
    t = judges.court_year_table(dec, complement).with_columns(
        pl.lit(
            "Published decisions only (A2AJ); Federal Court and Tax Court, where one judge "
            "decides; associate judges and prothonotaries excluded; judges matched by surname "
            "from the decision header; complement from FJA snapshots (persons, not full-time "
            "equivalents). No individual is identified: figures are counts or distributions "
            "across judges, and distributions over fewer than five judges are withheld."
        ).alias("bias_statement")
    )
    _write(t, "link_judges_vs_complement_by_court_year", derived, site, publish=False)


def build_appeal_chains(derived: Path, site: Path) -> None:
    """FCA appeal -> the file appealed from, where the appeal's opening entries name it. Lower
    files come from S10 (Federal Court non-immigration, 2018 on), S4 (immigration to 2022) and
    S12 (Tax Court, 2018 on). Per-chain rows stay in data/processed/links/."""
    proc = paths.processed_dir()
    p10 = proc / "s10" / "dockets.parquet"
    if not p10.exists():
        return
    d = pl.read_parquet(p10)
    nat = pl.col("nature").fill_null("")
    origin = (
        pl.when(nat.str.starts_with("Appeal (S.27"))
        .then(pl.lit("Federal Court"))
        .when(nat.str.contains("Tax Court"))
        .then(pl.lit("Tax Court"))
        .otherwise(pl.lit("other"))
    )
    fca = d.filter(pl.col("prefix") == "A").select(
        pl.col("docket").alias("fca_docket"),
        pl.col("docket_year").alias("fca_year"),
        origin.alias("origin"),
        nat.str.contains("Interloc").alias("interlocutory"),
        pl.col("date_filed").alias("fca_filed"),
        pl.col("final_disposition_date").alias("fca_end"),
        pl.col("scraped").str.to_date(strict=False).alias("scraped_date"),
        "appeal_from_file",
        "appeal_from_decision_date",
    )
    cols = ["docket", "date_filed", "final_disposition_date"]
    lower = [
        d.filter(pl.col("prefix") != "A").select(cols).with_columns(pl.lit("S10").alias("src"))
    ]
    for sid in ("s4", "s12"):
        p = proc / sid / "dockets.parquet"
        if p.exists():
            lower.append(
                pl.read_parquet(p, columns=cols).with_columns(pl.lit(sid.upper()).alias("src"))
            )
    low = (
        pl.concat(lower, how="vertical_relaxed")
        .unique("docket", keep="first")
        .rename(
            {
                "docket": "appeal_from_file",
                "date_filed": "lower_filed",
                "final_disposition_date": "lower_end",
            }
        )
    )
    n0 = fca.height
    ch = fca.join(low, on="appeal_from_file", how="left")
    assert ch.height == n0
    days = lambda a, b: (pl.col(a) - pl.col(b)).dt.total_days()  # noqa: E731
    ch = ch.with_columns(
        pl.when(pl.col("appeal_from_file").is_null())
        .then(pl.lit("lower file not named"))
        .when(pl.col("src").is_null())
        .then(pl.lit("named, not in our data"))
        .otherwise(pl.lit("linked"))
        .alias("status"),
        # filing below to the notice of appeal. The lower file's own end date is not used: a
        # Tax Court file stays open until the appeal comes back, and an interlocutory appeal
        # is taken while the lower file carries on.
        days("fca_filed", "lower_filed").alias("to_appeal_days"),
        days("fca_filed", "appeal_from_decision_date").alias("appeal_lag_days"),
        days("fca_end", "fca_filed").alias("fca_days"),
        days("fca_end", "lower_filed").alias("total_days"),
    ).with_columns(
        pl.when(pl.col("origin") == "Federal Court")
        .then(
            pl.when(pl.col("interlocutory"))
            .then(pl.lit("Federal Court (interlocutory)"))
            .otherwise(pl.lit("Federal Court (final)"))
        )
        .otherwise(pl.col("origin"))
        .alias("origin")
    )
    out = proc / "links"
    out.mkdir(exist_ok=True)
    ch.write_parquet(out / "appeal_chains.parquet")
    linked = pl.col("status") == "linked"
    done = linked & pl.col("fca_days").is_not_null() & (pl.col("to_appeal_days") >= 0)
    agg = (
        ch.filter(pl.col("origin") != "other")
        .group_by("origin", "fca_year")
        .agg(
            pl.len().alias("n_appeals"),
            pl.col("appeal_from_file").is_not_null().mean().alias("lower_file_named_share"),
            linked.mean().alias("linked_share"),
            done.sum().alias("n_complete_chains"),
            pl.col("to_appeal_days").filter(done).median().alias("filing_to_appeal_days_p50"),
            pl.col("fca_days").filter(done).median().alias("fca_days_p50"),
            pl.col("total_days").filter(done).median().alias("total_days_p50"),
            pl.col("total_days").filter(done).quantile(0.9).alias("total_days_p90"),
        )
        .filter(pl.col("n_complete_chains") >= 20)
        .sort("origin", "fca_year")
        .with_columns(
            pl.lit(
                "Completed chains only (the appeal has ended), so recent years are biased short. "
                "Not linked: appeals whose opening entries do not name the lower file (about a "
                "third) and lower files outside our data (Federal Court files before 2018, "
                "immigration files after 2022, Tax Court files before 2018). Years with fewer "
                "than 20 complete chains are omitted. The Supreme Court leg is not built."
            ).alias("bias_statement")
        )
    )
    _write(agg, "link_appeal_chains_by_year", derived, site, publish=False)


def build_links(derived: Path, site: Path) -> None:
    """Decision-to-docket links (S3 x S10). Per-decision rows go to data/processed/links/ and are
    never published; only aggregate match rates are written as a derived table."""
    proc = paths.processed_dir()
    need = [proc / "s3" / "decisions_meta.parquet", proc / "s10" / "dockets.parquet"]
    if not all(p.exists() for p in need):
        return
    dockets = pl.read_parquet(need[1])
    dropped_p = proc / "s10" / "dropped_confidential.parquet"
    keys = linkage.decision_keys(pl.read_parquet(need[0]), ["FC", "FCA"], linkage.normalise_fc_key)
    # the frame is what the crawl covered: census strata, and sampled strata (never a "miss")
    cov = dockets.group_by("prefix").agg(
        pl.col("docket_year").min().alias("lo"), pl.col("docket_year").max().alias("hi")
    )
    span = {r["prefix"]: (r["lo"], r["hi"]) for r in cov.iter_rows(named=True)}
    links = linkage.link_decisions(
        keys,
        dockets,
        pl.read_parquet(proc / "s10" / "entries.parquet"),
        census={p: span[p] for p in ("A", "T") if p in span},
        sample={p: span[p] for p in ("IMM",) if p in span},
        dropped=pl.read_parquet(dropped_p) if dropped_p.exists() else None,
    )
    out = proc / "links"
    out.mkdir(exist_ok=True)
    links.write_parquet(out / "fc_decision_docket.parquet")
    rates = linkage.match_rates(links).with_columns(
        pl.lit(
            "Published decisions (A2AJ) joined to docket files by court file number; census "
            "strata only (FCA from 2010, FC non-immigration from 2018); files we drop for a "
            "confidentiality marker are counted, not linked"
        ).alias("bias_statement")
    )
    _write(rates, "link_fc_decision_docket_match_rates", derived, site, publish=False)
    meta = pl.read_parquet(need[0])

    # FC immigration decisions x Refugee Law Lab dockets (S4: filed to 2022, scraped Nov 2022)
    s4d, s4e = proc / "s4" / "dockets.parquet", proc / "s4" / "entries.parquet"
    if s4d.exists() and s4e.exists():
        d4 = pl.read_parquet(s4d).with_columns(
            pl.lit(None, dtype=pl.String).alias("proceeding_type")
        )
        k4 = linkage.decision_keys(meta, ["FC"], linkage.normalise_fc_key).filter(
            pl.col("key").str.starts_with("IMM-")
        )
        lo, hi = max(int(d4["filing_year"].min()), 1997), int(d4["filing_year"].max())
        l4 = linkage.link_decisions(k4, d4, pl.read_parquet(s4e), census={"IMM": (lo, hi)})
        l4.write_parquet(out / "fc_imm_decision_docket.parquet")
        r4 = linkage.match_rates(l4).with_columns(
            pl.lit(
                "Published FC immigration decisions (A2AJ) joined to Refugee Law Lab dockets by "
                "file number; dockets scraped November 2022, so later decisions on these files "
                "have no docket entry to match"
            ).alias("bias_statement")
        )
        _write(r4, "link_fc_imm_decision_docket_match_rates", derived, site, publish=False)

    # Tax Court decisions x Tax Court dockets (S12 census from 2018)
    s12d, s12e = proc / "s12" / "dockets.parquet", proc / "s12" / "entries.parquet"
    if s12d.exists() and s12e.exists():
        t = pl.read_parquet(s12d)
        dt = t.select(
            "docket",
            "date_filed",
            pl.col("procedure_group").alias("proceeding_type"),
            "nature",
            "final_disposition_date",
            pl.col("first_hearing_date").alias("hearing_date"),
            "judgment_date",
        )
        et = pl.read_parquet(s12e).with_columns(
            pl.col("entry_type").replace({"hearing_held": "hearing"}),
            pl.lit(None, dtype=pl.String).alias("hearing_subject"),
        )
        kt = linkage.decision_keys(meta, ["TCC"], linkage.normalise_tcc_key)
        lt = linkage.link_decisions(
            kt,
            dt,
            et,
            census={"TCC": (int(t["docket_year"].min()), int(t["docket_year"].max()))},
            key_parts=linkage.tcc_key_parts,
        )
        lt.write_parquet(out / "tcc_decision_docket.parquet")
        rt = linkage.match_rates(lt).with_columns(
            pl.lit(
                "Published Tax Court decisions (A2AJ) joined to docket files by file number; "
                "files from 2018 on; only a few percent of files end in a published decision"
            ).alias("bias_statement")
        )
        _write(rt, "link_tcc_decision_docket_match_rates", derived, site, publish=False)


def build_all() -> None:
    derived, site = _out_dirs()
    build_s1(derived, site)
    build_s5(derived, site)
    build_s6(derived, site)
    fed = build_s8(derived, site)
    v = build_s9(derived, site)
    if v is not None and "FC" in fed:
        _write(
            panel.federal_quarterly_panel(v, fed["FC"]), "s9_s8_fc_quarterly_panel", derived, site
        )
    build_s3(derived, site)
    build_s4(derived, site)
    build_s7(derived, site)
    build_s12(derived, site)
    build_s10(derived, site)
    build_links(derived, site)
    build_appeal_chains(derived, site)
    build_judges(derived, site, v)
