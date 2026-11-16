import polars as pl

from courtdelay.common import paths, statcan
from courtdelay.sources import s1_statcan_iccs as s1

FIX = paths.fixtures_dir("s1") / "35100029-eng.zip"


def test_read_and_tidy_fixture():
    df = statcan.read_table_zip(FIX.read_bytes(), 35100029)
    assert statcan.dimension_columns(df) == [
        "Offences",
        "Age of accused",
        "Sex of accused",
        "Type of case",
        "Statistics",
    ]
    tidy = statcan.tidy(df, 35100029)
    assert set(tidy["geo"].unique()) == {"Canada", "Ontario"}
    assert tidy["product_id"][0] == "35100029"
    # Ontario, all adults, total cases, median days in 2024/2025 is a plausible number
    med = tidy.filter(
        (pl.col("geo") == "Ontario")
        & (pl.col("ref_date") == "2024/2025")
        & (pl.col("type of case") == "Total cases")
        & (pl.col("statistics") == "Median")
    )
    assert med.height == 1
    assert 30 <= med["value"][0] <= 1000
    assert med["uom"][0] == "Days"


def test_validate_passes_on_fixture():
    df = statcan.read_table_zip(FIX.read_bytes(), 35100029)
    s1.validate({35100029: statcan.tidy(df, 35100029)})
