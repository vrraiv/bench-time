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


def test_confidential_file_is_kept_and_counted(monkeypatch):
    entries = [dict(FIX["entries"][0], IS_CONFIDENTIAL="Y")]
    row, ents = s10.parse_file(FIX["info"], entries, "2026-11-16")
    assert row["n_confidential_flag_entries"] == 1 and len(ents) == 1
    assert row["n_sealed_text_entries"] == 0 and row["n_publication_ban_entries"] == 0
    monkeypatch.setattr(s10, "DROP_MARKED_FILES", True)
    assert s10.parse_file(FIX["info"], entries, "2026-11-16") == (None, [])


def test_copy_of_a_lead_file_order_is_recorded_apart_from_the_ending():
    copy = (
        "Copy of Order dated 27-APR-2020 rendered by a judge placed on file.\n"
        "Original filed on Court File No. T-10-18"
    )
    assert s10.copies_of_decisions([copy, "Letter received"], "T-11-18") == [
        ("T-10-18", "27-APR-2020")
    ]
    assert s10.copies_of_decisions([copy], "T-10-18") == [], "the file's own order is not a copy"

    def row(docket, end, kind, copies):
        return {
            "division": "T",
            "docket": docket,
            "final_disposition_date": end,
            "final_disposition_type": kind,
            "_copies": copies,
        }

    rows = [
        row("T-10-18", date(2020, 4, 27), "order", []),
        row("T-11-18", None, None, [("T-10-18", "27-APR-2020")]),  # the lead's closing order
        row("T-12-18", None, None, [("T-10-18", "03-MAR-2019")]),  # an earlier, procedural order
        row("T-13-18", None, None, [("T-99-18", "27-APR-2020")]),  # lead file not in our records
    ]
    assert s10.add_lead_file_endings(rows) == 1
    by = {r["docket"]: r for r in rows}
    assert by["T-11-18"]["lead_order_end_date"] == date(2020, 4, 27)
    assert by["T-11-18"]["lead_order_file"] == "T-10-18"
    assert by["T-11-18"]["final_disposition_date"] is None, "the file's own ending is untouched"
    assert by["T-12-18"]["lead_order_end_date"] is None
    assert by["T-13-18"]["lead_order_end_date"] is None
    assert all("_copies" not in r for r in rows)


def test_appeal_from_reads_the_lower_file_number():
    e = [
        {"DOC_DT": "2021-04-02", "RE_NO": 2, "RECORDED_ENTRY": "Letter received"},
        {
            "DOC_DT": "2021-04-01",
            "RE_NO": 1,
            "RECORDED_ENTRY": "Notice of Appeal filed on 01-APR-2021 against a decision of the "
            "Federal Court dated 12-MAR-2021 in T-0123-19",
        },
    ]
    assert s10.appeal_from(e) == ("T-123-19", "12-MAR-2021")
    e[1]["RECORDED_ENTRY"] = "Notice of Appeal against a judgment dated 05-JAN-2021 2018-456(IT)G"
    assert s10.appeal_from(e) == ("2018-456(IT)G", "05-JAN-2021")
    assert s10.appeal_from([{"DOC_DT": "2021-04-01", "RE_NO": 1, "RECORDED_ENTRY": "x"}]) == (
        None,
        None,
    )
