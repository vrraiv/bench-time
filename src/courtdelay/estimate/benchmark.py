"""Benchmarks for the Federal Court's published workload figures (S8) from our docket data.

The pending series on the site is the Court's own published stock. These comparisons rebuild its
components from court-file records: immigration filings from the Refugee Law Lab dockets (S4,
census to 2021) and from our sample of immigration files (S10, about 1,000 per filing year from
2023, 300 for 2022), non-immigration filings and dispositions from our census of ``T`` files
(S10, 2018 on), and the immigration pending stock from the sample.

Every benchmark comes from the same registry as the statistics pages, so agreement shows that the
pages match the Court's file system, not that an outside count confirms them. Docket-derived
pending counts are held back from publication (see CLAUDE.md), so the table built here is written
with ``publish=False``.
"""

from __future__ import annotations

import math
from datetime import date

import polars as pl

TOTAL_RX = r"(?i)^(grand total|total federal court|total trial division|total)$"
IMM_TOTAL_RX = (
    r"(?i)^(immigration (&|and) refugee( \(imm\))?( -)? ?total|immigration and refugee"
    r"|total immigration)$"
)
Z = 1.96

SCHEMA = {
    "component": pl.Utf8,
    "measure": pl.Utf8,
    "period_end": pl.Utf8,
    "court_published": pl.Int64,
    "ours": pl.Int64,
    "ours_lo": pl.Int64,
    "ours_hi": pl.Int64,
    "basis": pl.Utf8,
}


def fc_court_series(fc_activity: pl.DataFrame) -> pl.DataFrame:
    """One row per period: the Court's total, immigration and non-immigration year-to-date
    filings and dispositions and the pending stock. Raises when a period does not have exactly
    one total row and one immigration-total row (the labels change over the years)."""
    cols = ["commenced", "dispositions", "pending"]
    tot = fc_activity.filter(pl.col("subject_matter").str.contains(TOTAL_RX))
    imm = fc_activity.filter(pl.col("subject_matter").str.contains(IMM_TOTAL_RX))
    n = fc_activity["period_end"].n_unique()
    for name, part in (("total", tot), ("immigration total", imm)):
        if part.height != n or part["period_end"].n_unique() != n:
            raise ValueError(f"S8 FC: expected one {name} row per period, got {part.height}/{n}")
    j = tot.select(["period_end", *cols]).join(
        imm.select(["period_end", *cols]), on="period_end", suffix="_imm"
    )
    return j.with_columns(
        *[(pl.col(c) - pl.col(f"{c}_imm")).alias(f"{c}_nonimm") for c in cols]
    ).sort("period_end")


def _strata(sample: pl.DataFrame) -> list[tuple[pl.DataFrame, int, int]]:
    """(files, n sampled, top file number) per filing-year stratum of the immigration sample.
    The top number in the sample stands in for the number of files opened in the year."""
    out = []
    for (_,), k in sample.partition_by("docket_year", as_dict=True).items():
        out.append((k, k.height, int(k["number"].max())))
    return out


def _row(component, measure, period_end, court, ours, lo, hi, basis) -> dict:
    return {
        "component": component,
        "measure": measure,
        "period_end": period_end,
        "court_published": court,
        "ours": None if ours is None else round(ours),
        "ours_lo": None if lo is None else round(lo),
        "ours_hi": None if hi is None else round(hi),
        "basis": basis,
    }


def fc_benchmark(
    fc_activity: pl.DataFrame, s10: pl.DataFrame | None, s4: pl.DataFrame | None
) -> pl.DataFrame:
    """Long table of the Court's published figure against ours, with a 95% sampling interval
    where ours is scaled from the immigration sample. Flows are year to date at ``period_end``."""
    court = fc_court_series(fc_activity)
    rows: list[dict] = []

    if s4 is not None:
        last_full = s4["scraped"].min().year - 1
        filed = dict(s4.group_by(pl.col("date_filed").dt.year()).len().iter_rows())
        for r in court.filter(pl.col("period_end").str.ends_with("12-31")).iter_rows(named=True):
            y = int(r["period_end"][:4])
            if y in filed and y <= last_full:
                rows.append(
                    _row(
                        "immigration",
                        "filings, year to date",
                        r["period_end"],
                        r["commenced_imm"],
                        filed[y],
                        None,
                        None,
                        "Refugee Law Lab dockets (census), by filing date",
                    )
                )

    if s10 is not None:
        fc = s10.filter(pl.col("division") == "T")
        sample = fc.filter(pl.col("prefix") == "IMM")
        census = fc.filter((pl.col("prefix") == "T") & ~pl.col("is_registration"))
        first_census_year = census["docket_year"].min() if census.height else None
        strata = _strata(sample) if sample.height else []
        first_sample_year = min((int(k["docket_year"][0]) for k, _, _ in strata), default=None)

        for r in court.iter_rows(named=True):
            cut = date.fromisoformat(r["period_end"])
            jan1 = date(cut.year, 1, 1)
            in_ytd = pl.col("date_filed").is_between(jan1, cut)
            open_at = (pl.col("date_filed") <= cut) & (
                pl.col("final_disposition_date").is_null()
                | (pl.col("final_disposition_date") > cut)
            )

            # immigration filings: share of the year's sampled files dated by the cut-off
            for k, n, top in strata:
                if int(k["docket_year"][0]) != cut.year or cut.year == first_sample_year:
                    continue
                p = k.filter(in_ytd).height / n
                se = math.sqrt(p * (1 - p) / n)
                rows.append(
                    _row(
                        "immigration",
                        "filings, year to date",
                        r["period_end"],
                        r["commenced_imm"],
                        p * top,
                        (p - Z * se) * top,
                        (p + Z * se) * top,
                        "our sample of immigration files, scaled by the top file number",
                    )
                )

            # immigration pending: sampled files open at the cut-off, scaled stratum by stratum
            if first_sample_year is not None and cut.year > first_sample_year:
                est = var = 0.0
                for k, n, top in strata:
                    p = k.filter(open_at).height / n
                    est += p * top
                    var += top**2 * p * (1 - p) / n
                rows.append(
                    _row(
                        "immigration",
                        "pending at period end",
                        r["period_end"],
                        r["pending_imm"],
                        est,
                        est - Z * math.sqrt(var),
                        est + Z * math.sqrt(var),
                        f"our sample of immigration files opened from {first_sample_year}, "
                        "scaled; older files not counted",
                    )
                )

            # non-immigration flows: census of T files, year ends and the latest period
            last = r["period_end"] == court["period_end"][-1]
            if first_census_year is None or not (r["period_end"].endswith("12-31") or last):
                continue
            if cut.year >= first_census_year:
                rows.append(
                    _row(
                        "non-immigration",
                        "filings, year to date",
                        r["period_end"],
                        r["commenced_nonimm"],
                        census.filter(in_ytd).height,
                        None,
                        None,
                        "our census of court files, registrations excluded",
                    )
                )
            # endings of files opened before the census began are missing in its first years
            if cut.year >= first_census_year + 4:
                ended = census.filter(pl.col("final_disposition_date").is_between(jan1, cut))
                rows.append(
                    _row(
                        "non-immigration",
                        "dispositions, year to date",
                        r["period_end"],
                        r["dispositions_nonimm"],
                        ended.height,
                        None,
                        None,
                        f"our census of court files opened from {first_census_year}, "
                        "registrations excluded",
                    )
                )

    out = pl.DataFrame(rows, schema=SCHEMA)
    return out.with_columns(
        (pl.col("ours") / pl.col("court_published")).round(3).alias("ratio"),
        pl.lit(
            "court-published figure against our count from court-file records; same registry, "
            "not an outside count; docket-derived stocks run high because some endings are missed"
        ).alias("bias_statement"),
    ).sort(["component", "measure", "period_end"])
