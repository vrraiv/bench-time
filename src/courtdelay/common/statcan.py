"""Statistics Canada full-table downloads.

Each table is one request: ``GET https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip``, a zip
holding ``{pid}.csv`` (long format) and ``{pid}_MetaData.csv`` (title, reference period, archive
status, dimensions). The release time is the zip's ``Last-Modified`` header. We download whole
tables and filter locally. Licence: Statistics Canada Open Licence.

Until 2026-11-23 this went through the Web Data Service (``getCubeMetadata`` and
``getFullTableDownloadCSV``, which only returns the same zip URL). WDS was the less reliable part
during StatCan's November 2026 outages, so it is no longer used. During those outages every URL
answered 200 with an HTML "currently unavailable" page; anything that is not a zip is treated
as a temporary failure (retried, never cached). See docs/sources.md S1.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass

import polars as pl

from courtdelay.common import paths
from courtdelay.common.http import Client, Response

ZIP_URL = "https://www150.statcan.gc.ca/n1/tbl/csv/{pid}-eng.zip"
#: StatCan outages come and go server by server; retry for up to ~5 minutes per table.
ATTEMPTS = 5

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
class TableMeta:
    product_id: str
    title_en: str
    start: str
    end: str
    release_time: str  # zip Last-Modified header, as served
    archive_status: str
    dimensions: list[str]


def is_zip(content: bytes, content_type: str = "") -> bool:
    return content[:4] == b"PK"


def _not_a_zip(content: bytes, content_type: str) -> bool:
    return not is_zip(content)


def fetch_table_zip(
    client: Client, pid: int, *, source: str, vintage: str = "", refresh: bool = False
) -> Response:
    """Download the full-table zip for ``pid``. A 200 that is not a zip (StatCan's outage page)
    is retried and never cached; if it persists, FetchError is raised."""
    return client.get(
        ZIP_URL.format(pid=pid),
        source=source,
        vintage=vintage,
        refresh=refresh,
        transient=_not_a_zip,
        attempts=ATTEMPTS,
    )


def table_meta(zip_bytes: bytes, pid: int, *, release_time: str = "") -> TableMeta:
    """Read the header block of ``{pid}_MetaData.csv`` inside a table zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        text = zf.read(f"{pid}_MetaData.csv").decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    head = dict(zip(rows[0], rows[1], strict=False))
    dims: list[str] = []
    for i, row in enumerate(rows):
        if row[:2] == ["Dimension ID", "Dimension name"]:
            for r in rows[i + 1 :]:
                if not r or not r[0]:
                    break
                dims.append(r[1])
            break
    return TableMeta(
        product_id=head.get("Product Id", str(pid)),
        title_en=head.get("Cube Title", ""),
        start=head.get("Start Reference Period", ""),
        end=head.get("End Reference Period", ""),
        release_time=release_time,
        archive_status=head.get("Archive Status", ""),
        dimensions=dims,
    )


def cached_meta(resp: Response) -> dict:
    """The stored ``.meta.json`` record for a response (headers, fetched_at, sha256)."""
    return json.loads((resp.path.parent / f"{resp.path.stem}.meta.json").read_text())


def read_table_zip(data: bytes, pid: int) -> pl.DataFrame:
    """Read ``{pid}.csv`` out of a StatCan table zip into a DataFrame with all columns as strings
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
    """(path, meta) of the most recently fetched 2xx zip for ``pid`` under data/raw/<source>.
    Files that are not zips (outage pages cached before 2026-11-23) are skipped."""
    raw = paths.raw_dir(source)
    best = None
    for meta_file in raw.glob("*.meta.json"):
        meta = json.loads(meta_file.read_text())
        if not (meta["url"].endswith(f"{pid}-eng.zip") and 200 <= meta["status"] < 300):
            continue
        data = raw / meta["file"]
        if not data.exists():
            continue
        with data.open("rb") as fh:
            if not is_zip(fh.read(4)):
                continue
        if best is None or meta["fetched_at"] > best["fetched_at"]:
            best = meta
    if best is None:
        raise FileNotFoundError(f"no cached zip for {pid} under {raw}; run fetch first")
    return raw / best["file"], best
