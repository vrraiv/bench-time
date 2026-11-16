"""Statistics Canada Web Data Service (WDS) helpers.

Verified 2026-11-15 (docs/sources.md S1): ``getCubeMetadata`` (POST, 8-digit productId) and
``getFullTableDownloadCSV/{pid}/en`` (GET, returns the URL of a zip holding ``{pid}.csv`` and
``{pid}_MetaData.csv``). We download whole tables and filter locally; it is one request per table
instead of thousands of vector calls. Licence: Statistics Canada Open Licence.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass

import polars as pl

from courtdelay.common import paths
from courtdelay.common.http import Client, Response

WDS = "https://www150.statcan.gc.ca/t1/wds/rest"

# Non-dimension columns in every full-table CSV. Everything else is a dimension.
FIXED_COLS = [
    "REF_DATE",
    "GEO",
    "DGUID",
    "UOM",
    "UOM_ID",
    "SCALAR_FACTOR",
    "SCALAR_ID",
    "VECTOR",
    "COORDINATE",
    "VALUE",
    "STATUS",
    "SYMBOL",
    "TERMINATED",
    "DECIMALS",
]


@dataclass(frozen=True)
class CubeMeta:
    product_id: str
    title_en: str
    start: str
    end: str
    release_time: str
    archive_status: str
    n_series: int
    dimensions: list[str]


def cube_metadata(client: Client, pid: int, *, source: str, vintage: str = "") -> CubeMeta:
    resp = client.post_json(
        f"{WDS}/getCubeMetadata", [{"productId": pid}], source=source, vintage=vintage
    )
    payload = resp.json()[0]
    if payload["status"] != "SUCCESS":
        raise RuntimeError(f"getCubeMetadata {pid}: {payload}")
    obj = payload["object"]
    return CubeMeta(
        product_id=obj["productId"],
        title_en=obj["cubeTitleEn"],
        start=obj["cubeStartDate"],
        end=obj["cubeEndDate"],
        release_time=obj["releaseTime"],
        archive_status=obj.get("archiveStatusEn", ""),
        n_series=int(obj.get("nbSeriesCube", 0)),
        dimensions=[d["dimensionNameEn"] for d in obj.get("dimension", [])],
    )


def fetch_full_table(client: Client, pid: int, *, source: str, vintage: str = "") -> Response:
    """Download the full-table CSV zip for ``pid`` (two requests: locator JSON, then zip)."""
    loc = client.get(f"{WDS}/getFullTableDownloadCSV/{pid}/en", source=source, vintage=vintage)
    payload = loc.json()
    if payload.get("status") != "SUCCESS":
        raise RuntimeError(f"getFullTableDownloadCSV {pid}: {payload}")
    return client.get(payload["object"], source=source, vintage=vintage)


def read_table_zip(data: bytes, pid: int) -> pl.DataFrame:
    """Read ``{pid}.csv`` out of a WDS zip into a DataFrame with all columns as strings
    except VALUE (float). Dimension columns are whatever is not in FIXED_COLS."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        member = f"{pid}.csv"
        if member not in names:
            raise ValueError(f"{member} not in zip ({names})")
        raw = zf.read(member)
    df = pl.read_csv(
        io.BytesIO(raw),
        infer_schema_length=0,  # everything as Utf8; we cast what we need
        encoding="utf8-lossy",
        quote_char='"',
    )
    df = df.rename({c: c.lstrip("﻿") for c in df.columns})
    return df.with_columns(pl.col("VALUE").cast(pl.Float64, strict=False))


def dimension_columns(df: pl.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in FIXED_COLS]


def tidy(
    df: pl.DataFrame, pid: int, *, geos: tuple[str, ...] = ("Canada", "Ontario")
) -> pl.DataFrame:
    """Filter to selected geographies and add product_id; keep dimension columns as-is."""
    dims = dimension_columns(df)
    cols = [
        "REF_DATE",
        "GEO",
        *dims,
        "UOM",
        "SCALAR_FACTOR",
        "VECTOR",
        "COORDINATE",
        "VALUE",
        "STATUS",
    ]
    out = (
        df.filter(pl.col("GEO").is_in(list(geos)))
        .select(cols)
        .rename({c: c.lower() for c in cols})
        .with_columns(pl.lit(str(pid)).alias("product_id"))
    )
    return out


def latest_cached_zip(source: str, pid: int):
    """(path, meta) of the most recently fetched 2xx zip for ``pid`` under data/raw/<source>."""
    raw = paths.raw_dir(source)
    best = None
    for meta_file in raw.glob("*.meta.json"):
        meta = json.loads(meta_file.read_text())
        if meta["url"].endswith(f"{pid}-eng.zip") and 200 <= meta["status"] < 300:
            if best is None or meta["fetched_at"] > best["fetched_at"]:
                best = meta
    if best is None:
        raise FileNotFoundError(f"no cached zip for {pid} under {raw}; run fetch first")
    return raw / best["file"], best
