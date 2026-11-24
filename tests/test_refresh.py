"""Offline tests for the weekly refresh (no network)."""

import json
from datetime import date

import polars as pl
import pytest

from courtdelay import refresh
from courtdelay.common.http import FetchError
from courtdelay.sources import s10_fc_fca_dockets as s10


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class FakeFC:
    """Files up to max_n exist; records each request and whether it asked for a refresh."""

    def __init__(self, max_n, fail=()):
        self.max_n, self.fail, self.calls = max_n, set(fail), []

    def get(self, url, *, source, tier, params, refresh=False, accept=None):
        assert tier == 2 and refresh is True, "every refresh request must bypass the cache"
        nbr = params["courtnumber"]
        self.calls.append((url, nbr))
        if nbr in self.fail:
            raise FetchError(url, 503)
        n = int(nbr.split("-")[1])
        return FakeResp({"data": [{"x": 1}]} if n <= self.max_n else {"data": []})


def _dockets():
    rows = []
    for n in range(1, 41):
        rows.append(("T", 2026, n, f"T-{n}-26", None if n % 2 else date(2026, 5, 1), n == 3))
    rows.append(("A", 2026, 7, "A-7-26", None, False))
    return pl.DataFrame(
        rows,
        schema=[
            "prefix",
            "docket_year",
            "number",
            "docket",
            "final_disposition_date",
            "is_registration",
        ],
        orient="row",
    )


def test_slices_are_stable_and_cover_everything():
    keys = [f"T-{n}-24" for n in range(1, 401)]
    parts = [{k for k in keys if refresh.in_slice(k, s)} for s in range(refresh.SLICES)]
    assert set().union(*parts) == set(keys) and sum(len(p) for p in parts) == len(keys)
    assert all(60 < len(p) < 140 for p in parts)
    assert refresh.week_slice(date(2026, 11, 22)) != refresh.week_slice(date(2026, 11, 29))


def test_new_filings_start_after_the_highest_known_number(monkeypatch):
    monkeypatch.setattr(s10, "STOP_AFTER_MISSES", 5)
    c = FakeFC(max_n=43)
    run = refresh._Run("fc", None)
    refresh.s10_new_filings(c, _dockets(), 2026, run)
    t_probes = [nbr for url, nbr in c.calls if url == s10.ADDINFO and nbr.startswith("T-")]
    assert t_probes[0] == "T-41-26" and t_probes[-1] == "T-48-26"  # 3 found, then 5 misses
    # A files: only A-7-26 known, so probing starts at 8
    assert [n for u, n in c.calls if u == s10.ADDINFO and n.startswith("A-")][0] == "A-8-26"
    assert run.stats["new_files"] == 3 + 36  # T-41..43 and A-8..43


def test_recheck_takes_only_open_files_in_this_slice_and_skips_registrations():
    c = FakeFC(max_n=1000)
    run = refresh._Run("fc", None)
    d = _dockets()
    k = 1
    refresh.s10_recheck(c, d, k, run)
    asked = {nbr for url, nbr in c.calls if url == s10.ADDINFO}
    open_files = d.filter(pl.col("final_disposition_date").is_null() & ~pl.col("is_registration"))
    assert asked == {x for x in open_files["docket"] if refresh.in_slice(x, k)}
    assert "T-3-26" not in asked and len(asked) == run.stats["rechecked_files"]


def test_run_stops_after_repeated_failures_and_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTDELAY_DATA_DIR", str(tmp_path))
    (tmp_path / "processed" / "s10").mkdir(parents=True)
    _dockets().write_parquet(tmp_path / "processed" / "s10" / "dockets.parquet")
    (tmp_path / "raw").mkdir()
    monkeypatch.setattr(s10, "STOP_AFTER_MISSES", 5)
    c = FakeFC(max_n=0, fail={f"A-{n}-26" for n in range(8, 60)})
    row = refresh.run_refresh("fc", client=c, today=date(2026, 11, 22))
    assert row["status"] == "aborted" and row["failed_requests"] == refresh.MAX_CONSECUTIVE_ERRORS
    logged = json.loads((tmp_path / "raw" / "refresh_log.jsonl").read_text().splitlines()[-1])
    assert logged["court"] == "fc" and logged["status"] == "aborted"


class FakeSCC:
    def __init__(self, listed):
        self.listed, self.calls = listed, []

    def get(self, url, *, source, tier, params=None, refresh=False, accept=None):
        assert tier == 2
        self.calls.append((url, refresh))

        class R:
            text = "".join(f"<loc>/cases-dossiers/search-recherche/{n}/</loc>" for n in self.listed)

        return R()


def test_scc_refresh_fetches_new_pages_and_rechecks_open_slice(tmp_path, monkeypatch):
    from courtdelay.sources import s13_scc_cases as s13

    (tmp_path / "s13").mkdir()
    open_cases = list(range(40000, 40040))
    pl.DataFrame(
        {
            "case_no": [*open_cases, 40100],
            "closed_date": [None] * 40 + [date(2024, 1, 1)],
        },
        schema={"case_no": pl.Int64, "closed_date": pl.Date},
    ).write_parquet(tmp_path / "s13" / "cases.parquet")
    monkeypatch.setattr(refresh.paths, "processed_dir", lambda: tmp_path)
    monkeypatch.setattr(s13, "cached_case_numbers", lambda: {*open_cases, 40100})
    # 30000 is before the frame and is ignored; 40101 and 40102 are new
    client = FakeSCC([30000, *open_cases, 40100, 40101, 40102])
    run = refresh._Run("scc", None)
    today = date(2026, 11, 22)
    refresh.refresh_scc(client, today, run)
    assert client.calls[0] == (s13.SITEMAP, True)
    new = [u for u, r in client.calls[1:] if not r]
    assert new == [s13.CASE_URL.format(n=n) for n in (40101, 40102)]
    k = refresh.week_slice(today)
    want = [s13.CASE_URL.format(n=n) for n in open_cases if refresh.in_slice(str(n), k)]
    assert [u for u, r in client.calls[1:] if r] == want and 0 < len(want) < 40
    assert run.stats == {"new_files": 2, "rechecked_files": len(want)}
    # new-only: the site map and nothing else once the new pages are held
    monkeypatch.setattr(s13, "cached_case_numbers", lambda: {*open_cases, 40100, 40101, 40102})
    c2 = FakeSCC([*open_cases, 40100, 40101, 40102])
    refresh.refresh_scc(c2, today, refresh._Run("scc", None), new_only=True)
    assert len(c2.calls) == 1


def test_listing_that_shrinks_is_refused():
    import json

    body = lambda n: json.dumps({"data": [{"APPEAL_NBR": f"2018-{i}(IT)I"} for i in range(n)]})  # noqa: E731
    accept = refresh._keeps_most(1000)
    assert accept(body(1000).encode()) and accept(body(800).encode())
    assert not accept(body(218).encode()) and not accept(b"not json")
    # small listings only need to come back with rows
    small = refresh._keeps_most(5)
    assert small(body(1).encode()) and not small(body(0).encode())


def test_tcc_refresh_keeps_cached_listing_and_stops_when_listings_shrink(tmp_path, monkeypatch):
    from courtdelay.sources import s12_tcc_dockets as s12

    before = {f"2026-{d}{i:03d}(IT)I": "Closed" for d in range(1, 10) for i in range(40)}
    monkeypatch.setattr(refresh, "_s12_listing_from_cache", lambda: before)
    monkeypatch.setattr(refresh, "_s12_cached_entry_numbers", lambda: set(before))
    monkeypatch.setattr(s12, "listing_ledger", lambda: dict.fromkeys(before, {}))

    class Shrunk:
        calls = 0

        def get(self, url, *, source, tier, params, refresh=False, accept=None):
            Shrunk.calls += 1
            rows = [{"APPEAL_NBR": f"{params['courtnumber']}000(IT)I", "STATUS": "Closed"}]
            import json

            if accept is not None and not accept(json.dumps({"data": rows}).encode()):
                raise FetchError(url, 200, "rejected; cached copy kept")
            return FakeResp({"data": rows})

    run = refresh._Run("tcc", None)
    with pytest.raises(refresh.RefreshAborted):
        refresh.refresh_tcc(Shrunk(), date(2026, 11, 29), run, first_year=2026)
    # the run stops after five refused listings; no file is fetched, no listing replaced
    assert Shrunk.calls == refresh.MAX_CONSECUTIVE_ERRORS
    assert run.stats == {"failed_requests": refresh.MAX_CONSECUTIVE_ERRORS}
