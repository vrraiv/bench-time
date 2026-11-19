"""S10 + S11: Federal Court and Federal Court of Appeal dockets (Tier 2).

Verified 2026-11-16 from the Court's own page scripts (docs/sources.md S10): the "Court Files" page
calls JSON endpoints on www.fct-cf.ca with ``division`` = "t" (Federal Court) or "a" (Federal Court
of Appeal) and ``courtnumber`` (e.g. IMM-1234-23, T-567-24, A-89-25):

  GET /CourtFilesAndDecisions/proceedingQueriesAddInfo?division=&courtnumber=   file information
  GET /CourtFilesAndDecisions/proceedingQueriesRE?division=&courtnumber=        recorded entries

Two requests per file at the client's 4 s per-host spacing (single-threaded), every response cached
under data/raw/s10_fc_fca_dockets/ (gitignored, local only; responses include party names). The
parser keeps file number, dates, entry types and outcomes only; names are dropped at parse time.

Sampling plan (owner decision 2026-11-16; docs/methods.md E1):
  FCA ("A-")         census by filing year
  FC general ("T-")  census by filing year
  FC immigration     simple random sample of 1,000 files per filing year from 2023 on
                     (Refugee Law Lab covers 1997-2022)
Docket numbers are sequential within a year (N = 1, 2, ...). A census walks N upward and stops after
``STOP_AFTER_MISSES`` consecutive numbers that do not exist. A sample first finds the year's
highest existing N by galloping search, then draws N uniformly without replacement (seeded);
non-existent numbers are recorded as misses and replaced from the reserve draw.

Everything is resume-safe: the plan (sample lists, seeds, frame sizes) is written to
``plan_<stratum>.json`` before crawling, and the HTTP cache means a restarted run never re-fetches.
Progress is appended to ``progress_<stratum>.jsonl``. The client refuses all of this while
COURTDELAY_CONTACT is unset.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict, dataclass

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s10_fc_fca_dockets"
BASE = "https://www.fct-cf.ca/CourtFilesAndDecisions"
ADDINFO = f"{BASE}/proceedingQueriesAddInfo"
ENTRIES = f"{BASE}/proceedingQueriesRE"
TIER = 2
STOP_AFTER_MISSES = 200
SEED = 20261116


@dataclass(frozen=True)
class Stratum:
    name: str  # e.g. "FCA-2024"
    prefix: str  # "A", "T", "IMM"
    division: str  # "a" or "t"
    year: int  # filing year (4-digit)
    mode: str  # "census" | "sample"
    n_sample: int = 0

    def number(self, n: int) -> str:
        return f"{self.prefix}-{n}-{self.year % 100:02d}"


def default_plan(
    fca_years=range(2010, 2027), fc_general_years=range(2018, 2027), imm_years=range(2023, 2027)
) -> list[Stratum]:
    plan = [Stratum(f"FCA-{y}", "A", "a", y, "census") for y in fca_years]
    plan += [Stratum(f"FCT-{y}", "T", "t", y, "census") for y in fc_general_years]
    plan += [Stratum(f"IMM-{y}", "IMM", "t", y, "sample", 1000) for y in imm_years]
    # overlap sample (owner approval 2026-11-18): 300 files from the last filing year the Refugee
    # Law Lab series covers, to check that S4 and this source measure the same stages alike
    plan.append(Stratum("IMM-2022", "IMM", "t", 2022, "sample", 300))
    return plan


# -- requests -------------------------------------------------------------------------------


def _get(client: Client, url: str, s: Stratum, number: str):
    return client.get(
        url, source=SOURCE, tier=TIER, params={"division": s.division, "courtnumber": number}
    )


def exists(payload) -> bool:
    """True if an additional-info response describes a real file. The response shape is
    confirmed in the pilot; until then accept any non-empty 'data' list or non-empty object."""
    if payload is None:
        return False
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        return bool(data) if isinstance(data, list | dict) else bool(payload)
    if isinstance(payload, list):
        return len(payload) > 0
    return False


MAX_CONSECUTIVE_ERRORS = 5
_consecutive_errors = 0


class CrawlAborted(RuntimeError):
    """Raised after MAX_CONSECUTIVE_ERRORS failed requests in a row (site down, TLS failure,
    blocking). The cache keeps everything fetched so far; rerunning resumes."""


def _record_failure(s: Stratum, number: str, exc: Exception) -> None:
    global _consecutive_errors
    _consecutive_errors += 1
    with (paths.raw_dir(SOURCE) / f"failures_{s.name}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"docket": number, "error": str(exc)[:300]}) + "\n")
    log.warning("%s %s: %s", s.name, number, exc)
    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        raise CrawlAborted(
            f"{_consecutive_errors} consecutive request failures; last: {exc}"
        ) from exc


def fetch_file(client: Client, s: Stratum, n: int) -> bool | None:
    """Fetch both endpoints for one file number. Returns True (file exists, both fetched),
    False (no such file) or None (a request failed: neither a hit nor a miss; logged to
    failures_<stratum>.jsonl for a later retry)."""
    global _consecutive_errors
    number = s.number(n)
    try:
        info = _get(client, ADDINFO, s, number)
        try:
            payload = info.json()
        except ValueError:
            payload = None
        if not exists(payload):
            _consecutive_errors = 0
            return False
        _get(client, ENTRIES, s, number)
    except FetchError as exc:
        _record_failure(s, number, exc)
        return None
    _consecutive_errors = 0
    return True


def highest_number(client: Client, s: Stratum, hint: int = 1000) -> int:
    """Galloping then binary search for the highest existing N in a year. Files are sequential, so
    existence is (nearly) monotone; runs of missing numbers (withdrawn or sealed files) up to ~50
    long are tolerated by probing N, N+3, N+10, N+25 and N+50. Underestimating the frame would
    silently drop the year's latest filings, so this errs towards probing more."""

    def any_exists(n: int) -> bool:
        return any(fetch_file(client, s, n + k) is True for k in (0, 3, 10, 25, 50))

    lo, hi = 0, max(hint, 1)
    while any_exists(hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if any_exists(mid):
            lo = mid
        else:
            hi = mid
    return lo


def _progress(s: Stratum, row: dict) -> None:
    with (paths.raw_dir(SOURCE) / f"progress_{s.name}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def crawl_census(client: Client, s: Stratum, *, start: int = 1) -> dict:
    misses, n, found = 0, start, 0
    while misses < STOP_AFTER_MISSES:
        r = fetch_file(client, s, n)
        if r is True:
            found, misses = found + 1, 0
        elif r is False:
            misses += 1
        if n % 50 == 0:
            _progress(s, {"n": n, "found": found})
        n += 1
    result = {"stratum": s.name, "last_n_probed": n - 1, "found": found}
    _progress(s, {"done": True, **result})
    return result


def make_sample_plan(client: Client, s: Stratum, hint: int) -> dict:
    plan_path = paths.raw_dir(SOURCE) / f"plan_{s.name}.json"
    if plan_path.exists():
        return json.loads(plan_path.read_text())
    max_n = highest_number(client, s, hint)
    rng = random.Random(f"{SEED}-{s.name}")
    order = list(range(1, max_n + 1))
    rng.shuffle(order)
    plan = {"stratum": asdict(s), "frame_max_n": max_n, "seed": f"{SEED}-{s.name}", "order": order}
    plan_path.write_text(json.dumps(plan))
    return plan


def crawl_sample(client: Client, s: Stratum, hint: int = 8000) -> dict:
    plan = make_sample_plan(client, s, hint)
    found, tried = 0, 0
    for n in plan["order"]:
        if found >= s.n_sample:
            break
        tried += 1
        if fetch_file(client, s, n) is True:
            found += 1
        if tried % 50 == 0:
            _progress(s, {"tried": tried, "found": found})
    result = {"stratum": s.name, "frame_max_n": plan["frame_max_n"], "tried": tried, "found": found}
    _progress(s, {"done": True, **result})
    return result


def run_stratum(client: Client, s: Stratum) -> dict:
    return crawl_census(client, s) if s.mode == "census" else crawl_sample(client, s)


def fetch(client: Client, strata: list[str] | None = None) -> list[dict]:
    plan = default_plan()
    if strata:
        plan = [s for s in plan if s.name in strata]
    return [run_stratum(client, s) for s in plan]


# -- parse ---------------------------------------------------------------------------------

# Fields kept from the file-information record. STYLE_OF_CAUSE, Party and Ships are never read.
INFO_FIELDS = {
    "COURT_NO": "docket",
    "DIVISION": "division",
    "OFF_CD": "office",
    "PRCDG_TYPE": "proceeding_type_code",
    "ENGLISH_PROCEEDING_TYPE": "proceeding_type",
    "ENGLISH_NATURE_DESC": "nature",
    "ENGLISH_PROCEEDING_CLASS": "proceeding_class",
    "LANG_CD": "language",
}


def ms_date(v):
    """'/Date(1735794000000)/' (UTC milliseconds) -> local (Eastern) calendar date. The Court stores
    midnight Eastern, i.e. 04:00 or 05:00 UTC, so subtracting 5 hours gives the intended day."""
    import re
    from datetime import UTC, datetime, timedelta

    if not v:
        return None
    m = re.search(r"(-?\d+)", str(v))
    if not m:
        return None
    return (datetime.fromtimestamp(int(m.group(1)) / 1000, UTC) - timedelta(hours=5)).date()


def parse_file(info: dict, entries: list[dict], fetched_at: str) -> tuple[dict | None, list[dict]]:
    """One docket -> (docket row, entry rows), names dropped. Returns (None, []) for files with any
    entry flagged confidential (dropped per docs/HANDOFF.md section 6; counted by the caller)."""
    from courtdelay.sources import s4_rll_fc_dockets as s4

    if any(str(e.get("IS_CONFIDENTIAL", "N")).upper() == "Y" for e in entries):
        return None, []
    if any(s4.SEALED_RE.search(e.get("RECORDED_ENTRY") or "") for e in entries):
        return None, []
    docket = info.get("COURT_NO")
    docs = [
        {
            "RE_NO": e.get("RE_NO"),
            "DOC_DT": (e.get("DOC_DT") or "")[:10] or None,
            # the structured copy flag is more reliable than text rules
            "RECORDED_ENTRY": ("Copy of " if str(e.get("IS_COPY", "N")).upper() == "Y" else "")
            + (e.get("RECORDED_ENTRY") or ""),
        }
        for e in entries
    ]
    ents = s4.classify_docket_entries(docs, docket)
    track = next(
        (e.get("ENGLISH_TRACK_NAME") for e in entries if e.get("ENGLISH_TRACK_NAME")), None
    )
    prefix, num, yy = (docket.split("-") + [None, None])[:3] if docket else (None, None, None)
    row = {k_out: info.get(k_in) for k_in, k_out in INFO_FIELDS.items()}
    row.update(
        {
            "prefix": prefix,
            "number": int(num) if num and num.isdigit() else None,
            "docket_year": 2000 + int(yy) if yy and yy.isdigit() else None,
            "date_filed": ms_date(info.get("FILE_DT")),
            "track": track,
            "scraped": fetched_at[:10],
            **s4.derive_docket(ents),
        }
    )
    return row, [{k: v for k, v in e.items() if k != "_fixed"} for e in ents]


def _cached_pairs():
    """Yield ((division, docket), info record, entry records, fetched_at) from the cache."""
    from urllib.parse import parse_qs, urlsplit

    raw = paths.raw_dir(SOURCE)
    info, ents = {}, {}
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if not 200 <= meta["status"] < 300:
            continue
        q = parse_qs(urlsplit(meta["url"]).query)
        key = (q.get("division", [""])[0], q.get("courtnumber", [""])[0])
        target = info if "proceedingQueriesAddInfo" in meta["url"] else ents
        target[key] = (raw / meta["file"], meta["fetched_at"])
    for key, (path, fetched_at) in info.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("data"):
            continue
        if key not in ents:
            continue
        ep = json.loads(ents[key][0].read_text(encoding="utf-8"))
        yield key, payload["data"][0], ep.get("data") or [], fetched_at


def parse(client: Client | None = None):
    import polars as pl

    dockets, entries, dropped = [], [], 0
    for _key, info, ents, fetched_at in _cached_pairs():
        row, erows = parse_file(info, ents, fetched_at)
        if row is None:
            dropped += 1
            continue
        dockets.append(row)
        entries.extend(erows)
    out = paths.processed_dir() / "s10"
    out.mkdir(exist_ok=True)
    d = pl.DataFrame(dockets, infer_schema_length=None)
    e = pl.DataFrame(entries, infer_schema_length=None)
    if d.height:
        d.write_parquet(out / "dockets.parquet")
        e.write_parquet(out / "entries.parquet")
    log.info("S10: %d dockets parsed, %d dropped as confidential/sealed", d.height, dropped)
    return {"dockets": d, "entries": e, "dropped": dropped}


def validate(frames) -> None:
    import polars as pl

    d = frames["dockets"]
    if d.height == 0:
        raise ValueError("S10: no dockets parsed")
    by = (
        d.group_by(["prefix", "docket_year"])
        .agg(
            pl.len().alias("n"),
            pl.col("final_disposition_date").is_not_null().mean().alias("disposed_share"),
            (pl.col("date_filed").dt.year() != pl.col("docket_year"))
            .mean()
            .alias("filed_other_year"),
        )
        .sort(["prefix", "docket_year"])
    )
    log.info("S10 by stratum:\n%s", by)
    bad = d.filter(pl.col("date_filed").is_null()).height
    if bad > 0.01 * d.height:
        raise ValueError(f"S10: {bad} dockets without a filing date")
