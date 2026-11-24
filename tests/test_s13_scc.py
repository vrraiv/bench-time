"""Offline tests for the Supreme Court case-information parser (synthetic page, no network)."""

from datetime import date

from courtdelay.sources import s13_scc_cases as s13

PAGE = """<html><body><main>
<h1>49999</h1><h2>PERSON ONE v. PERSON TWO</h2>
<table><tr><th>Date</th><th>Proceeding</th><th>Filed By (if applicable)</th></tr>
<tr><td>2023-06-01</td><td>Close file on Leave</td><td></td></tr>
<tr><td>2023-05-25</td><td>Judgment of the Court on the application for leave to appeal, The
 application for leave to appeal from the judgment of the Federal Court of Appeal, Number
 A-123-21, 2022 FCA 45, dated March 10, 2022, is dismissed with costs.</td><td></td></tr>
<tr><td>2023-04-03</td><td>All materials on application for leave submitted to the Judges,
 for consideration by the Court</td><td></td></tr>
<tr><td>2022-06-20</td><td>Respondent's response on the application for leave to appeal,
 completed on</td><td>PERSON TWO</td></tr>
<tr><td>2022-05-09</td><td>Certificate (on limitations to public access)</td>
 <td>PERSON ONE</td></tr>
<tr><td>2022-05-09</td><td>Application for leave to appeal, completed on 2022-05-12</td>
 <td>PERSON ONE</td></tr>
</table>
<table><tr><th>Name</th><th>Role</th><th>Status</th></tr>
<tr><td>PERSON ONE</td><td>Applicant</td><td>Active</td></tr></table>
<h4>Lower court rulings</h4>
<div class="div-border"><div class="row"><div class="col-md-5 mb-3">January 5, 2021<br/>
Federal Court<br/><br/>2021 FC 9, T-55-19</div><div class="col-md-7">Application dismissed</div>
</div><hr/><div class="row"><div class="col-md-5 mb-3">March 10, 2022<br/>Federal Court of Appeal
<br/><br/>2022 FCA 45, A-123-21</div><div class="col-md-7">Appeal dismissed</div></div></div>
</main></body></html>"""


def test_classify_labels():
    assert s13.classify("Application for leave to appeal, completed on 2022-05-12") == "leave_filed"
    assert s13.classify("Respondent's response on the application for leave to appeal") == "other"
    assert s13.classify("All materials on application for leave submitted to the Judges") == (
        "leave_submitted"
    )
    assert s13.classify("Hearing of the appeal, 2026-01-15, DAY 2") == "hearing"
    assert s13.classify("Judgment on the appeal rendered, CJ") == "judgment"
    assert s13.classify("Written reasons rendered after oral judgment") == "written_reasons"
    assert s13.classify("Judgment reserved OR rendered with reasons to follow") == (
        "judgment_reserved"
    )
    assert s13.classify("Appeal closed") == "closed"
    assert s13.classify("Certificate (on limitations to public access)") == "access_certificate"


def test_parse_page_stages_origin_and_no_names():
    row, ents = s13.parse_page(PAGE, 49999, "2026-11-19T20:00:00+00:00")
    assert row["leave_filed_date"] == date(2022, 5, 9)
    assert row["leave_submitted_date"] == date(2023, 4, 3)
    assert row["leave_decision_date"] == date(2023, 5, 25) and row["leave_result"] == "dismissed"
    assert row["closed_date"] == date(2023, 6, 1) and row["hearing_date"] is None
    assert row["court_appealed_from"] == "Federal Court of Appeal"
    assert row["lower_court_file"] == "A-123-21" and row["lower_court_citation"] == "2022 FCA 45"
    assert row["lower_court_judgment_date"] == date(2022, 3, 10)
    assert row["n_access_certificates"] == 1 and row["n_entries"] == 6
    assert row["n_restriction_marker_entries"] == 0
    blob = repr(row) + repr(ents)
    assert "PERSON" not in blob


def test_origin_falls_back_to_lower_court_rulings_before_leave_is_decided():
    undecided = PAGE.replace("Judgment of the Court on the application for leave", "Letter about")
    row, _ = s13.parse_page(undecided, 49999, "2026-11-19")
    assert row["leave_decision_date"] is None and row["leave_result"] is None
    assert row["court_appealed_from"] == "Federal Court of Appeal"
    assert row["lower_court_file"] == "A-123-21"
    assert row["lower_court_judgment_date"] == date(2022, 3, 10)


def test_result_comes_from_registry_label_and_latest_leave_judgment():
    two = PAGE.replace(
        "<tr><td>2023-06-01</td><td>Close file on Leave</td><td></td></tr>",
        "<tr><td>2023-09-14</td><td>Judgment of the Court on the application for leave to "
        "appeal, The application is granted.<br/>Granted, with costs in the cause</td><td></td>"
        "</tr><tr><td>2023-05-25</td><td>Judgment of the Court on the application for leave to "
        "cross-appeal, The application is dismissed.<br/>Dismissed</td><td></td></tr>",
    )
    row, ents = s13.parse_page(two, 49999, "2026-11-20")
    assert row["leave_result"] == "granted" and row["leave_granted_any"] is True
    assert row["leave_decision_date"] == date(2023, 9, 14)
    assert row["leave_first_decision_date"] == date(2023, 5, 25)
    assert row["n_leave_decision_dates"] == 2
    assert row["leave_completed_date"] == date(2022, 5, 12)
    assert sum(e["entry_type"] == "cross_leave_decision" for e in ents) == 1
    # the court appealed from still comes from the first leave judgment's wording
    assert row["lower_court_file"] == "A-123-21"
    assert row["first_ruling_court"] == "Federal Court"
    assert row["first_ruling_date"] == date(2021, 1, 5)


def test_several_lower_files_and_no_judge_name_as_court():
    d = s13.leave_details(
        "The applications for leave to appeal from the judgments of the Court of Appeal for "
        "Ontario, Numbers C50052 and C50050, 2010 ONCA 642 and 2010 ONCA 782, dated October 5, "
        "2010 and November 17, 2010, are dismissed with costs."
    )
    assert (
        d["lower_court_files"] == "C50052; C50050" and d["lower_court_citation"] == "2010 ONCA 642"
    )
    assert d["leave_result"] == "dismissed"
    assert (
        s13.leave_details(
            "The application for leave to appeal from the direction of Person J.A. of the Federal "
            "Court of Appeal, Number A-201-16, dated January 3, 2017, is dismissed."
        )
        == {}
    )
    assert s13.result_label("Dismissed, without costs") == "dismissed"
    assert s13.result_label("Remand") == "remanded"
