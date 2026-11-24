"""``courtdelay refresh``: the weekly incremental fetch for the docket sources (S10, S12, S13).

Owner decisions 2026-11-19: weekly, overnight on Sunday; each run fetches new filings and
re-checks one rotating slice of the files that were still open, so every open file is re-checked
once every ``SLICES`` weeks; parsing and rebuilding the tables happens monthly. Registered
tribunal decisions and certificates are never re-checked (they do not close).

A re-check replaces the cached copy of a file in place (``refresh=True``), so the cache always
holds one copy per file, the latest. A failed or empty answer never replaces a good copy
(see ``Client.request``). Earlier states of a file live in the restic backup snapshots.

One process per host: run ``fc``, ``tcc`` and ``scc`` as three processes. Rates are the
per-host limits in ``common/http.py``; this module adds no requests beyond the two endpoints the
census already uses. Five failed requests in a row stop the run (site down or blocking).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, date, datetime
from urllib.parse import unquote

import polars as pl

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError
from courtdelay.sources import s10_fc_fca_dockets as s10
from courtdelay.sources import s12_tcc_dockets as s12
from courtdelay.sources import s13_scc_cases as s13

log = logging.getLogger(__name__)

SLICES = 4
MAX_CONSECUTIVE_ERRORS = 5


class RefreshAborted(RuntimeError):
    """Too many failed requests in a row; the run stops and reports."""


def week_slice(today: date, slices: int = SLICES) -> int:
    return today.isocalendar().week % slices


def in_slice(key: str, k: int, slices: int = SLICES) -> bool:
    """Stable assignment of a file number to a slice (independent of run order)."""
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % slices == k


def _has_rows(content: bytes) -> bool:
    try:
        return bool(json.loads(content).get("data"))
    except (ValueError, AttributeError):
        return False


# A year listing that comes back with far fewer files than the copy we hold is refused: the
# cached copy is kept and the request counts as a failure, so a listing that shrinks across the
# board stops the run. (Between 16 and 19 November 2026 the Tax Court's listings lost 84% of
# their files; the refresh accepted them because they still had rows.)
LISTING_MIN_SHARE = 0.8
LISTING_MIN_BEFORE = 20


def _keeps_most(n_before: int):
    """accept() for a listing that held ``n_before`` files when last read."""

    def accept(content: bytes) -> bool:
        try:
            n = len(json.loads(content).get("data") or [])
        except (ValueError, AttributeError):
            return False
        if n_before < LISTING_MIN_BEFORE:
            return n > 0
        return n >= LISTING_MIN_SHARE * n_before

    return accept


class _Run:
    """Counters, error budget and time budget shared by the steps of one run."""

    def __init__(self, court: str, max_minutes: float | None, clock=time.monotonic):
        self.court = court
        self.started = datetime.now(UTC).isoformat(timespec="seconds")
        self._clock = clock
        self._deadline = clock() + max_minutes * 60 if max_minutes else None
        self.errors_in_a_row = 0
        self.stats: dict[str, int] = {}

    def add(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def ok(self) -> None:
        self.errors_in_a_row = 0

    def failed(self, what: str, exc: Exception) -> None:
        self.errors_in_a_row += 1
        self.add("failed_requests")
        log.warning("refresh %s: %s: %s", self.court, what, exc)
        if self.errors_in_a_row >= MAX_CONSECUTIVE_ERRORS:
            raise RefreshAborted(f"{self.errors_in_a_row} failed requests in a row; last: {exc}")

    def out_of_time(self) -> bool:
        return self._deadline is not None and self._clock() >= self._deadline


# -- Federal Court / Federal Court of Appeal ---------------------------------------------------


def _s10_fetch(client: Client, s: s10.Stratum, n: int, run: _Run, *, known: bool) -> bool | None:
    """Re-request one file. ``known`` files must come back non-empty or the cached copy is kept."""
    number = s.number(n)
    params = {"division": s.division, "courtnumber": number}
    try:
        info = client.get(
            s10.ADDINFO,
            source=s10.SOURCE,
            tier=s10.TIER,
            params=params,
            refresh=True,
            accept=_has_rows if known else None,
        )
        if not s10.exists(info.json()):
            run.ok()
            return False
        client.get(
            s10.ENTRIES,
            source=s10.SOURCE,
            tier=s10.TIER,
            params=params,
            refresh=True,
            accept=_has_rows if known else None,
        )
    except (FetchError, ValueError) as exc:
        run.failed(number, exc)
        return None
    run.ok()
    return True


def s10_new_filings(client: Client, dockets: pl.DataFrame, year: int, run: _Run) -> None:
    """Probe upward from the highest known number of the current year, for A and T files."""
    for name, prefix, division in (("FCA", "A", "a"), ("FCT", "T", "t")):
        s = s10.Stratum(f"{name}-{year}", prefix, division, year, "census")
        known = dockets.filter((pl.col("prefix") == prefix) & (pl.col("docket_year") == year))
        n = int(known["number"].max() or 0) + 1
        misses = 0
        while misses < s10.STOP_AFTER_MISSES and not run.out_of_time():
            r = _s10_fetch(client, s, n, run, known=False)
            if r is True:
                misses = 0
                run.add("new_files")
            elif r is False:
                misses += 1
            n += 1


def s10_recheck(client: Client, dockets: pl.DataFrame, k: int, run: _Run) -> None:
    open_files = dockets.filter(
        pl.col("final_disposition_date").is_null() & ~pl.col("is_registration")
    ).sort("docket")
    for row in open_files.iter_rows(named=True):
        if run.out_of_time():
            run.add("skipped_out_of_time")
            continue
        if not in_slice(row["docket"], k):
            continue
        division = "a" if row["prefix"] == "A" else "t"
        s = s10.Stratum("recheck", row["prefix"], division, row["docket_year"], "census")
        if _s10_fetch(client, s, row["number"], run, known=True):
            run.add("rechecked_files")


def refresh_fc(client: Client, today: date, run: _Run, new_only: bool = False) -> None:
    p = paths.processed_dir() / "s10" / "dockets.parquet"
    dockets = pl.read_parquet(p)
    s10_new_filings(client, dockets, today.year, run)
    if not new_only:
        s10_recheck(client, dockets, week_slice(today), run)


# -- Tax Court ---------------------------------------------------------------------------------


def _s12_listing_from_cache() -> dict[str, str]:
    """File number -> status as last listed (read before the listing is refreshed)."""
    out = {}
    for _meta, j in s12._cached_json("/appealnumber/courtnumber"):
        for row in j.get("data") or []:
            if row.get("APPEAL_NBR"):
                out[row["APPEAL_NBR"].strip()] = (row.get("STATUS") or "").strip()
    return out


def _s12_cached_entry_numbers() -> set[str]:
    raw = paths.raw_dir(s12.SOURCE)
    out = set()
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if "/appealnumberRE" in meta["url"] and 200 <= meta["status"] < 300:
            out.add(unquote(meta["url"].split("appealnumber=")[1].split("&")[0]))
    return out


def refresh_tcc(
    client: Client, today: date, run: _Run, new_only: bool = False, first_year: int = 2018
) -> None:
    """Re-list every filing year (nine requests a year carry every file's status), then fetch the
    entries of new files, of files whose status changed, and of this week's slice of open files."""
    # every file listed so far goes into the ledger before any cached listing is replaced
    ever_listed = len(s12.listing_ledger())
    before = _s12_listing_from_cache()
    have_entries = _s12_cached_entry_numbers()
    now: dict[str, str] = {}
    for year in range(first_year, today.year + 1):
        for d in range(1, 10):
            prefix = f"{year}-{d}"
            n_prefix = sum(n.startswith(prefix) for n in before)
            try:
                r = client.get(
                    s12.LIST_URL,
                    source=s12.SOURCE,
                    tier=s12.TIER,
                    params={"courtnumber": prefix, "lang": "e"},
                    refresh=True,
                    # a prefix that listed files before must list most of them again
                    accept=_keeps_most(n_prefix) if n_prefix else None,
                )
                rows = r.json().get("data") or []
                run.ok()
            except (FetchError, ValueError) as exc:
                run.failed(f"list {prefix}", exc)
                continue
            for row in rows:
                nbr = (row.get("APPEAL_NBR") or "").strip()
                if nbr.startswith(prefix):
                    now[nbr] = (row.get("STATUS") or "").strip()
    # the new listings go into the ledger too; the log shows how much of the census is listed
    s12.listing_ledger()
    run.add("listed_now", len(now))
    run.add("ever_listed", max(ever_listed, len(now)))
    k = week_slice(today)
    closed = {"closed", "withdrawn"}
    for nbr in sorted(now, key=lambda n: (len(n), n)):
        if run.out_of_time():
            run.add("skipped_out_of_time")
            continue
        is_new = nbr not in have_entries
        changed = nbr in before and before[nbr] != now[nbr]
        still_open = now[nbr].lower() not in closed
        if not (is_new or changed or (still_open and not new_only and in_slice(nbr, k))):
            continue
        try:
            client.get(
                s12.RE_URL,
                source=s12.SOURCE,
                tier=s12.TIER,
                params={"appealnumber": nbr, "lang": "e"},
                refresh=True,
                accept=None if is_new else _has_rows,
            )
            run.ok()
            run.add("new_files" if is_new else "status_changed" if changed else "rechecked_files")
        except FetchError as exc:
            run.failed(nbr, exc)


# -- Supreme Court ------------------------------------------------------------------------------


def _is_case_list(content: bytes) -> bool:
    return b"/cases-dossiers/search-recherche/" in content


def _has_docket(content: bytes) -> bool:
    return b"Proceeding" in content


def refresh_scc(client: Client, today: date, run: _Run, new_only: bool = False) -> None:
    """Re-read the court's site map (one request) and fetch case pages not yet held; then
    re-request this week's slice of the files that were still open at the last parse (no
    "closed" entry). Added to the weekly run by owner decision 2026-11-20."""
    try:
        xml = client.get(
            s13.SITEMAP, source=s13.SOURCE, tier=s13.TIER, refresh=True, accept=_is_case_list
        ).text
        run.ok()
    except FetchError as exc:
        run.failed("site map", exc)
        return
    listed = {int(n) for n in s13.CASE_RE.findall(xml) if int(n) >= s13.FIRST_CASE}
    for n in sorted(listed - s13.cached_case_numbers()):
        if run.out_of_time():
            run.add("skipped_out_of_time")
            continue
        try:
            client.get(s13.CASE_URL.format(n=n), source=s13.SOURCE, tier=s13.TIER)
            run.ok()
            run.add("new_files")
        except FetchError as exc:
            run.failed(str(n), exc)
    if new_only:
        return
    cases = pl.read_parquet(paths.processed_dir() / "s13" / "cases.parquet")
    k = week_slice(today)
    for n in cases.filter(pl.col("closed_date").is_null())["case_no"].sort().to_list():
        if not in_slice(str(n), k):
            continue
        if run.out_of_time():
            run.add("skipped_out_of_time")
            continue
        try:
            client.get(
                s13.CASE_URL.format(n=n),
                source=s13.SOURCE,
                tier=s13.TIER,
                refresh=True,
                accept=_has_docket,
            )
            run.ok()
            run.add("rechecked_files")
        except FetchError as exc:
            run.failed(str(n), exc)


# -- entry point -------------------------------------------------------------------------------


def run_refresh(
    court: str,
    *,
    client: Client | None = None,
    today: date | None = None,
    max_minutes: float | None = None,
    new_only: bool = False,
) -> dict:
    """Run one court's weekly refresh and append a status line to data/raw/refresh_log.jsonl."""
    today = today or date.today()
    run = _Run(court, max_minutes)
    status, detail = "ok", ""
    own = client is None
    client = client or Client()
    try:
        {"fc": refresh_fc, "tcc": refresh_tcc, "scc": refresh_scc}[court](
            client, today, run, new_only
        )
    except RefreshAborted as exc:
        status, detail = "aborted", str(exc)
    finally:
        if own:
            client.close()
    row = {
        "court": court,
        "started": run.started,
        "finished": datetime.now(UTC).isoformat(timespec="seconds"),
        "slice": week_slice(today),
        "status": status,
        "detail": detail,
        **run.stats,
    }
    with (paths.data_dir() / "raw" / "refresh_log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    log.info("refresh %s: %s", court, row)
    return row
