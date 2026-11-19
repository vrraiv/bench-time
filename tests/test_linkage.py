from datetime import date

import polars as pl

from courtdelay.estimate import linkage as lk


def test_normalise_fc_key():
    assert lk.normalise_fc_key(" t-0123-19") == "T-123-19"
    assert lk.normalise_fc_key("IMM-12345-23") == "IMM-12345-23"
    assert lk.normalise_fc_key("T-12") is None  # truncated
    assert lk.normalise_fc_key("08-A-12") is None  # FCA pre-appeal motion number
    assert lk.normalise_fc_key(None) is None
    assert lk.key_year("A-5-98") == 1998 and lk.key_year("T-5-24") == 2024


def _meta():
    rows = [
        # final judgment on a census file, hearing recorded on the docket
        ("2020 FC 1", "FC", date(2020, 6, 1), date(2020, 3, 2), date(2020, 3, 3), "T-10-19"),
        # interlocutory decision on the same file; two files cited, one malformed
        ("2019 FC 9", "FC", date(2019, 9, 1), None, None, "T-10-19;T-12"),
        ("2021 FC 2", "FC", date(2021, 1, 5), date(2020, 12, 1), date(2020, 12, 1), "T-77-20"),
        ("2021 FC 3", "FC", date(2021, 2, 5), None, None, "T-78-20"),  # dropped as sealed
        ("2012 FC 4", "FC", date(2012, 2, 5), None, None, "T-5-11"),  # before the census
        ("2024 FC 5", "FC", date(2024, 2, 5), None, None, "IMM-5-23"),  # sampled stratum
    ]
    return pl.DataFrame(
        [
            {
                "citation_en": c,
                "citation_fr": None,
                "court": court,
                "decision_date": dd,
                "hearing_date": h0,
                "hearing_last_date": h1,
                "hearing_mode": None,
                "file_numbers": f,
            }
            for c, court, dd, h0, h1, f in rows
        ],
        schema_overrides={"citation_fr": pl.String, "hearing_mode": pl.String},
    )


def test_link_statuses_and_entry_matches():
    dockets = pl.DataFrame(
        {
            "docket": ["T-10-19"],
            "date_filed": [date(2019, 1, 4)],
            "proceeding_type": ["Application"],
            "nature": ["synthetic"],
            "final_disposition_date": [date(2020, 6, 1)],
            "hearing_date": [date(2019, 8, 1)],
            "judgment_date": [date(2019, 9, 3)],
        }
    )
    entries = pl.DataFrame(
        {
            "docket": ["T-10-19"] * 4,
            "entry_date": [
                date(2019, 9, 3),
                date(2020, 3, 3),
                date(2020, 6, 1),
                date(2019, 8, 1),
            ],
            "entry_type": ["order", "hearing", "judgment", "hearing"],
            "hearing_subject": [None, "judicial_review", None, "case management conference"],
        }
    )
    keys = lk.decision_keys(_meta(), ["FC"], lk.normalise_fc_key)
    assert keys.height == 7
    out = lk.link_decisions(
        keys,
        dockets,
        entries,
        census={"T": (2018, 2026)},
        sample={"IMM": (2023, 2026)},
        dropped=pl.DataFrame({"docket": ["T-78-20"]}),
    )
    assert out.height == 7
    st = {(r["decision_id"], r["file_raw"]): r for r in out.iter_rows(named=True)}
    final = st[("2020 FC 1", "T-10-19")]
    assert final["status"] == "linked" and final["entry_match"] == "exact"
    assert final["hearing_match"] == "exact" and final["is_last_judgment"] is True
    assert final["hearing_entry_is_conference"] is False
    assert final["filing_to_decision_days"] == 514
    inter = st[("2019 FC 9", "T-10-19")]
    assert inter["entry_match"] == "within_7d" and inter["is_last_judgment"] is False
    assert inter["hearing_match"] is None  # the decision states no hearing date
    assert st[("2019 FC 9", "T-12")]["status"] == "bad_key"
    assert st[("2021 FC 2", "T-77-20")]["status"] == "in_frame_no_docket"
    assert st[("2021 FC 3", "T-78-20")]["status"] == "sealed_dropped"
    assert st[("2012 FC 4", "T-5-11")]["status"] == "out_of_frame"
    assert st[("2024 FC 5", "IMM-5-23")]["status"] == "sample_frame"
    rates = lk.match_rates(out)
    # census frame only: the 2012 and immigration decisions are not counted as misses
    assert rates["n_decision_files"].sum() == 4
    assert "judges_line" not in out.columns
