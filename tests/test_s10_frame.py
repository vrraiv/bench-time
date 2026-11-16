"""Offline tests for the S10/S11 sampling frame and stopping rules (no network)."""

import json

import pytest

from courtdelay.sources import s10_fc_fca_dockets as s10


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class FakeClient:
    """Files 1..max_n exist except listed gaps; records every request."""

    def __init__(self, max_n, gaps=()):
        self.max_n, self.gaps, self.calls = max_n, set(gaps), []

    def get(self, url, *, source, tier, params):
        assert tier == 2 and source == s10.SOURCE
        self.calls.append((url, params["courtnumber"]))
        n = int(params["courtnumber"].split("-")[1])
        ok = 1 <= n <= self.max_n and n not in self.gaps
        return FakeResp({"data": [{"x": 1}]} if ok else {"data": []})


@pytest.fixture
def raw(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTDELAY_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(s10, "STOP_AFTER_MISSES", 5)
    return tmp_path


def test_numbering():
    assert s10.Stratum("IMM-2024", "IMM", "t", 2024, "sample", 10).number(57) == "IMM-57-24"
    assert s10.Stratum("FCA-2009", "A", "a", 2009, "census").number(3) == "A-3-09"


def test_census_walks_past_gaps_and_stops(raw):
    c = FakeClient(max_n=30, gaps={7, 8, 9})
    r = s10.crawl_census(c, s10.Stratum("FCA-2024", "A", "a", 2024, "census"))
    assert r["found"] == 27 and r["last_n_probed"] == 35
    # entries are requested only for existing files
    assert sum(1 for u, _ in c.calls if u == s10.ENTRIES) == 27


def test_sample_is_seeded_resumable_and_replaces_misses(raw):
    s = s10.Stratum("IMM-2024", "IMM", "t", 2024, "sample", 20)
    c = FakeClient(max_n=300, gaps=set(range(100, 120)))
    r = s10.crawl_sample(c, s, hint=50)
    assert r["found"] == 20 and r["frame_max_n"] >= 298
    plan = json.loads((raw / "raw" / s10.SOURCE / "plan_IMM-2024.json").read_text())
    c2 = FakeClient(max_n=300, gaps=set(range(100, 120)))
    assert s10.make_sample_plan(c2, s, hint=50)["order"] == plan["order"]
    assert c2.calls == [], "plan reused, no frame probing on resume"


def test_default_plan_matches_owner_decision():
    plan = s10.default_plan()
    assert {s.mode for s in plan if s.prefix in {"A", "T"}} == {"census"}
    imm = [s for s in plan if s.prefix == "IMM"]
    assert [s.year for s in imm] == [2023, 2024, 2025, 2026] and all(
        s.n_sample == 1000 for s in imm
    )
