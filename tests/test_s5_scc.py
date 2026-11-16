import polars as pl

from courtdelay.common import paths
from courtdelay.sources import s5_scc_statistics as s5

FIX = paths.fixtures_dir("s5") / "stat-2025.html"


def test_parse_stat_page():
    df = s5.parse_html(FIX.read_bytes(), page_year=2025, url="fixture")
    assert df["year"].min() == 2016 and df["year"].max() == 2025
    assert df["page_as_of"][0] == "September 25, 2026"
    assert set(df["section"].unique()) >= {
        "Cases filed",
        "Applications for leave",
        "Appeals heard",
        "Appeal judgments",
        "Average time lapses (in months)",
    }
    tl = df.filter(pl.col("section") == "Average time lapses (in months)")
    assert tl.height == 30  # 3 stages x 10 years
    hj = tl.filter(pl.col("item") == "Between hearing and judgment").sort("year")
    assert hj["value"].to_list() == [4.8, 4.6, 4.8, 5.3, 5.4, 4.2, 4.6, 5.5, 6.3, 5.1]
    leave = df.filter(
        (pl.col("section") == "Cases filed")
        & (pl.col("item") == "Complete applications for leave to appeal")
        & (pl.col("year") == 2025)
    )
    assert leave["value"][0] == 517


def test_time_lapse_stage_mapping():
    items = [
        "Between filing of application for leave and decision on application for leave",
        "Between date leave granted (or date notice of appeal as of right filed) and hearing",
        "Between hearing and judgment",
    ]
    stages = [next(k for k, rx in s5.TIME_LAPSE_ITEMS.items() if rx.search(i)) for i in items]
    assert stages == ["leave_filing_to_leave_decision", "leave_to_hearing", "hearing_to_judgment"]


def test_missing_table_raises():
    import pytest

    with pytest.raises(ValueError):
        s5.parse_html("<html><body><table><tr><td>x</td></tr></table></body></html>", page_year=1)


def test_archived_cat5_page():
    df = s5.parse_archived_cat5((paths.fixtures_dir("s5") / "cat5_archived_2013.html").read_bytes())
    assert df.height == 33 and df["year"].min() == 2002 and df["year"].max() == 2012
    hj = df.filter(pl.col("item") == "Between hearing and judgment").sort("year")
    assert hj["value"][0] == 5.6 and hj["value"][-1] == 6.4
    stages = {
        next(k for k, rx in s5.TIME_LAPSE_ITEMS.items() if rx.search(i))
        for i in df["item"].unique()
    }
    assert stages == set(s5.TIME_LAPSE_ITEMS)
