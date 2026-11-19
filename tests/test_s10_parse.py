import json
from datetime import date

from courtdelay.common import paths
from courtdelay.sources import s10_fc_fca_dockets as s10

FIX = json.loads((paths.fixtures_dir("s10") / "synthetic_A-9-25.json").read_text(encoding="utf-8"))


def test_ms_date_is_eastern_calendar_day():
    assert s10.ms_date("/Date(1735794000000)/") == date(2025, 1, 2)  # 05:00 UTC
    assert s10.ms_date("/Date(1657080000000)/") == date(2022, 7, 6)  # 04:00 UTC, daylight time
    assert s10.ms_date(None) is None


def test_parse_file_drops_names_and_derives_stages():
    row, ents = s10.parse_file(FIX["info"], FIX["entries"], "2026-11-16T03:00:00+00:00")
    blob = json.dumps(row, default=str) + json.dumps(ents, default=str)
    assert "PARTY" not in blob and "Person" not in blob, "no party or deponent names survive"
    assert row["docket"] == "A-9-25" and row["docket_year"] == 2025 and row["number"] == 9
    assert row["date_filed"] == date(2025, 1, 2) and row["track"] == "Appeals"
    assert row["scheduled_hearing_date"] == date(2025, 9, 28)
    assert row["final_disposition_type"] == "judgment"
    assert row["final_disposition_date"] == date(2026, 1, 15)
    assert row["final_disposition_result"] == "dismissed"
    types = [e["entry_type"] for e in sorted(ents, key=lambda e: e["re_no"])]
    assert types[2] == "copy_on_file", "IS_COPY flag respected"
    assert types[5] == "removed_entry"


def test_cancelled_document_does_not_end_the_file():
    entries = [e for e in FIX["entries"] if e["RE_NO"] in (1, 2, 4)]
    row, _ = s10.parse_file(FIX["info"], entries, "2026-11-16")
    assert row["final_disposition_date"] is None, "a later hearing order means the file continued"


def test_confidential_file_is_dropped():
    entries = [dict(FIX["entries"][0], IS_CONFIDENTIAL="Y")]
    assert s10.parse_file(FIX["info"], entries, "2026-11-16") == (None, [])
