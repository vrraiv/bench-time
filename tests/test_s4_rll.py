"""Synthetic recorded entries modelled on Federal Court docket formats; no real names."""

from datetime import date

from courtdelay.sources import s4_rll_fc_dockets as s4

LEAVE_GRANTED = (
    "Order rendered by The Honourable Mr. Justice Example at Vancouver on 09-SEP-2019 granting "
    "the application for leave fixing the hearing at a Special Sitting at Vancouver on 27-NOV-2019 "
    "to begin at 09:30 specifying documents to be produced"
)
LEAVE_DISMISSED = (
    "(Final decision) Order rendered by Associate Chief Justice Example at Ottawa on 06-MAY-2019 "
    "dismissing the application for leave Decision endorsed on the record on document 1 received "
    "on 07-MAY-2019 Considered by the Court without personal appearance"
)
HEARING_JR = (
    "Toronto 11-DEC-2019 BEFORE The Honourable Madam Justice Example Language: E Before the Court: "
    "Judicial Review Result of Hearing: Matter reserved held in Court Duration per day: 11-DEC-2019"
)
HEARING_MOTION = (
    "Toronto 13-NOV-2019 BEFORE The Honourable Mr. Justice Example Language: E Before the Court: "
    "Motion Doc. No. 3 on behalf of Applicant Result of Hearing: Matter reserved held in Court"
)
JUDGMENT = (
    "(Final decision) Reasons for Judgment and Judgment dated 12-MAR-2020 rendered by The "
    "Honourable Madam Justice Example Matter considered with personal appearance The Court's "
    "decision is with regard to Judicial Review Result: dismissed Filed on 12-MAR-2020 copies sent"
)
COPY = (
    "Copy of Reasons for Judgment and Judgment dated 04-MAR-2021 rendered by The Honourable Madam "
    "Justice Example placed on file. Original filed on Court File No. IMM-0000-19"
)
DISCONTINUANCE = "Notice of discontinuance on behalf of the applicant filed on 23-APR-2019"
FILING = (
    "Copy of the application for leave and for judicial review with proof of service on the "
    "respondent on 12-DEC-2019 filed on 12-DEC-2019"
)


def test_classify_and_result():
    assert s4.classify_entry(LEAVE_GRANTED) == "leave_decision"
    assert s4.entry_result(LEAVE_GRANTED) == "granted"
    assert s4.classify_entry(LEAVE_DISMISSED) == "leave_decision"
    assert s4.entry_result(LEAVE_DISMISSED) == "dismissed"
    assert s4.classify_entry(HEARING_JR) == "hearing"
    assert s4.hearing_subject(HEARING_JR) == "judicial_review"
    assert s4.entry_result(HEARING_JR) == "reserved"
    assert s4.hearing_subject(HEARING_MOTION) == "motion"
    assert s4.classify_entry(JUDGMENT) == "judgment" and s4.entry_result(JUDGMENT) == "dismissed"
    assert s4.classify_entry(COPY) == "copy_on_file"
    assert s4.classify_entry(FILING) == "copy_on_file"
    assert s4.classify_entry(DISCONTINUANCE) == "discontinuance"
    assert s4.classify_entry("") == "other"


def test_dates():
    assert s4.parse_entry_date("2019-05-15") == date(2019, 5, 15)
    assert s4.parse_entry_date("27-NOV-2019") == date(2019, 11, 27)
    assert s4.parse_entry_date(None) is None


def _doc(re_no, dt, text):
    return {"RE_NO": re_no, "DOCNO": None, "DOC_DT": dt, "RECORDED_ENTRY": text}


def test_derive_docket_granted_path():
    docs = [
        _doc(1, "2019-05-01", "Application for leave and for judicial review filed on 01-MAY-2019"),
        _doc(2, "2019-09-09", LEAVE_GRANTED),
        _doc(3, "2019-11-13", HEARING_MOTION),
        _doc(4, "2019-12-11", HEARING_JR),
        _doc(5, "2020-03-12", JUDGMENT),
        _doc(6, "2021-03-04", COPY),
    ]
    ents = s4.classify_docket_entries(docs, "IMM-1-19")
    assert all("RECORDED_ENTRY" not in e for e in ents)
    d = s4.derive_docket(ents)
    assert d["leave_decision_date"] == date(2019, 9, 9) and d["leave_result"] == "granted"
    assert d["scheduled_hearing_date"] == date(2019, 11, 27)
    assert d["hearing_date"] == date(2019, 12, 11), (
        "motion hearing must not count as the JR hearing"
    )
    assert d["judgment_date"] == date(2020, 3, 12)
    assert d["final_disposition_date"] == date(2020, 3, 12)
    assert (
        d["final_disposition_type"] == "judgment" and d["final_disposition_result"] == "dismissed"
    )
    assert d["n_entries"] == 6


def test_derive_docket_leave_dismissed_and_discontinued():
    docs = [
        _doc(1, "2019-01-10", "Application filed on 10-JAN-2019"),
        _doc(2, "2019-05-07", LEAVE_DISMISSED),
    ]
    d = s4.derive_docket(s4.classify_docket_entries(docs, "IMM-2-19"))
    assert (
        d["final_disposition_type"] == "leave_decision"
        and d["final_disposition_result"] == "dismissed"
    )
    docs = [
        _doc(1, "2019-01-10", "Application filed on 10-JAN-2019"),
        _doc(2, "2019-04-23", DISCONTINUANCE),
    ]
    d = s4.derive_docket(s4.classify_docket_entries(docs, "IMM-3-19"))
    assert d["final_disposition_type"] == "discontinuance"
    assert d["final_disposition_date"] == date(2019, 4, 23)


def test_sealed_marker_detected():
    assert s4.SEALED_RE.search("Order that the file be sealed pending further order")
    assert not s4.SEALED_RE.search("Order granting an extension of time")


LEAVE_DISMISSED_FR = (
    "(Décision finale) Ordonnance rendu(e) par Monsieur le juge Exemple à Ottawa le 06-AVR-2010 "
    "rejetant la demande d'autorisation Décision inscrite au dossier"
)
JR_ALLOWED_FR = (
    "(Décision finale) Jugement rendu(e) par Madame le juge Exemple à Montréal le 27-OCT-2010 "
    "accueillant la demande de contrôle judiciaire"
)


def test_french_entries_and_terminal_variants():
    assert s4.classify_entry(LEAVE_DISMISSED_FR) == "leave_decision"
    assert s4.entry_result(LEAVE_DISMISSED_FR) == "dismissed"
    assert s4.FINAL_RE.match(LEAVE_DISMISSED_FR)
    assert s4.classify_entry(JR_ALLOWED_FR) == "judgment"
    assert s4.entry_result(JR_ALLOWED_FR) == "granted"
    assert s4.classify_entry("Discontinuance on behalf of Applicant filed on 27-JUL-2011") == (
        "discontinuance"
    )
    assert s4.classify_entry("****** CANCELLED ****** Application for leave") == "cancelled"
    assert s4.classify_entry("Copie certifiée de la décision du tribunal") == "copy_on_file"
    assert s4.parse_entry_date("06-AVR-2010") == date(2010, 4, 6)
    docs = [_doc(1, "2010-01-10", "Demande déposée"), _doc(2, "2010-04-06", LEAVE_DISMISSED_FR)]
    d = s4.derive_docket(s4.classify_docket_entries(docs, "IMM-9-10"))
    assert d["final_disposition_type"] == "leave_decision"
    assert d["final_disposition_result"] == "dismissed"
