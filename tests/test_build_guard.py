"""The build never replaces a committed table with one built from older source data."""

import json

import polars as pl

from courtdelay.estimate import build


def _guard(committed, local):
    stale = {s for s in local if s in committed and local[s] < committed[s]}
    return {"committed": committed, "local": local, "stale": stale, "changed": set(), "kept": []}


def test_table_sources_reads_guarded_prefixes_only():
    assert build._table_sources("s9_s8_fc_quarterly_panel") == {"s9", "s8"}
    assert build._table_sources("s10_fc_fca_km_by_cohort") == set()
    assert build._table_sources("link_fc_decision_docket_match_rates") == set()


def test_stale_source_keeps_committed_table_and_entry(tmp_path, monkeypatch):
    site = tmp_path / "data"
    site.mkdir()
    (site / "s8_x.csv").write_text("q,n\n2026Q3,5\n", encoding="utf-8")
    (site / build.VINTAGE_FILE).write_text(json.dumps({"s8": "2026-11-25"}), encoding="utf-8")
    monkeypatch.setattr(build, "_guard", _guard({"s8": "2026-11-25"}, {"s8": "2026-11-16"}))
    build._write(pl.DataFrame({"q": ["2026Q2"], "n": [4]}), "s8_x", tmp_path, site)
    build._write(pl.DataFrame({"a": [1]}), "s10_y", tmp_path, site)
    build.finish_guard(site)
    assert (site / "s8_x.csv").read_text(encoding="utf-8") == "q,n\n2026Q3,5\n"
    assert (site / "s10_y.csv").exists()
    assert json.loads((site / build.VINTAGE_FILE).read_text(encoding="utf-8")) == {
        "s8": "2026-11-25"
    }


def test_newer_data_is_written_and_dated_but_a_new_fetch_time_alone_is_not(tmp_path, monkeypatch):
    site = tmp_path / "data"
    site.mkdir()
    (site / "s8_x.csv").write_text("q,n\n2026Q2,4\n", encoding="utf-8")
    (site / "s1_z.csv").write_text("v,fetched_at\n1,2026-10-01\n", encoding="utf-8")
    committed = {"s1": "2026-10-01", "s8": "2026-11-16", "s5": "2026-11-16"}
    local = {"s1": "2026-11-29", "s8": "2026-11-29"}  # s5: no local data, entry must survive
    monkeypatch.setattr(build, "_guard", _guard(committed, local))
    build._write(pl.DataFrame({"q": ["2026Q3"], "n": [5]}), "s8_x", tmp_path, site)
    build._write(pl.DataFrame({"v": [1], "fetched_at": ["2026-11-29"]}), "s1_z", tmp_path, site)
    build.finish_guard(site)
    assert "2026Q3" in (site / "s8_x.csv").read_text(encoding="utf-8")
    assert "2026-10-01" in (site / "s1_z.csv").read_text(encoding="utf-8")
    assert json.loads((site / build.VINTAGE_FILE).read_text(encoding="utf-8")) == {
        "s1": "2026-10-01",
        "s5": "2026-11-16",
        "s8": "2026-11-29",
    }
