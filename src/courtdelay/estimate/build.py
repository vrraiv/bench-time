"""``courtdelay build``: turn processed source parquet into the small derived tables the site uses.

Everything written here is an aggregate (no names, no texts). Each table carries a
``bias_statement`` column or an accompanying note, plus vintage columns where available.
Outputs go to data/processed/derived/ (parquet) and site/src/data/ (CSV, gitignored until it is
decided what is published).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from pathlib import Path

import polars as pl

from courtdelay.common import paths
from courtdelay.estimate import (
    benchmark,
    judges,
    linkage,
    panel,
    reserve_time,
    stock_flow,
    survival,
)

log = logging.getLogger(__name__)


def _out_dirs() -> tuple[Path, Path]:
    derived = paths.processed_dir() / "derived"
    derived.mkdir(exist_ok=True)
    site = paths.REPO_ROOT / "site" / "src" / "data"
    site.mkdir(parents=True, exist_ok=True)
    return derived, site


#: Open-data sources that are also refreshed on GitHub Actions. Their pages change in place and
#: are cached on the owner's machine until re-requested, so a local build can be older than the
#: committed tables. ``site/src/data/source_vintage.json`` records, per source, the fetch date of
#: the data behind the committed tables; a build whose local copy is older leaves them alone.
GUARDED = ("s1", "s2", "s5", "s7", "s8", "s9")
VINTAGE_FILE = "source_vintage.json"
_guard: dict | None = None  # set by build_all; None means no guard (direct calls, tests)


def local_vintage() -> dict[str, str]:
    """Newest fetch date (YYYY-MM-DD) among each guarded source's cached 2xx responses."""
    out = {}
    raw = paths.data_dir() / "raw"
    for sid in GUARDED:
        best = ""
        for meta_file in raw.glob(f"{sid}_*/*.meta.json"):
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if 200 <= (meta.get("status") or 0) < 300:
                best = max(best, meta["fetched_at"][:10])
        if best:
            out[sid] = best
    return out


def start_guard(site: Path) -> dict:
    f = site / VINTAGE_FILE
    committed = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    local = local_vintage()
    stale = {s for s in GUARDED if s in local and s in committed and local[s] < committed[s]}
    return {"committed": committed, "local": local, "stale": stale, "changed": set(), "kept": []}


def finish_guard(site: Path) -> None:
    """Record the fetch date for sources whose tables changed (or that have no entry yet), and
    say which tables were left alone. A source with no local data keeps its committed entry."""
    g = _guard
    if g is None:
        return
    new = dict(g["committed"])
    for sid, day in g["local"].items():
        if sid in g["changed"] or sid not in new:
            new[sid] = day
    if new != g["committed"]:
        (site / VINTAGE_FILE).write_text(
            json.dumps(dict(sorted(new.items())), indent=1) + "\n", encoding="utf-8", newline="\n"
        )
    for sid in sorted(g["stale"]):
        log.warning(
            "build: local %s data (fetched %s) is older than the committed tables (%s); "
            "%d table(s) left as committed. Run: uv run courtdelay fetch %s --refresh",
            sid,
            g["local"][sid],
            g["committed"][sid],
            sum(sid in srcs for _, srcs in g["kept"]),
            sid,
        )


def _table_sources(name: str) -> set[str]:
    """Guarded sources a table is built from, read from its name (``s9_s8_fc_...`` -> s9, s8)."""
    out = set()
    for token in name.split("_"):
        if token not in GUARDED:
            break
        out.add(token)
    return out


def _csv_rows(text: str) -> list[dict]:
    return [
        {k: v for k, v in r.items() if k != "fetched_at"} for r in csv.DictReader(io.StringIO(text))
    ]


def _write(df: pl.DataFrame, name: str, derived: Path, site: Path, *, publish: bool = True) -> None:
    """Published tables go to site/src/data (committed). ``publish=False`` tables are held back
    from the repository until the owner decides; their CSV goes to site/src/review-data
    (gitignored) so the access-gated preview site can show them as results under review.

    A published table is left untouched when its source data is older than the committed copy
    (see ``GUARDED``), and when nothing but the ``fetched_at`` column would change."""
    df.write_parquet(derived / f"{name}.parquet")
    if publish:
        srcs = _table_sources(name)
        target = site / f"{name}.csv"
        if _guard is not None and srcs & _guard["stale"]:
            _guard["kept"].append((name, srcs))
            log.warning("build: %s left as committed (local source data is older)", name)
            return
        text = df.write_csv()
        if target.exists() and _csv_rows(target.read_text(encoding="utf-8")) == _csv_rows(text):
            log.info("build: %s unchanged", name)
            return
        target.write_text(text, encoding="utf-8", newline="")
        if _guard is not None:
            _guard["changed"] |= srcs
    else:
        review = site.parent / "review-data"
        review.mkdir(exist_ok=True)
        df.write_csv(review / f"{name}.csv")
    log.info("build: %s (%d rows%s)", name, df.height, "" if publish else ", held back")


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


def build_s8_benchmark(derived: Path, site: Path) -> None:
    """The Federal Court's published filings, dispositions and pending against counts from
    court-file records. Held back: it carries docket-derived pending counts."""
    proc = paths.processed_dir()
    act = proc / "s8" / "fc_activity.parquet"
    if not act.exists():
        return
    s10, s4 = proc / "s10" / "dockets.parquet", proc / "s4" / "dockets.parquet"
    older = proc / "s10" / "imm_pre2022.parquet"
    fca = proc / "s8" / "fca_activity.parquet"
    if not (s10.exists() or s4.exists()):
        return
    t = benchmark.fc_benchmark(
        pl.read_parquet(act),
        pl.read_parquet(s10) if s10.exists() else None,
        pl.read_parquet(s4) if s4.exists() else None,
        pl.read_parquet(older) if older.exists() else None,
        pl.read_parquet(fca) if fca.exists() else None,
    )
    _write(t, "s8_fc_benchmark_vs_court_files", derived, site, publish=False)


def build_s9(derived: Path, site: Path) -> pl.DataFrame | None:
    p = paths.processed_dir() / "s9" / "judges_snapshots.parquet"
    if not p.exists():
        return None
    v = panel.monthly_vacancy_panel(pl.read_parquet(p))
    v = v.sort(["court_code", "month"])  # stable row order: the panel came out in group order
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
        min_followed_share=0.5,
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
    """FCA and Federal Court (non-immigration) cohort tables from the docket census. Published
    (owner decision 2026-11-19); Tax Court, appeal-chain and judge tables are still held back."""
    p = paths.processed_dir() / "s10" / "dockets.parquet"
    if not p.exists():
        return
    d = (
        pl.read_parquet(p)
        .filter(pl.col("prefix").is_in(["A", "T"]) & ~pl.col("is_registration"))
        # same population as the Court's own counts (owner rule 2026-11-22): its Federal Court
        # figures appear to leave out the Crown's tax-collection matters, so the tables do too
        .filter(
            ~(
                (pl.col("prefix") == "T")
                & pl.col("nature").fill_null("").str.contains(benchmark.TAX_COLLECTION_RX)
            )
        )
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
        min_followed_share=0.5,
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
        _write(km, "s10_fc_fca_km_by_cohort", derived, site)
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
    _write(mix, "s10_fc_fca_file_outcomes_by_cohort", derived, site)


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
                "than 20 complete chains are omitted. The Supreme Court stage is a separate table."
            ).alias("bias_statement")
        )
    )
    _write(agg, "link_appeal_chains_by_year", derived, site, publish=False)


def build_scc_leg(derived: Path, site: Path) -> None:
    """Supreme Court leg of the appeal chains, for appeals the Court heard: SCC decision -> the
    FCA judgment appealed -> the FCA court file -> (where linked) the file in the court below.
    Leave applications are covered by build_scc_cases (S13). Run after build_links
    and build_appeal_chains."""
    from courtdelay.sources import s3_a2aj_decisions as s3

    proc = paths.processed_dir()
    need = [
        proc / "s3" / "decisions_meta.parquet",
        proc / "links" / "fc_decision_docket.parquet",
        proc / "s10" / "dockets.parquet",
    ]
    raw, _ = s3._parquet_for("SCC")
    if raw is None or not all(p.exists() for p in need):
        return
    meta = pl.read_parquet(need[0])
    scc = meta.filter((pl.col("court") == "SCC") & (pl.col("decision_date").dt.year() >= 2010))
    text = (
        pl.scan_parquet(raw)
        .filter(pl.col("citation_en").is_in(scc["citation_en"].to_list()))
        .select("citation_en", "unofficial_text_en", "cases_cited_en")
        .collect()
    )
    year = dict(zip(scc["citation_en"], scc["decision_date"].dt.year(), strict=True))
    found = [
        (c, *linkage.scc_appeal_from_fca(t, cited, year[c]))
        for c, t, cited in zip(
            text["citation_en"].to_list(),
            text["unofficial_text_en"].to_list(),
            text["cases_cited_en"].to_list(),
            strict=True,
        )
    ]
    src = pl.DataFrame(found, schema=["citation_en", "fca_citation", "basis"], orient="row").filter(
        pl.col("fca_citation").is_not_null()
    )
    fca_dec = meta.filter(pl.col("court") == "FCA").select(
        pl.col("citation_en").alias("fca_citation"), pl.col("decision_date").alias("fca_judgment")
    )
    links = (
        pl.read_parquet(need[1])
        .filter((pl.col("court") == "FCA") & (pl.col("status") == "linked"))
        .select(pl.col("decision_id").alias("fca_citation"), pl.col("key").alias("fca_docket"))
        .unique("fca_citation", keep="first")
    )
    fca_file = pl.read_parquet(need[2]).select(
        pl.col("docket").alias("fca_docket"), pl.col("date_filed").alias("fca_filed")
    )
    ch = (
        scc.select(
            "citation_en",
            pl.col("hearing_last_date").alias("scc_hearing"),
            pl.col("decision_date").alias("scc_judgment"),
        )
        .join(src, on="citation_en")
        .join(fca_dec, on="fca_citation", how="left")
        .join(links, on="fca_citation", how="left")
        .join(fca_file, on="fca_docket", how="left")
    )
    chains_p = proc / "links" / "appeal_chains.parquet"
    if chains_p.exists():
        low = (
            pl.read_parquet(chains_p)
            .filter(pl.col("status") == "linked")
            .select("fca_docket", "origin", "lower_filed")
        )
        ch = ch.join(low, on="fca_docket", how="left")
    else:
        ch = ch.with_columns(
            pl.lit(None, dtype=pl.String).alias("origin"),
            pl.lit(None, dtype=pl.Date).alias("lower_filed"),
        )

    def days(a: str, b: str) -> pl.Expr:
        return (pl.col(a) - pl.col(b)).dt.total_days()

    ch = ch.with_columns(
        days("fca_judgment", "fca_filed").alias("fca_days"),
        days("scc_hearing", "fca_judgment").alias("fca_judgment_to_scc_hearing_days"),
        days("scc_judgment", "scc_hearing").alias("scc_hearing_to_judgment_days"),
        days("scc_judgment", "fca_filed").alias("fca_filing_to_scc_judgment_days"),
        days("scc_judgment", "lower_filed").alias("lower_filing_to_scc_judgment_days"),
        pl.when(pl.col("scc_judgment").dt.year() < 2018)
        .then(pl.lit("2010-2017"))
        .otherwise(pl.lit("2018-2026"))
        .alias("period"),
    )
    (proc / "links").mkdir(exist_ok=True)
    ch.write_parquet(proc / "links" / "scc_chains.parquet")
    rows = []
    for period in ["2010-2017", "2018-2026", "2010-2026"]:
        sub = ch if period == "2010-2026" else ch.filter(pl.col("period") == period)
        for col, label in [
            ("fca_days", "FCA: filing to judgment"),
            ("fca_judgment_to_scc_hearing_days", "FCA judgment to Supreme Court hearing"),
            ("scc_hearing_to_judgment_days", "Supreme Court: hearing to judgment"),
            ("fca_filing_to_scc_judgment_days", "FCA filing to Supreme Court judgment"),
            ("lower_filing_to_scc_judgment_days", "Filing in the court below to SCC judgment"),
        ]:
            v = sub[col].drop_nulls()
            v = v.filter(v >= 0)
            if v.len() < 20:  # no small cells
                continue
            rows.append(
                {
                    "scc_judgment_period": period,
                    "leg": label,
                    "n": v.len(),
                    "p50_days": v.median(),
                    "p25_days": v.quantile(0.25),
                    "p75_days": v.quantile(0.75),
                    "p90_days": v.quantile(0.9),
                }
            )
    agg = pl.DataFrame(rows).with_columns(
        pl.lit(
            "Appeals from the Federal Court of Appeal that the Supreme Court heard and decided "
            "(published decisions, 2010 on); cases refused leave are not included and the leave "
            "stage is not measured separately; the FCA judgment appealed is taken from the "
            "decision's own statement or, failing that, the most recent FCA decision it cites; "
            "legs with fewer than 20 cases are omitted."
        ).alias("bias_statement")
    )
    _write(agg, "link_scc_leg_from_fca", derived, site, publish=False)


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
    rates = linkage.match_rates(links, min_n=30).with_columns(
        pl.lit(
            "Published decisions (A2AJ) joined to docket files by court file number; census "
            "strata only (FCA from 2010, FC non-immigration from 2018); files we drop for a "
            "confidentiality marker are counted, not linked"
        ).alias("bias_statement")
    )
    _write(rates, "link_fc_decision_docket_match_rates", derived, site)
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
        r4 = linkage.match_rates(l4, min_n=30).with_columns(
            pl.lit(
                "Published FC immigration decisions (A2AJ) joined to Refugee Law Lab dockets by "
                "file number; dockets scraped November 2022, so later decisions on these files "
                "have no docket entry to match"
            ).alias("bias_statement")
        )
        _write(r4, "link_fc_imm_decision_docket_match_rates", derived, site)

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
        rt = linkage.match_rates(lt, min_n=30).with_columns(
            pl.lit(
                "Published Tax Court decisions (A2AJ) joined to docket files by file number; "
                "files from 2018 on; only a few percent of files end in a published decision"
            ).alias("bias_statement")
        )
        _write(rt, "link_tcc_decision_docket_match_rates", derived, site, publish=False)


SCC_ORIGINS = [
    ("Court of Appeal for Ontario", r"^Court of Appeal (for|of) Ontario"),
    ("Federal Court of Appeal", r"^Federal Court of Appeal"),
    ("Court of Appeal of Quebec", r"^Court of Appeal of Quebec"),
    ("Court of Appeal for British Columbia", r"^Court of Appeal (for|of) British Columbia"),
    ("Court of Appeal of Alberta", r"^Court of Appeal of Alberta"),
]
S13_BIAS = (
    "Supreme Court of Canada case information pages, every file opened from 2010, read "
    "November 2026. Unit is the Supreme Court file, not the application: a file with several "
    "leave judgments counts once, at its latest. Files under leave still pending are censored "
    "at the read date; applications discontinued before a decision are censored at the "
    "discontinuance. Cases that reach the Supreme Court are a selected group and do not "
    "describe the courts below in general."
)


def _scc_origin() -> pl.Expr:
    name = pl.col("court_appealed_from").fill_null("")
    e = pl.lit("Other courts")
    for label, rx in reversed(SCC_ORIGINS):
        e = pl.when(name.str.contains(rx)).then(pl.lit(label)).otherwise(e)
    return e.alias("origin")


def _quantile_rows(df: pl.DataFrame, by: list[str], legs: list[tuple[str, str]], min_n: int = 30):
    """Median and tails of completed intervals, long format, cells under ``min_n`` omitted."""
    out = []
    for col, label in legs:
        v = pl.col(col).filter(pl.col(col) >= 0)
        out.append(
            df.group_by(by)
            .agg(
                v.count().alias("n"),
                v.median().alias("p50_days"),
                v.quantile(0.25).alias("p25_days"),
                v.quantile(0.75).alias("p75_days"),
                v.quantile(0.9).alias("p90_days"),
            )
            .filter(pl.col("n") >= min_n)
            .with_columns(pl.lit(label).alias("leg"))
        )
    return pl.concat(out, how="vertical_relaxed").select([*by, "leg", pl.exclude([*by, "leg"])])


def build_scc_cases(derived: Path, site: Path) -> None:
    """Supreme Court leave and appeal stages from the court's case pages (S13): by court
    appealed from, a check against the court's own yearly statistics, and the Federal Court of
    Appeal chain through the leave stage. All held back (appeal-chain results)."""
    proc = paths.processed_dir()
    p13 = proc / "s13" / "cases.parquet"
    if not p13.exists():
        return

    def days(a: str, b: str) -> pl.Expr:
        return (pl.col(a) - pl.col(b)).dt.total_days()

    def period(col: str) -> pl.Expr:
        y = pl.col(col).dt.year()
        return (
            pl.when(y < 2015)
            .then(pl.lit("2010-2014"))
            .when(y < 2020)
            .then(pl.lit("2015-2019"))
            .otherwise(pl.lit("2020-2026"))
        )

    c = pl.read_parquet(p13).with_columns(
        _scc_origin(),
        pl.col("scraped").str.to_date(strict=False).alias("scraped_date"),
        pl.col("leave_completed_date").cast(pl.Date),
    )
    # appeals as of right and references carry no leave application: kept out of leave tables
    leave = c.filter(
        pl.col("leave_filed_date").is_not_null() & (pl.col("leave_filed_date").dt.year() >= 2010)
    ).with_columns(
        period("leave_filed_date").alias("filing_period"),
        days("leave_filed_date", "lower_court_judgment_date").alias("judgment_to_leave_filing"),
        days("leave_completed_date", "leave_filed_date").alias("filing_to_complete"),
        days("lower_court_judgment_date", "first_ruling_date").alias("first_ruling_to_appeal"),
    )

    # -- leave stage by court appealed from ----------------------------------------------------
    both = pl.concat(
        [leave, leave.with_columns(pl.lit("All courts").alias("origin"))],
        how="vertical_relaxed",
    )
    both = pl.concat(
        [both, both.with_columns(pl.lit("2010-2026").alias("filing_period"))],
        how="vertical_relaxed",
    ).with_columns((pl.col("origin") + "|" + pl.col("filing_period")).alias("cohort"))
    km = survival.cohort_table(
        both,
        cohort_col="cohort",
        start_col="leave_filed_date",
        event_col="leave_decision_date",
        censor_col="scraped_date",
        competing_col="leave_discontinued_date",
        n_boot=200,
        label="leave application filed -> leave decision",
        min_at_risk=20,
        min_followed_share=0.5,
        bias_statement=S13_BIAS,
    )
    decided = pl.col("leave_result").is_not_null()
    extra = both.group_by("cohort").agg(
        decided.sum().alias("n_decided"),
        (pl.col("leave_result") == "granted").sum().alias("n_granted"),
        pl.col("judgment_to_leave_filing").median().alias("judgment_below_to_filing_days_p50"),
        pl.col("filing_to_complete").median().alias("filing_to_complete_days_p50"),
        pl.col("filing_to_complete").quantile(0.9).alias("filing_to_complete_days_p90"),
        pl.col("first_ruling_to_appeal")
        .filter(pl.col("first_ruling_to_appeal") >= 0)
        .count()
        .alias("n_first_ruling"),
        pl.col("first_ruling_to_appeal")
        .filter(pl.col("first_ruling_to_appeal") >= 0)
        .median()
        .alias("first_ruling_to_appeal_judgment_days_p50"),
    )
    by_origin = (
        km.join(extra, on="cohort")
        .with_columns(
            pl.col("cohort").str.split("|").list.get(0).alias("origin"),
            pl.col("cohort").str.split("|").list.get(1).alias("filing_period"),
            # no rate on fewer than 30 decided files or fewer than 5 grants
            pl.when((pl.col("n_decided") >= 30) & (pl.col("n_granted") >= 5))
            .then(pl.col("n_granted") / pl.col("n_decided"))
            .alias("granted_share"),
            pl.when(pl.col("n_first_ruling") < 30)
            .then(None)
            .otherwise(pl.col("first_ruling_to_appeal_judgment_days_p50"))
            .alias("first_ruling_to_appeal_judgment_days_p50"),
        )
        # counts that can fall under the 30-file minimum are not carried in the table
        .drop("cohort", "n_competing", "n_granted", "n_first_ruling")
        .sort("origin", "filing_period")
    )
    by_origin = by_origin.select(
        ["origin", "filing_period", pl.exclude(["origin", "filing_period", "bias_statement"])]
        + ["bias_statement"]
    )
    _write(by_origin, "s13_scc_leave_by_origin", derived, site, publish=False)

    # -- check against the court's own yearly statistics (S5) ----------------------------------
    p5 = proc / "s5" / "scc_stats.parquet"
    if p5.exists():
        s5 = pl.read_parquet(p5).filter(pl.col("year").is_between(2011, 2025))
        m = 30.44
        ours = []

        def add(measure, year_col, value, sub=c, months_col=None):
            g = sub.filter(pl.col(year_col).is_not_null()).group_by(
                pl.col(year_col).dt.year().alias("year")
            )
            if months_col is None:
                t = g.agg(pl.len().cast(pl.Float64).alias("ours"))
            else:
                v = pl.col(months_col) / m
                t = g.agg(
                    v.mean().round(1).alias("ours"),
                    v.median().round(1).alias("our_median"),
                    v.quantile(0.9).round(1).alias("our_p90"),
                )
            ours.append(t.with_columns(pl.lit(measure).alias("measure"), pl.lit(value).alias("k")))

        t = c.with_columns(
            days("leave_decision_date", "leave_completed_date").alias("complete_to_decision"),
            days("leave_decision_date", "leave_filed_date").alias("filed_to_decision"),
            days("hearing_date", "leave_decision_date").alias("leave_to_hearing"),
            days("judgment_date", "hearing_date").alias("hearing_to_judgment"),
        )
        granted = t.filter(pl.col("leave_granted_any").fill_null(False))
        add(
            "Leave applications filed (count)",
            "leave_filed_date",
            "Cases filed|Complete applications for leave to appeal",
        )
        add(
            "Leave applications granted (count)",
            "leave_decision_date",
            "Applications for leave|Granted (pending)",
            sub=t.filter(pl.col("leave_result") == "granted"),
        )
        add("Appeals heard (count)", "hearing_date", "Appeals heard|Total number")
        add("Appeal judgments (count)", "judgment_date", "Appeal judgments|Total number")
        add(
            "Complete leave application to leave decision (average months)",
            "leave_decision_date",
            "Average time lapses (in months)|Between filing of application for leave and "
            "decision on application for leave",
            sub=t,
            months_col="complete_to_decision",
        )
        add(
            "Leave application first filed to leave decision (average months)",
            "leave_decision_date",
            None,
            sub=t,
            months_col="filed_to_decision",
        )
        add(
            "Leave granted to hearing (average months)",
            "hearing_date",
            "Average time lapses (in months)|Between date leave granted (or date notice of "
            "appeal as of right filed) and hearing",
            sub=granted,
            months_col="leave_to_hearing",
        )
        add(
            "Hearing to judgment (average months)",
            "judgment_date",
            "Average time lapses (in months)|Between hearing and judgment",
            sub=t,
            months_col="hearing_to_judgment",
        )
        court = s5.select(
            (pl.col("section") + "|" + pl.col("item")).alias("k"),
            "year",
            pl.col("value").alias("court_published"),
        ).unique(["k", "year"], keep="first")
        chk = (
            pl.concat(ours, how="diagonal_relaxed")
            .filter(pl.col("year").is_between(2011, 2025))
            # judgments of 2011 mostly belong to files opened before 2010, outside the frame
            .filter(~((pl.col("year") == 2011) & pl.col("measure").str.contains("udgment")))
            .join(court, on=["k", "year"], how="left")
            .drop("k")
            .sort("measure", "year")
            .select("measure", "year", "ours", "court_published", "our_median", "our_p90")
            .with_columns(
                pl.lit(
                    "Ours: computed from the Supreme Court's case pages (files opened from "
                    "2010, so 2011 is the first full year), counted by file. Court: the "
                    "court's published yearly statistics, which count applications and may "
                    "assign years differently. The court's leave average runs from the date "
                    "the application was complete; ours from first filing is shown beside it. "
                    "Our leave-to-hearing figure leaves out appeals as of right."
                ).alias("bias_statement")
            )
        )
        _write(chk, "s13_scc_vs_court_statistics", derived, site, publish=False)

    # -- appeal stages for files that went on to a hearing --------------------------------------
    ap = pl.concat(
        [c, c.with_columns(pl.lit("All courts").alias("origin"))], how="vertical_relaxed"
    ).with_columns(
        days("hearing_date", "leave_decision_date").alias("a"),
        days("hearing_date", "appeal_perfected_date").alias("b"),
        days("judgment_date", "hearing_date").alias("c"),
        days("judgment_date", "leave_filed_date").alias("d"),
    )
    stages = _quantile_rows(
        ap,
        ["origin"],
        [
            ("a", "Leave granted to hearing"),
            ("b", "Appeal ready for hearing to hearing"),
            ("c", "Hearing to judgment"),
            ("d", "Leave application filed to judgment on the appeal"),
        ],
    ).with_columns(
        pl.lit(
            "Completed intervals only, files opened 2010 to 2026 pooled, so the most recent "
            "files are under-represented in the longer intervals. Hearing to judgment includes "
            "judgments given from the bench (zero days). Cells under 30 files omitted. " + S13_BIAS
        ).alias("bias_statement")
    )
    _write(
        stages.sort("origin", "leg"),
        "s13_scc_appeal_stages_by_origin",
        derived,
        site,
        publish=False,
    )

    # -- Federal Court of Appeal chain through the leave stage ----------------------------------
    p10 = proc / "s10" / "dockets.parquet"
    if not p10.exists():
        return
    fca_files = pl.read_parquet(p10).filter(pl.col("prefix") == "A")
    known = set(fca_files["docket"].to_list())
    plinks = proc / "links" / "fc_decision_docket.parquet"
    by_cite = {}
    if plinks.exists():
        lk = pl.read_parquet(plinks).filter(
            (pl.col("court") == "FCA") & (pl.col("status") == "linked")
        )
        by_cite = dict(zip(lk["decision_id"].to_list(), lk["key"].to_list(), strict=True))
    f = c.filter(pl.col("origin") == "Federal Court of Appeal")
    rows = []
    for case_no, files, cite in zip(
        f["case_no"].to_list(),
        f["lower_court_files"].to_list(),
        f["lower_court_citation"].to_list(),
        strict=True,
    ):
        toks = [t.strip().upper() for t in (files or "").split(";") if t.strip()]
        keys = [linkage.normalise_fc_key(re.sub(r"\s+", "-", t)) for t in toks]
        hit = next((k for k in keys if k in known), None)
        if hit:
            status = "linked by file number"
        elif cite and by_cite.get(cite) in known:
            hit, status = by_cite[cite], "linked by citation"
        elif any(re.fullmatch(r"\d{2}-A-\d+", t) for t in toks):
            status = "motion number (no appeal file)"
        elif any(k and linkage.key_year(k) < 2010 for k in keys):
            status = "FCA file from before 2010"
        elif not toks:
            status = "no file number given"
        else:
            status = "not found"
        rows.append((case_no, hit, status))
    link = pl.DataFrame(rows, schema=["case_no", "fca_docket", "link_status"], orient="row")
    ch = (
        f.join(link, on="case_no")
        .join(
            fca_files.select(
                pl.col("docket").alias("fca_docket"),
                pl.col("date_filed").alias("fca_filed"),
                pl.col("judgment_date").alias("fca_judgment_in_file"),
                pl.col("final_disposition_date").alias("fca_end"),
            ),
            on="fca_docket",
            how="left",
        )
        .with_columns(
            days("lower_court_judgment_date", "fca_filed").alias("fca_days"),
            days("leave_filed_date", "lower_court_judgment_date").alias("to_leave_filing"),
            days("leave_decision_date", "leave_filed_date").alias("leave_days"),
            days("leave_decision_date", "fca_filed").alias("fca_filing_to_leave_decision"),
            days("judgment_date", "fca_filed").alias("fca_filing_to_scc_judgment"),
            (days("lower_court_judgment_date", "fca_end").abs() <= 7).alias("dates_agree"),
            pl.when(pl.col("leave_result") == "granted")
            .then(pl.lit("Leave granted"))
            .when(pl.col("leave_result").is_not_null())
            .then(pl.lit("Leave refused or otherwise ended"))
            .alias("leave_outcome"),
        )
    )
    (proc / "links").mkdir(exist_ok=True)
    ch.write_parquet(proc / "links" / "scc_leave_fca.parquet")
    linked = ch.filter(pl.col("fca_docket").is_not_null())
    log.info(
        "S13-S10 link: %d FCA-origin files; %s; the Supreme Court's stated FCA judgment date is "
        "within 7 days of the end of the FCA file for %.0f%% of linked files",
        ch.height,
        dict(ch["link_status"].value_counts(sort=True).iter_rows()),
        100 * (linked["dates_agree"].mean() or 0),
    )
    n_by = ch.group_by("link_status").agg(pl.len().alias("n"))
    status = (
        ch.join(n_by, on="link_status")
        .with_columns(
            # statuses with fewer than 30 files are reported together
            pl.when(pl.col("n") < 30)
            .then(pl.lit("not linked, other reasons"))
            .otherwise(pl.col("link_status"))
            .alias("link_status")
        )
        .group_by("link_status")
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") >= 30)
        .with_columns(
            pl.lit("link status").alias("table"),
            (pl.col("n") / ch.height).alias("share"),
        )
        .rename({"link_status": "group"})
    )
    legs = [
        ("fca_days", "FCA: filing to judgment"),
        ("to_leave_filing", "FCA judgment to leave application"),
        ("leave_days", "Leave application to leave decision"),
        ("fca_filing_to_leave_decision", "FCA filing to leave decision"),
        ("fca_filing_to_scc_judgment", "FCA filing to Supreme Court judgment"),
    ]
    dec = linked.filter(pl.col("leave_outcome").is_not_null())
    q = pl.concat(
        [
            _quantile_rows(dec, ["leave_outcome"], legs),
            _quantile_rows(
                dec.with_columns(pl.lit("All decided").alias("leave_outcome")),
                ["leave_outcome"],
                legs[:4],
            ),
        ],
        how="vertical_relaxed",
    ).rename({"leave_outcome": "group"})
    out = pl.concat(
        [status.with_columns(pl.lit(None, dtype=pl.String).alias("leg")), q],
        how="diagonal_relaxed",
    ).with_columns(
        pl.col("table").fill_null("intervals"),
        pl.lit(
            "Supreme Court files that name the Federal Court of Appeal as the court appealed "
            "from, matched to our census of FCA files (2010 on) by file number, then by neutral "
            "citation. Leave decided 2010 to 2026, pooled; completed intervals only. FCA files "
            "opened before 2010 are outside the census. Cells under 30 files omitted. "
            "Applications for leave are a selected group of FCA files."
        ).alias("bias_statement"),
    )
    _write(
        out.select(
            "table",
            "group",
            "leg",
            "n",
            "share",
            pl.exclude(["table", "group", "leg", "n", "share", "bias_statement"]),
            "bias_statement",
        ),
        "link_scc_leave_fca_chain",
        derived,
        site,
        publish=False,
    )


def build_all() -> None:
    global _guard
    derived, site = _out_dirs()
    _guard = start_guard(site)
    try:
        _build_all(derived, site)
        finish_guard(site)
    finally:
        _guard = None


def _build_all(derived: Path, site: Path) -> None:
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
    build_s8_benchmark(derived, site)
    build_links(derived, site)
    build_appeal_chains(derived, site)
    build_judges(derived, site, v)
    build_scc_leg(derived, site)
    build_scc_cases(derived, site)
