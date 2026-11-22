from datetime import date

import polars as pl
import pytest

from courtdelay.estimate import benchmark, stock_flow


def _activity():
    rows = []
    for end, tot, imm in (
        ("2023-12-31", (1300, 1100, 900), (1000, 900, 600)),
        ("2024-06-30", (700, 500, 1100), (500, 350, 750)),
    ):
        for label, (c, d, p) in (
            ("Grand Total", tot),
            ("Immigration and Refugee (IMM) - Total", imm),
        ):
            rows.append(
                {
                    "court": "FC",
                    "period_start": f"{end[:4]}-01-01",
                    "period_end": end,
                    "subject_matter": label,
                    "commenced": c,
                    "dispositions": d,
                    "pending": p,
                }
            )
    return pl.DataFrame(rows)


def _file(prefix, year, number, filed, ended=None, registration=False):
    return {
        "division": "T",
        "prefix": prefix,
        "docket_year": year,
        "number": number,
        "date_filed": filed,
        "final_disposition_date": ended,
        "is_registration": registration,
    }


def _dockets():
    files = [
        # 2023 stratum: 4 sampled of 1,000 numbers; one still open at both cut-offs
        _file("IMM", 2023, 250, date(2023, 3, 1), date(2023, 9, 1)),
        _file("IMM", 2023, 500, date(2023, 6, 1), date(2024, 2, 1)),
        _file("IMM", 2023, 750, date(2023, 9, 1), date(2024, 8, 1)),
        _file("IMM", 2023, 1000, date(2023, 12, 1), None),
        # 2024 stratum: 4 sampled of 800 numbers; one dated in December 2023, two by 30 June
        _file("IMM", 2024, 10, date(2023, 12, 20), None),
        _file("IMM", 2024, 300, date(2024, 3, 1), date(2024, 5, 1)),
        _file("IMM", 2024, 500, date(2024, 6, 1), None),
        _file("IMM", 2024, 800, date(2024, 9, 1), None),
        # census of T files
        _file("T", 2023, 1, date(2023, 2, 1), date(2023, 5, 1)),
        _file("T", 2023, 2, date(2023, 4, 1), None),
        _file("T", 2023, 3, date(2023, 4, 2), None, registration=True),
        _file("T", 2024, 1, date(2024, 2, 1), None),
    ]
    return pl.DataFrame(files, schema_overrides={"final_disposition_date": pl.Date})


def _get(t, component, measure, period_end):
    return t.filter(
        (pl.col("component") == component)
        & (pl.col("measure") == measure)
        & (pl.col("period_end") == period_end)
    ).row(0, named=True)


def test_court_series_splits_immigration_and_checks_labels():
    s = benchmark.fc_court_series(_activity())
    assert s["pending_nonimm"].to_list() == [300, 350]
    assert s["commenced_nonimm"].to_list() == [300, 200]
    with pytest.raises(ValueError, match="immigration total"):
        benchmark.fc_court_series(_activity().filter(pl.col("subject_matter") == "Grand Total"))


def test_benchmark_scales_the_immigration_sample():
    t = benchmark.fc_benchmark(_activity(), _dockets(), None)
    # filings to 30 June 2024: 2 of 4 sampled files dated in 2024 by then, top number 800;
    # the file numbered -24 but dated December 2023 is not a 2024 filing
    r = _get(t, "immigration", "filings, year to date", "2024-06-30")
    assert (r["ours"], r["court_published"], r["ratio"]) == (400, 500, 0.8)
    assert r["ours_lo"] < 400 < r["ours_hi"]
    # the first sampled year is not benchmarked for flows or stock
    assert t.filter(
        pl.col("period_end") == "2023-12-31", pl.col("component") == "immigration"
    ).is_empty()
    # open at 30 June 2024: 2023 stratum 2 of 4 x 1,000, 2024 stratum 2 of 4 x 800
    r = _get(t, "immigration", "pending at period end", "2024-06-30")
    assert (r["ours"], r["court_published"]) == (900, 750)


def test_benchmark_counts_the_census_without_registrations():
    t = benchmark.fc_benchmark(_activity(), _dockets(), None)
    r = _get(t, "non-immigration", "filings, year to date", "2023-12-31")
    assert (r["ours"], r["court_published"]) == (2, 300)
    # dispositions wait until the census has run four years
    assert t.filter(pl.col("measure") == "dispositions, year to date").is_empty()


def test_steady_state_flag():
    df = pl.DataFrame(
        {
            "court": ["FC"] * 3,
            "subject_matter": ["TOTAL"] * 3,
            "period_end": ["2024-03-31", "2024-06-30", "2024-09-30"],
            "q_start": ["2024-01-01", "2024-04-01", "2024-07-01"],
            "commenced_q": [100, 300, 100],
            "dispositions_q": [100, 100, 0],
            "pending": [1000, 1200, 1300],
        }
    )
    w = stock_flow.littles_law(df)
    assert w["steady_state_ok"].to_list() == [True, False, None]


def test_benchmark_sets_aside_files_not_yet_numbered():
    t = benchmark.fc_benchmark(_activity(), _dockets(), None)
    # IMM-500-24 was filed on 1 June 2024, but IMM-300-24 before it was filed on 1 March and
    # nothing shows a later number issued by 30 June, so all open files count as numbered ...
    r = _get(t, "immigration", "pending at period end, files numbered by then", "2024-06-30")
    assert r["ours"] == 900
    # ... while a file filed before a lower-numbered one was numbered after its filing date
    late = _dockets().vstack(
        pl.DataFrame(
            [
                _file("IMM", 2024, 400, date(2024, 7, 15)),
                _file("IMM", 2024, 450, date(2024, 6, 20)),
            ],
            schema_overrides={"final_disposition_date": pl.Date},
        )
    )
    t = benchmark.fc_benchmark(_activity(), late, None)
    full = _get(t, "immigration", "pending at period end", "2024-06-30")["ours"]
    numbered = _get(t, "immigration", "pending at period end, files numbered by then", "2024-06-30")
    # IMM-450-24 (filed 20 June) and IMM-500-24 (1 June) follow IMM-400-24, filed 15 July
    assert full - numbered["ours"] == round(2 / 6 * 800)


def test_benchmark_adds_older_files_from_the_list_sample():
    # 4 fetched of 100 files in the frame: two still open, one ended in 2024, one in 2023
    older = pl.DataFrame(
        [
            {"frame_group": "2021", "frame_n": 100, **_file("IMM", 2021, n, date(2021, 5, 1), end)}
            for n, end in ((1, None), (2, None), (3, date(2024, 3, 1)), (4, date(2023, 5, 1)))
        ],
        schema_overrides={"final_disposition_date": pl.Date},
    )
    t = benchmark.fc_benchmark(_activity(), _dockets(), None, older)
    # older files still without an ending are not added to the stock
    assert t.filter(pl.col("measure").str.contains("older")).is_empty()
    # endings to 30 June 2024: 250 + 200 from the yearly samples, 25 from the older files
    r = _get(t, "immigration", "dispositions, year to date", "2024-06-30")
    assert (r["ours"], r["court_published"]) == (475, 350)
    # without the older sample neither row is produced
    t0 = benchmark.fc_benchmark(_activity(), _dockets(), None)
    assert (
        t0.filter(pl.col("measure").str.contains("dispositions"))
        .filter(pl.col("component") == "immigration")
        .is_empty()
    )
