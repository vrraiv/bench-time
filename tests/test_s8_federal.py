import polars as pl

from courtdelay.common import paths
from courtdelay.sources import s8_federal_workload as s8

FIX = paths.fixtures_dir("s8")


def test_date_from_text():
    assert s8._date_from_text("Activity Summary - January 1, 2026 to March 31, 2026") == (
        "2026-01-01",
        "2026-03-31",
    )
    assert s8._date_from_text("January 1st to December 31 2010") == ("2010-01-01", "2010-12-31")
    assert s8._date_from_text("From January 1 to June 30, 2025") == ("2025-01-01", "2025-06-30")
    assert s8._date_from_text("no dates here") == (None, None)


def test_fc_2026_layout_with_colspan_header():
    url = "https://www.fct-cf.ca/en/pages/about-the-court/reports-and-statistics/statistics-march-31-2026"
    rows = s8.parse_fc_page((FIX / "fc_2026-03-31.html").read_bytes(), url)
    assert len(rows) == 20
    total = next(r for r in rows if r["subject_matter"] == "Grand Total")
    assert (
        total["commenced"],
        total["dispositions"],
        total["pending"],
        total["leave_granted"],
    ) == (
        7942,
        5176,
        30821,
        559,
    )
    assert total["period_start"] == "2026-01-01" and total["period_end"] == "2026-03-31"


def test_fc_2010_layout():
    url = "https://www.fct-cf.ca/en/pages/about-the-court/reports-and-statistics/statistics-december-31-2010"
    rows = s8.parse_fc_page((FIX / "fc_2010-12-31.html").read_bytes(), url)
    total = next(r for r in rows if r["subject_matter"] == "TOTAL FEDERAL COURT")
    assert (total["commenced"], total["dispositions"], total["pending"]) == (9386, 9337, 5156)
    assert total["period_end"] == "2010-12-31"
    imm = next(r for r in rows if r["subject_matter"] == "Total Immigration")
    assert imm["leave_granted"] == 1256


def test_fca_page():
    df = pl.DataFrame(
        s8.parse_fca_page((FIX / "fca_stats_excerpt.html").read_bytes()), schema=s8.SCHEMA
    )
    assert df["period_end"].n_unique() == 2
    q1 = df.filter((pl.col("period_end") == "2026-03-31") & (pl.col("subject_matter") == "TOTAL"))
    assert q1.select(["commenced", "dispositions", "pending"]).row(0) == (107, 116, 478)


def test_tcc_workload():
    df = s8.parse_tcc_page((FIX / "tcc_workload.html").read_bytes())
    assert set(df["fiscal_year"]) == {"2018-19", "2019-20", "2020-21", "2021-22", "2022-23"}
    filed = df.filter(
        pl.col("metric").str.starts_with("Proceedings Instituted")
        & (pl.col("fiscal_year") == "2022-23")
    )
    assert filed["value"][0] == 3230
