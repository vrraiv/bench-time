import polars as pl
import pytest

from courtdelay.common import paths
from courtdelay.sources import s7_ocj_statistics as s7

FIX = paths.fixtures_dir("s7")
pytest.importorskip("openpyxl")


def meta(name: str) -> dict:
    series = (
        "offence_based"
        if "Offence" in name
        else "disposition_rate"
        if "Disposition" in name
        else "clearance_rate"
    )
    return {
        "url": f"https://www.ontariocourts.ca/ocj/files/stats/crim/{name[:4]}/{name}",
        "year": int(name[:4]),
        "series": series,
        "case_type": "all",
        "ext": name.rsplit(".", 1)[1],
    }


def test_parse_period_and_unit_type():
    assert s7.parse_period("April 2025 to March 2026") == ("2025-04-01", "2026-03-31")
    assert s7.parse_period("January 2019 to December 2019") == ("2019-01-01", "2019-12-31")
    assert s7.unit_type("Provincial Overview") == "province"
    assert s7.unit_type("Central East Overview") == "region"
    assert s7.unit_type("Barrie") == "courthouse"


def test_offence_based_xlsx_2026():
    name = "2026-Offence-Based-Criminal.xlsx"
    df = pl.DataFrame(s7.parse_offence_xlsx((FIX / name).read_bytes(), meta(name)))
    prov = df.filter((pl.col("unit_type") == "province") & (pl.col("offence_type") == "TOTAL"))
    assert prov["period_start"][0] == "2025-04-01" and prov["period_end"][0] == "2026-03-31"
    row = prov.filter(pl.col("offence_group") == "Crimes Against the Person").row(0, named=True)
    assert (row["received"], row["disposed"], row["avg_days"], row["pending"]) == (
        79678,
        76000,
        242,
        59899,
    )
    assert set(df["unit"]) == {"Provincial Overview", "Central East Overview"}


def test_offence_based_pdf_2019():
    name = "2019-Offence-Based-Criminal.pdf"
    df = pl.DataFrame(s7.parse_offence_pdf((FIX / name).read_bytes(), meta(name)))
    prov = df.filter(
        (pl.col("unit") == "Provincial Overview") & (pl.col("offence_type") == "TOTAL")
    )
    row = prov.filter(pl.col("offence_group") == "Crimes Against the Person").row(0, named=True)
    assert (row["received"], row["disposed"], row["avg_days"], row["avg_appearances"]) == (
        66327,
        55876,
        199,
        9.4,
    )
    assert row["period_start"] == "2019-01-01" and row["period_end"] == "2019-12-31"
    assert row["trial_rate"] == pytest.approx(0.075)


def test_disposition_rate_xlsx_and_pdf():
    name = "2026-Disposition-Rate-Criminal.xlsx"
    df = pl.DataFrame(
        s7.parse_monthly_xlsx((FIX / name).read_bytes(), meta(name), s7.DR_COLS, "dr")
    )
    r = df.filter((pl.col("unit_type") == "province") & (pl.col("month") == "2024-04")).row(
        0, named=True
    )
    assert (r["pct_under_10m"], r["avg_appearances"], r["avg_days_all"]) == (0.808, 8.5, 175)
    name = "2019-Disposition-Rate-Criminal.pdf"
    df = pl.DataFrame(s7.parse_monthly_pdf((FIX / name).read_bytes(), meta(name), s7.DR_COLS, "dr"))
    r = df.filter(
        (pl.col("unit") == "Ontario Overview")
        & (pl.col("month") == "2018-01")
        & pl.col("avg_days_all").is_not_null()
    ).row(0, named=True)
    assert (r["pct_under_10m"], r["pct_over_18m"], r["avg_days_all"]) == (0.851, 0.033, 151)


def test_clearance_rate_xlsx():
    name = "2026-Clearance-Rate-Criminal.xlsx"
    df = pl.DataFrame(
        s7.parse_monthly_xlsx((FIX / name).read_bytes(), meta(name), s7.CR_COLS, "cr")
    )
    r = df.filter((pl.col("unit_type") == "province") & (pl.col("month") == "2024-04")).row(
        0, named=True
    )
    assert (r["received"], r["disposed"], r["net_received_less_disposed"]) == (21265, 22053, -788)
