import json
from datetime import date

import pytest

from courtdelay.common import paths
from courtdelay.sources import s12_tcc_dockets as s12

FIX = json.loads((paths.fixtures_dir("s12") / "synthetic_2024-9.json").read_text(encoding="utf-8"))


def test_classify_labels():
    assert s12.classify("Notice of Appeal") == "notice_of_appeal"
    assert s12.classify("Amended Reply to Notice of Appeal") == "reply"
    assert s12.classify("Minutes of Hearing and Exhibit list") == "hearing_held"
    assert s12.classify("Adj. prior to hearing - Sine die") == "adjournment"
    assert s12.classify("Judgment") == "judgment"
    assert s12.classify("Judgment (Consent to Judgment) sent") != "judgment"
    assert s12.classify("File Closed") == "file_closed"
    assert s12.classify("Notice of Discontinuance") == "discontinuance"


def test_parse_file_stages_and_no_names():
    row, ents = s12.parse_file(FIX["listing"], FIX["entries"], "2026-11-16T18:00:00+00:00")
    blob = json.dumps(row, default=str) + json.dumps(ents, default=str)
    assert "PERSON" not in blob and "LAWYER" not in blob
    assert (
        row["docket_year"] == 2024 and row["number"] == 9 and row["procedure_suffix"] == "General"
    )
    assert row["date_filed"] == date(2024, 1, 5) and row["reply_date"] == date(2024, 3, 15)
    assert row["first_scheduled_date"] == date(2024, 6, 12)
    assert row["first_hearing_date"] == date(2025, 2, 10)
    assert row["judgment_date"] == date(2025, 6, 1) and row["n_adjournments"] == 1
    assert row["final_disposition_date"] == date(2025, 6, 20)


def test_confidential_dropped():
    listing = dict(FIX["listing"], CONFIDENTIAL_IND="Y")
    assert s12.parse_file(listing, FIX["entries"], "2026-11-16") == (None, [])


class FakeResp:
    def __init__(self, p):
        self._p = p

    def json(self):
        return self._p


def test_list_year_uses_nine_prefixes_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTDELAY_DATA_DIR", str(tmp_path))
    calls = []

    class C:
        def get(self, url, *, source, tier, params):
            calls.append(params["courtnumber"])
            p = params["courtnumber"]
            return FakeResp({"data": [{"APPEAL_NBR": p + "(IT)I"}, {"APPEAL_NBR": "2023-1(IT)G"}]})

    nums = s12.list_year(C(), 2024)
    assert calls == [f"2024-{d}" for d in range(1, 10)]
    assert nums[0] == "2024-1(IT)I" and all(n.startswith("2024-") for n in nums) and len(nums) == 9


def test_errors_abort_after_five(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTDELAY_DATA_DIR", str(tmp_path))
    s12._consecutive_errors = 0

    class C:
        def get(self, url, *, source, tier, params):
            raise s12.FetchError(url, None, "timeout")

    with pytest.raises(s12.CrawlAborted):
        s12.list_year(C(), 2024)


def test_application_numbers_and_new_milestones():
    listing = dict(FIX["listing"], APPEAL_NBR="2018-80(GST)APP")
    row, _ = s12.parse_file(listing, FIX["entries"], "2026-11-16")
    assert row["docket_year"] == 2018 and row["procedure_suffix"] == "Application"
    assert row["is_application"] is True
    listing = dict(FIX["listing"], APPEAL_NBR="2018-4718(EI)")
    row, _ = s12.parse_file(listing, FIX["entries"], "2026-11-16")
    assert row["docket_year"] == 2018 and row["procedure_suffix"] is None
    assert s12.classify("Joint Application for hearing") == "hearing_requested"
    assert s12.classify("Case Management Conference Held") == "case_mgmt_held"
    assert s12.classify("Request for adjournment") == "adjournment_requested"
    assert s12.classify("Memo requesting date submitted from a Joint Application") == "other"


def test_dismissed_and_abeyance():
    assert s12.classify("Dismissed") == "outcome"
    assert s12.classify("Dism. for failure to appear") == "outcome"
    assert s12.classify("Allowed in Part") == "outcome"
    assert s12.classify("Released from Pending") == "abeyance_released"
    assert s12.classify("Hearing Adjourned by TCC") == "court_adjournment"
    assert s12.classify("Request to be held in abeyance") == "abeyance_requested"
    assert s12.classify("Held in Abeyance granted") == "abeyance"
    assert s12.classify("Held in Abeyance Pending Related Decision") == "abeyance"
    assert s12.classify("Case Management Conference scheduled") == "case_mgmt_scheduled"
    ents = [
        {"INFO": "Notice of Appeal", "CREATED_DATE": "2019-01-02T00:00:00"},
        {"INFO": "Held in Abeyance granted", "CREATED_DATE": "2019-03-01T00:00:00"},
        {"INFO": "Dismissed", "CREATED_DATE": "2020-05-04T00:00:00"},
    ]
    listing = dict(FIX["listing"], APPEAL_NBR="2019-5(IT)I")
    row, _ = s12.parse_file(listing, ents, "2026-11-17")
    assert row["abeyance_date"].isoformat() == "2019-03-01"
    assert row["final_disposition_date"].isoformat() == "2020-05-04"


@pytest.mark.parametrize(
    "nbr,group",
    [
        ("2018-9(IT)G", "General"),
        ("2018-9(GST)I", "Informal"),
        ("2018-80(GST)APP", "Application"),
        ("2018-826(EI)", "EI"),
        ("2018-828(CPP)", "CPP"),
        ("2018-811(OAS)", "OAS"),
        ("2018-12(IT)", "Other / unlettered"),
    ],
)
def test_procedure_group(nbr, group):
    row, _ = s12.parse_file(dict(FIX["listing"], APPEAL_NBR=nbr), FIX["entries"], "2026-11-16")
    assert row["procedure_group"] == group


def test_filing_date_fallbacks():
    ents = [
        {"INFO": "Receipt for Notice of Application", "CREATED_DATE": "2019-02-03T00:00:00"},
        {"INFO": "Application Scheduled", "CREATED_DATE": "2019-06-01T00:00:00"},
    ]
    # applications usually have no listed filing date: first recorded entry is used
    listing = dict(FIX["listing"], APPEAL_NBR="2019-77(IT)APP", FILED_DATE=None)
    row, _ = s12.parse_file(listing, ents, "2026-11-18")
    assert row["date_filed"].isoformat() == "2019-02-03"
    assert row["date_filed_source"] == "first_entry"
    # a mistyped listed date (year 0026) is rejected
    listing = dict(FIX["listing"], APPEAL_NBR="2019-78(IT)G", FILED_DATE="0026-01-07T00:00:00")
    row, _ = s12.parse_file(listing, ents, "2026-11-18")
    assert row["listed_filed_date_implausible"] is True
    assert row["date_filed"].isoformat() == "2019-02-03"
    # a December filing numbered in January is kept
    listing = dict(FIX["listing"], APPEAL_NBR="2019-3(IT)I", FILED_DATE="2018-12-28T00:00:00")
    row, _ = s12.parse_file(listing, ents, "2026-11-18")
    assert row["date_filed_source"] == "listing"


def test_active_status_overrides_motion_judgment():
    ents = [
        {"INFO": "Notice of Appeal", "CREATED_DATE": "2021-01-05T00:00:00"},
        {"INFO": "Withdrawal of Motion", "CREATED_DATE": "2021-06-01T00:00:00"},
        {"INFO": "Judgment", "CREATED_DATE": "2021-07-01T00:00:00"},
    ]
    listing = dict(FIX["listing"], APPEAL_NBR="2021-9(IT)G", FILED_DATE="2021-01-05T00:00:00")
    row, _ = s12.parse_file(dict(listing, STATUS="Ready To Be Scheduled"), ents, "2026-11-18")
    assert row["court_status_active"] is True and row["final_disposition_date"] is None
    row, _ = s12.parse_file(dict(listing, STATUS="Heard"), ents, "2026-11-18")
    assert row["final_disposition_date"].isoformat() == "2021-07-01"
    assert row["discontinuance_date"] is None
    assert s12.classify("Notice of Withdrawal/Discontinuance") == "discontinuance"
    assert s12.classify("Notice of Withdrawal of Intervention") != "discontinuance"
    assert s12.classify("Judgment/Order remailed") != "judgment"
    assert s12.classify("Judgment with Reasons") == "judgment"
    assert s12.classify("Held in Abeyance denied") != "abeyance"


def test_sittings_trial_only_when_the_appeal_was_set_down():
    d = date
    # a case management conference, then the trial: only the second sitting is the trial
    file1 = [
        (d(2024, 1, 5), "Notice of Appeal"),
        (d(2024, 5, 1), "Case Management Conference scheduled"),
        (d(2024, 6, 3), "Minutes of Hearing"),
        (d(2024, 9, 1), "Order Hearing Fixed"),
        (d(2024, 9, 2), "Notice of Hearing"),
        (d(2025, 2, 10), "Minutes of Hearing and Exhibit list"),
        (d(2025, 2, 11), "Minutes of Hearing"),
    ]
    assert s12.classify_sittings(file1) == [
        (d(2024, 6, 3), "other"),
        (d(2025, 2, 10), "trial"),
        (d(2025, 2, 11), "trial"),
    ]
    # a conference held with no minutes does not swallow the trial that follows
    file2 = [
        (d(2024, 3, 1), "Notice of Hearing"),
        (d(2024, 4, 1), "Case Management Conference scheduled"),
        (d(2024, 4, 20), "Case Management Conference Held"),
        (d(2024, 6, 1), "Minutes of Hearing"),
    ]
    assert s12.classify_sittings(file2) == [(d(2024, 6, 1), "trial")]
    # nothing set down: not counted as a trial; a decision reserved that day makes it one
    assert s12.classify_sittings([(d(2024, 6, 1), "Minutes of Hearing")]) == [
        (d(2024, 6, 1), "unclassified")
    ]
    assert s12.classify_sittings(
        [(d(2024, 6, 1), "Minutes of Hearing"), (d(2024, 6, 1), "Reserved Decision at Hearing")]
    ) == [(d(2024, 6, 1), "trial")]
    # an adjourned trial date no longer counts as set down
    file3 = [
        (d(2024, 3, 1), "Notice of Hearing"),
        (d(2024, 5, 1), "Adj. prior to hearing - Sine die"),
        (d(2024, 6, 1), "Minutes of Hearing"),
    ]
    assert s12.classify_sittings(file3) == [(d(2024, 6, 1), "unclassified")]
