"""Judges deciding cases against the judicial complement (S3 decisions x S9 complement).

A judge's name is used only as a grouping key, and only in data/processed/links/. Every table
written by ``court_year_table`` is a count or an anonymous distribution across judges (owner
decision 2026-11-18: no individual names in published results, judges included).

Scope: courts where one judge decides (Federal Court, Tax Court). Appeal panels are left out
because the header does not say who wrote the reasons.
"""

from __future__ import annotations

import re
import unicodedata

import polars as pl

SINGLE_JUDGE_COURTS = ["FC", "TCC"]
MIN_JUDGES = 5

# not part of the federally appointed complement counted in S9
ASSOCIATE_RE = re.compile(
    r"prothonotary|protonotaire|associate\s+judge|juge\s+adjoint|case\s+management\s+judge|"
    r"assessment\s+officer|officier\s+taxateur|deputy\s+judge|juge\s+suppl[ée]ant",
    re.I,
)
TITLE_RE = re.compile(
    r"\b(?:the|honourable|hon|l|honorable|mr|mrs|ms|madam|madame|monsieur|mister|justice|juge|"
    r"le|la|chief|associate|en|chef|adjointe?|senior|judge|j|ja|cj|acj|jca|jcf|jcci|"
    r"before|present|pr[ée]sent|devant|coram|by|par|reasons|for|judgment|order|and)\b",
    re.I,
)


def judge_key(line: str | None) -> str | None:
    """Grouping key for a single-judge header line: the surname, upper case, accents removed.
    None when the line names no one. Not written to any published table."""
    if not line:
        return None
    t = unicodedata.normalize("NFKD", line).encode("ascii", "ignore").decode()
    t = re.sub(r"[.,:;()\[\]]", " ", t)
    t = TITLE_RE.sub(" ", t)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", t) if len(w) > 1]
    if not words:
        return None
    # surname = last word, with a leading particle kept ("DE MONTIGNY", "ST-LOUIS")
    key = words[-1].upper()
    if len(words) >= 2 and words[-2].lower() in {"de", "du", "van", "von", "st", "ste", "mc"}:
        key = f"{words[-2].upper()} {key}"
    return key


def judge_decisions(meta: pl.DataFrame) -> pl.DataFrame:
    """One row per decision of a single-judge court with a judge key (internal use only)."""
    d = meta.filter(
        pl.col("court").is_in(SINGLE_JUDGE_COURTS) & pl.col("decision_date").is_not_null()
    )
    return d.select(
        "court",
        pl.col("decision_date").dt.year().alias("year"),
        pl.col("judges_line").map_elements(judge_key, return_dtype=pl.String).alias("judge_key"),
        pl.col("judges_line")
        .str.contains("(?i)" + ASSOCIATE_RE.pattern)
        .fill_null(False)
        .alias("associate"),
        "reserve_days",
    )


def court_year_table(dec: pl.DataFrame, complement: pl.DataFrame | None) -> pl.DataFrame:
    """Counts and anonymous across-judge distributions by court and year. No names."""
    judges = dec.filter(pl.col("judge_key").is_not_null() & ~pl.col("associate"))
    per_judge = judges.group_by("court", "year", "judge_key").agg(
        pl.len().alias("n"),
        pl.col("reserve_days").filter(pl.col("reserve_days") >= 0).median().alias("reserve_p50"),
    )
    enough = pl.col("n") >= 10
    out = (
        per_judge.group_by("court", "year")
        .agg(
            pl.len().alias("n_judges_deciding"),
            pl.col("n").sum().alias("n_decisions"),
            pl.col("n").median().alias("decisions_per_judge_p50"),
            pl.col("n").quantile(0.1).alias("decisions_per_judge_p10"),
            pl.col("n").quantile(0.9).alias("decisions_per_judge_p90"),
            enough.sum().alias("n_judges_10plus"),
            pl.col("reserve_p50").filter(enough).quantile(0.1).alias("judge_reserve_p50_p10"),
            pl.col("reserve_p50").filter(enough).median().alias("judge_reserve_p50_p50"),
            pl.col("reserve_p50").filter(enough).quantile(0.9).alias("judge_reserve_p50_p90"),
        )
        .join(
            dec.group_by("court", "year").agg(
                pl.len().alias("n_decisions_all"),
                pl.col("judge_key").is_not_null().mean().alias("judge_identified_share"),
                pl.col("associate").mean().alias("associate_share"),
            ),
            on=["court", "year"],
        )
    )
    # a "distribution" over fewer than five judges would describe identifiable individuals
    few = pl.col("n_judges_10plus") < MIN_JUDGES
    out = out.with_columns(
        [
            pl.when(few).then(None).otherwise(pl.col(c)).alias(c)
            for c in ("judge_reserve_p50_p10", "judge_reserve_p50_p50", "judge_reserve_p50_p90")
        ]
    )
    if complement is not None and complement.height:
        comp = (
            complement.filter(pl.col("court_code").is_in(SINGLE_JUDGE_COURTS))
            .group_by(pl.col("court_code").alias("court"), pl.col("month").dt.year().alias("year"))
            .agg(
                pl.col("in_office").mean().alias("complement_in_office"),
                pl.col("supernumerary").mean().alias("complement_supernumerary"),
                pl.col("vacancies").mean().alias("vacancies"),
            )
        )
        out = out.join(comp, on=["court", "year"], how="left").with_columns(
            (
                pl.col("n_judges_deciding")
                / (pl.col("complement_in_office") + pl.col("complement_supernumerary"))
            ).alias("deciding_to_complement_ratio"),
            (pl.col("n_decisions") / pl.col("complement_in_office")).alias(
                "decisions_per_judge_in_office"
            ),
        )
    return out.sort("court", "year")
