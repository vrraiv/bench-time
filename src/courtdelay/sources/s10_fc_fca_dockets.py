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


def fetch_file(client: Client, s: Stratum, n: int) -> bool:
    """Fetch both endpoints for one file number; returns whether the file exists."""
    number = s.number(n)
    try:
        info = _get(client, ADDINFO, s, number)
    except FetchError as exc:
        log.warning("%s %s: %s", s.name, number, exc)
        return False
    try:
        payload = info.json()
    except ValueError:
        payload = None
    if not exists(payload):
        return False
    _get(client, ENTRIES, s, number)
    return True


def highest_number(client: Client, s: Stratum, hint: int = 1000) -> int:
    """Galloping then binary search for the highest existing N in a year. Files are sequential, so
    existence is (nearly) monotone; runs of missing numbers (withdrawn or sealed files) up to ~50
    long are tolerated by probing N, N+3, N+10, N+25 and N+50. Underestimating the frame would
    silently drop the year's latest filings, so this errs towards probing more."""

    def any_exists(n: int) -> bool:
        return any(fetch_file(client, s, n + k) for k in (0, 3, 10, 25, 50))

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
        if fetch_file(client, s, n):
            found, misses = found + 1, 0
        else:
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
        if fetch_file(client, s, n):
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


def parse(client: Client | None = None):
    raise NotImplementedError(
        "S10 parser is written after the pilot shows the JSON response format (no names kept)"
    )


def validate(_):
    raise NotImplementedError
