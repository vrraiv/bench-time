"""Decision-to-docket linkage: join published decisions (S3) to court files (S10, later S4/S12).

A decision cites one or more court file numbers; a court file may produce many decisions (motions,
costs, the final judgment). The link is therefore kept at the grain *decision x file number*, and
each linked pair is then matched to the docket's own recorded entries:

* ``entry_match``    is there a judgment or order entry on (or within 7 days of) the decision date?
* ``decision_is_final``  the Registry's final-decision marker falls within 7 days of the decision
  date: the decision ended the file (otherwise it is interlocutory or a later costs ruling)
* ``hearing_match``  is there a recorded hearing entry on the decision's stated hearing dates?

Neither source overwrites the other: the output records agreement categories. Match rates are
reported against the docket *frame* (census strata only); a decision citing a file outside the
frame is ``out_of_frame``, never a miss. Sampled strata (FC immigration) are ``sample_frame``.

Per-decision rows stay in data/processed/links/ (never published); only aggregate match rates are
written as a derived table. No judge names and no party names are carried.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import polars as pl

FC_KEY_RE = re.compile(r"^(\d{2}-)?([A-Z]{1,4})-0*(\d{1,6})-(\d{2})$")

# hearing entries that are not a hearing of the proceeding itself
CONFERENCE_RE = r"conference|mediation|meeting|neutral evaluation|next steps"


def normalise_fc_key(raw: str | None) -> str | None:
    """'t-0123-19 ' -> 'T-123-19'. Returns None for truncated or malformed numbers. Numbers in the
    FCA's 'yy-A-n' form (motions before an appeal exists) have no docket in the census."""
    if not raw:
        return None
    m = FC_KEY_RE.match(raw.strip().upper().replace(" ", ""))
    if not m or m.group(1):
        return None
    return f"{m.group(2)}-{int(m.group(3))}-{m.group(4)}"


def key_year(key: str) -> int:
    yy = int(key.rsplit("-", 1)[1])
    return 2000 + yy if yy <= 40 else 1900 + yy


def decision_keys(
    meta: pl.DataFrame, courts: list[str], normalise: Callable[[str | None], str | None]
) -> pl.DataFrame:
    """One row per decision x cited file number, with a normalised key (null when malformed)."""
    d = (
        meta.filter(pl.col("court").is_in(courts))
        .with_columns(pl.coalesce("citation_en", "citation_fr").alias("decision_id"))
        .filter(pl.col("decision_id").is_not_null())
        .unique("decision_id", keep="first", maintain_order=True)
        .select(
            "decision_id",
            "court",
            "decision_date",
            "hearing_date",
            "hearing_last_date",
            "hearing_mode",
            "file_numbers",
        )
    )
    out = (
        d.with_columns(pl.col("file_numbers").str.split(";").alias("file_raw"))
        .with_columns(pl.col("file_raw").list.len().fill_null(0).alias("n_files_cited"))
        .explode("file_raw")
        .with_columns(
            pl.col("file_raw").map_elements(normalise, return_dtype=pl.String).alias("key")
        )
        .unique(["decision_id", "key"], keep="first", maintain_order=True)
        .drop("file_numbers")
    )
    return out


def fc_key_parts(key: str) -> tuple[str, int]:
    """'T-123-19' -> ('T', 2019)."""
    return key.split("-", 1)[0], key_year(key)


TCC_KEY_RE = re.compile(r"^(\d{4}|\d{2})-(\d{1,6})\(([A-Z]{2,4})\)(G|I|APP)?$")


def normalise_tcc_key(raw: str | None) -> str | None:
    """'2019-0123 (it) g' -> '2019-123(IT)G'. None when malformed."""
    if not raw:
        return None
    m = TCC_KEY_RE.match(raw.strip().upper().replace(" ", ""))
    if not m:
        return None
    year = m.group(1) if len(m.group(1)) == 4 else f"19{m.group(1)}"  # two digits: 1990s
    return f"{year}-{int(m.group(2))}({m.group(3)}){m.group(4) or ''}"


def tcc_key_parts(key: str) -> tuple[str, int]:
    """'2019-123(IT)G' -> ('TCC', 2019): Tax Court numbers carry the year first."""
    return "TCC", int(key[:4])


def _frame_status(key: str | None, census: dict, sample: dict, key_parts) -> str:
    if key is None:
        return "bad_key"
    prefix, year = key_parts(key)
    if prefix in census and census[prefix][0] <= year <= census[prefix][1]:
        return "in_frame"
    if prefix in sample and sample[prefix][0] <= year <= sample[prefix][1]:
        return "sample_frame"
    return "out_of_frame"


def _nearest(pairs: pl.DataFrame, events: pl.DataFrame, on: str, name: str) -> pl.DataFrame:
    """For each (decision_id, key) the event on the same docket nearest to date ``on``.
    Returns decision_id, key, <name>_date, <name>_gap_days (event minus ``on``), extra columns."""
    j = (
        pairs.select("decision_id", "key", on)
        .filter(pl.col(on).is_not_null())
        .join(events, left_on="key", right_on="docket", how="inner")
        .with_columns((pl.col("entry_date") - pl.col(on)).dt.total_days().alias("gap"))
        .with_columns(pl.col("gap").abs().alias("absgap"))
        .sort(["decision_id", "key", "absgap", "gap"])
        .unique(["decision_id", "key"], keep="first", maintain_order=True)
    )
    extra = [c for c in events.columns if c not in ("docket", "entry_date")]
    return j.select(
        "decision_id",
        "key",
        pl.col("entry_date").alias(f"{name}_date"),
        pl.col("gap").alias(f"{name}_gap_days"),
        *[pl.col(c).alias(f"{name}_{c}") for c in extra],
    )


def _match_cat(gap: str) -> pl.Expr:
    return (
        pl.when(pl.col(gap).is_null())
        .then(pl.lit("none"))
        .when(pl.col(gap) == 0)
        .then(pl.lit("exact"))
        .when(pl.col(gap).abs() <= 7)
        .then(pl.lit("within_7d"))
        .otherwise(pl.lit("none"))
    )


def link_decisions(
    keys: pl.DataFrame,
    dockets: pl.DataFrame,
    entries: pl.DataFrame,
    *,
    census: dict[str, tuple[int, int]],
    sample: dict[str, tuple[int, int]] | None = None,
    dropped: pl.DataFrame | None = None,
    key_parts: Callable[[str], tuple[str, int]] = fc_key_parts,
) -> pl.DataFrame:
    """Left-join decision keys to dockets and match each linked pair to docket entries.

    ``status``: linked | sealed_dropped (file exists but we drop it) | in_frame_no_docket |
    sample_frame (file in a sampled stratum, not drawn) | out_of_frame | bad_key.
    """
    assert dockets["docket"].n_unique() == dockets.height, "docket ids must be unique"
    n0 = keys.height
    dk = dockets.select(
        pl.col("docket").alias("key"),
        pl.lit(True).alias("_has_docket"),
        "date_filed",
        "proceeding_type",
        "nature",
        "final_disposition_date",
        pl.col("hearing_date").alias("docket_first_hearing_date"),
        pl.col("judgment_date").alias("docket_first_judgment_date"),
    )
    sealed = set(dropped["docket"]) if dropped is not None else set()
    out = keys.join(dk, on="key", how="left")
    assert out.height == n0, "join must not duplicate decision rows"
    frame = [_frame_status(k, census, sample or {}, key_parts) for k in out["key"]]
    prefix = [key_parts(k)[0] if k is not None else None for k in out["key"]]
    out = out.with_columns(
        pl.Series("_frame", frame), pl.Series("prefix", prefix, dtype=pl.String)
    ).with_columns(
        pl.when(pl.col("_has_docket").fill_null(False))
        .then(pl.lit("linked"))
        .when(pl.col("key").is_in(list(sealed)))
        .then(pl.lit("sealed_dropped"))
        .when(pl.col("_frame") == "in_frame")
        .then(pl.lit("in_frame_no_docket"))
        .otherwise(pl.col("_frame"))
        .alias("status"),
        (pl.col("_frame") == "in_frame").alias("in_census_frame"),
    )

    linked = out.filter(pl.col("status") == "linked")
    # judgment or order entry nearest the decision date
    jo = entries.filter(pl.col("entry_type").is_in(["judgment", "order"])).select(
        "docket", "entry_date", "entry_type"
    )
    m_entry = _nearest(linked, jo, "decision_date", "entry")
    # the Registry's final-decision marker nearest the decision date (sources without the marker,
    # such as the Tax Court, leave decision_is_final null)
    if "is_final" in entries.columns:
        fin = entries.filter(pl.col("is_final")).select("docket", "entry_date")
    else:
        fin = entries.clear().select("docket", "entry_date")
    m_final = _nearest(linked, fin, "decision_date", "final")
    # recorded hearing entries: nearest to the decision's (last) hearing date
    he = entries.filter(pl.col("entry_type") == "hearing").select(
        "docket",
        "entry_date",
        pl.col("hearing_subject").fill_null("unspecified").alias("subject"),
    )
    m_hear = _nearest(linked, he, "hearing_last_date", "hearing")
    out = (
        out.join(m_entry, on=["decision_id", "key"], how="left")
        .join(m_final, on=["decision_id", "key"], how="left")
        .join(m_hear, on=["decision_id", "key"], how="left")
    )
    assert out.height == n0
    is_linked = pl.col("status") == "linked"
    out = out.with_columns(
        pl.when(is_linked).then(_match_cat("entry_gap_days")).alias("entry_match"),
        pl.when(is_linked & pl.col("hearing_last_date").is_not_null())
        .then(_match_cat("hearing_gap_days"))
        .alias("hearing_match"),
        pl.when(is_linked & pl.lit("is_final" in entries.columns))
        .then(pl.col("final_gap_days").abs().le(7).fill_null(False))
        .alias("decision_is_final"),
        pl.when(is_linked)
        .then(pl.col("hearing_subject").str.contains(CONFERENCE_RE).fill_null(False))
        .alias("hearing_entry_is_conference"),
        # the decision header's own dates are suspect when they precede the file
        (pl.col("hearing_date") < pl.col("date_filed")).alias("s3_hearing_before_filing"),
        (pl.col("hearing_last_date") < pl.col("date_filed")).alias("s3_last_hearing_before_filing"),
        (pl.col("decision_date") - pl.col("date_filed"))
        .dt.total_days()
        .alias("filing_to_decision_days"),
    )
    return out.drop("_has_docket", "_frame")


def match_rates(links: pl.DataFrame, min_n: int = 0) -> pl.DataFrame:
    """Aggregate match rates by court, file prefix and decision year (census frame only)."""
    f = links.filter(pl.col("in_census_frame")).with_columns(
        pl.col("decision_date").dt.year().alias("decision_year"),
    )
    lk = pl.col("status") == "linked"
    return (
        f.group_by("court", "prefix", "decision_year")
        .agg(
            pl.len().alias("n_decision_files"),
            lk.mean().alias("linked_share"),
            (pl.col("status") == "sealed_dropped").mean().alias("sealed_dropped_share"),
            (pl.col("status") == "in_frame_no_docket").mean().alias("no_docket_share"),
            (pl.col("entry_match") == "exact").sum().alias("_e0"),
            (pl.col("entry_match") != "none").sum().alias("_e7"),
            pl.col("hearing_match").is_not_null().sum().alias("n_with_hearing_date"),
            (pl.col("hearing_match") == "exact").sum().alias("_h0"),
            (pl.col("hearing_match").is_in(["exact", "within_7d"])).sum().alias("_h7"),
            lk.sum().alias("n_linked"),
        )
        .with_columns(
            (pl.col("_e0") / pl.col("n_linked")).alias("entry_exact_share"),
            (pl.col("_e7") / pl.col("n_linked")).alias("entry_within_7d_share"),
            (pl.col("_h0") / pl.col("n_with_hearing_date")).alias("hearing_exact_share"),
            (pl.col("_h7") / pl.col("n_with_hearing_date")).alias("hearing_within_7d_share"),
        )
        .drop("_e0", "_e7", "_h0", "_h7")
        .filter(pl.col("n_decision_files") >= min_n)  # published tables: no tiny cells
        .sort("court", "prefix", "decision_year")
    )
