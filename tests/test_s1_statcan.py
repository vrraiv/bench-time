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


META_CSV = """\ufeff"Cube Title","Product Id","CANSIM Id",URL,"Cube Notes","Archive Status",Frequency,"Start Reference Period","End Reference Period","Total number of dimensions"
"Civil court cases, by level of court and type of case","35100112","259-0011","https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3510011201",1,"CURRENT - a cube available to the public and that is current","Annual","2005-01-01","2024-01-01","4",

"Dimension ID","Dimension name","Dimension Notes","Dimension Definitions"
"1","Geography",,""
"2","Level of court",,""

"Dimension ID","Member Name","Classification Code"
"1","Canada","[11124]"
"""  # noqa: E501


def test_table_meta_from_zip():
    """Header layout copied from a real 35-10-0112 metadata file (public, no names)."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("35100112_MetaData.csv", META_CSV.encode("utf-8"))
    meta = statcan.table_meta(buf.getvalue(), 35100112, release_time="Thu, 26 Mar 2026")
    assert meta.product_id == "35100112"
    assert meta.title_en == "Civil court cases, by level of court and type of case"
    assert (meta.start, meta.end) == ("2005-01-01", "2024-01-01")
    assert meta.archive_status.startswith("CURRENT")
    assert meta.release_time == "Thu, 26 Mar 2026"
    assert meta.dimensions == ["Geography", "Level of court"]


def test_latest_cached_zip_skips_outage_pages(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("COURTDELAY_DATA_DIR", str(tmp_path))
    raw = paths.raw_dir("s_test")
    url = statcan.ZIP_URL.format(pid=35100029)
    (raw / "good.zip").write_bytes(FIX.read_bytes())
    (raw / "bad.html").write_bytes(b"<!DOCTYPE html>currently unavailable")
    for key, fname, when in [("good", "good.zip", "2026-11-16"), ("bad", "bad.html", "2026-11-23")]:
        (raw / f"{key}.meta.json").write_text(
            json.dumps({"url": url, "status": 200, "file": fname, "fetched_at": when})
        )
    path, meta = statcan.latest_cached_zip("s_test", 35100029)
    assert path.name == "good.zip" and meta["fetched_at"] == "2026-11-16"
