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
    assert s4.FINAL_RE.search(LEAVE_DISMISSED_FR)
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


def test_final_marker_on_its_own_line():
    def final(text):
        return s4.classify_docket_entries([_doc(5, "2021-02-01", text)], "A-1-20")[0]["is_final"]

    # the court's current system puts the marker on a line of its own after the entry text
    assert final("Judgment dated 01-FEB-2021 Result: dismissed copies sent\nFinal Decision  \nCopy")
    assert final("Jugement rendu le 01-FEV-2021\r\nDécision finale    ")
    # a mention in running prose is not a marker; neither is a cancelled entry
    assert not final(
        "Letter asking that the record be addressed after a final decision in the appeal"
    )
    assert not final("****** CANCELLED ****** (Final decision) Order rendered by the Court")


def test_judgment_fallback_can_be_turned_off():
    docs = [
        _doc(1, "2024-03-01", "Notice of appeal filed on 01-MAR-2024"),
        _doc(2, "2024-03-02", "Copy of judgment under appeal placed on file"),
        _doc(3, "2024-03-05", "Letter concerning the judgment of the Tax Court received"),
    ]
    ents = s4.classify_docket_entries(docs, "A-9-24")
    assert s4.derive_docket(ents)["final_disposition_source"] == "fallback"
    open_file = s4.derive_docket(ents, judgment_fallback=False)
    assert open_file["final_disposition_date"] is None
    assert open_file["final_disposition_source"] is None


def test_french_and_appeal_court_hearing_minutes():
    fr = "L'audition de cette affaire a lieu le 30-NOV-2016 à Montréal en présence de : le juge X"
    en = "This matter comes on for hearing on 07-JUN-2017 at Toronto. Judgment reserved"
    head = "Montréal 12-MAI-2020 En présence de Madame la juge X Langue : F Matière en litige : "
    fr2 = head + "Contrôle judiciaire Résultat de l'audition : en délibéré"
    cmc = head + "Conférence de gestion de l'instance Résultat : tenue"
    for t in (fr, en, fr2, cmc):
        assert s4.classify_entry(t) == "hearing", t
    assert s4.hearing_subject(fr2) == "judicial_review"
    docs = [
        _doc(1, "2020-01-10", "Notice of application filed"),
        _doc(2, "2020-03-01", cmc),
        _doc(3, "2020-05-12", fr2),
    ]
    d = s4.derive_docket(s4.classify_docket_entries(docs, "T-9-20"))
    assert d["hearing_date"] == date(2020, 5, 12)  # the case conference is not the hearing


# Entries in the Registry's format from 1 January 2026 (synthetic, modelled on real headers)
LEAVE_DISMISSED_2026 = (
    "Order (Final) dated 2026-05-28 rendered by The Honourable Mr. Justice Example without "
    "personal appearance regarding doc # 1 - IMM-CIT - APPLICATION FOR LEAVE AND JUDICIAL REVIEW "
    "Result - Leave dismissed issued to: all parties by email received on 2026-05-29"
)
LEAVE_GRANTED_2026 = (
    "Order dated 2026-06-25 rendered by The Honourable Madam Justice Example Result - Leave "
    "granted, Judicial Review scheduled The hearing of the application for judicial review shall "
    "take place before the Court in person at the Federal Court in the City of Toronto, on "
    "Wednesday, September 16, 2026, to commence at 11:00 a.m. issued to: all parties by email"
)
LEAVE_DISMISSED_2026_FR = (
    "Ordonnance (final(e)) daté(e)(s) du 2026-02-11 rendu(e)(s) par Monsieur le juge Exemple sans "
    "comparution des parties concernant le doc # 1 - IMM-CIT - DEMANDE D'AUTORISATION ET DE "
    "CONTRÔLE JUDICIARE Résultat - Demande d'autorisation rejetée délivré(e)(s) à : toutes les "
    "parties par courriel déposé(e)(s) le 2026-02-12"
)
JUDGMENT_2026 = (
    "Reasons - for Judgment and Judgment (Final) dated 2026-08-28 rendered by The Honourable "
    "Madam Justice Example with personal appearance Result - dismissed issued to: all parties"
)
INTERLOCUTORY_2026 = (
    "Order (Interlocutory) dated 2026-08-14 rendered by Associate Judge Example without personal "
    "appearance regarding doc # 3 - Notice of Status Review filed on 2026-08-14"
)
TRANSLATION_2026 = (
    "Traduction - texte français - jugement (final(e)) daté(e)(s) du 2026-03-02 déposé(e)(s) le "
    "2026-04-20"
)
HEARING_CMC_2026 = (
    "This matter comes on for Hearing on 2026-10-30 at Toronto virtual before Associate Judge "
    "Example hearing language: English Duration on 15 minutes Courtroom: Toronto (Zoom) "
    "Result of Hearing: CMC heard"
)
HEARING_FR_2026 = (
    "L'audition de cette affaire a eu lieu Audition le 2026-09-01 à Montréal en personne en "
    "présence de Monsieur le juge Exemple langue de l'audience : français Matière en litige : "
    "Contrôle judiciaire Résultat de l'audition : décision mise en délibéré"
)


def test_2026_registry_format():
    assert s4.classify_entry(LEAVE_DISMISSED_2026) == "leave_decision"
    assert s4.entry_result(LEAVE_DISMISSED_2026) == "dismissed"
    assert s4.is_final_marker(LEAVE_DISMISSED_2026)
    assert s4.classify_entry(LEAVE_GRANTED_2026) == "leave_decision"
    assert s4.entry_result(LEAVE_GRANTED_2026) == "granted"
    assert not s4.is_final_marker(LEAVE_GRANTED_2026)
    assert s4.classify_entry(LEAVE_DISMISSED_2026_FR) == "leave_decision"
    assert s4.entry_result(LEAVE_DISMISSED_2026_FR) == "dismissed"
    assert s4.is_final_marker(LEAVE_DISMISSED_2026_FR)
    assert s4.classify_entry(JUDGMENT_2026) == "judgment"
    assert s4.entry_result(JUDGMENT_2026) == "dismissed"
    assert s4.is_final_marker(JUDGMENT_2026)
    assert s4.is_final_marker("Copy of Copy of Order (Final) dated 2026-03-01 rendered by X")
    # not the decision itself: interlocutory orders, translations, corrections, placed on file
    assert not s4.is_final_marker(INTERLOCUTORY_2026)
    assert not s4.is_final_marker(TRANSLATION_2026)
    assert not s4.is_final_marker("Corrections to reasons (Final) dated 2026-03-01")
    assert not s4.is_final_marker("Copy of Decision placed on file (Final) dated 2026-03-01")
    assert s4.classify_entry("Recorded entry cancelled.") == "removed_entry"
    assert s4.classify_entry("Inscription enregistrée annulée.") == "removed_entry"
    # the older markers still work
    assert s4.is_final_marker(LEAVE_DISMISSED) and not s4.is_final_marker(LEAVE_GRANTED)


def test_2026_docket_stages():
    docs = [
        {"RE_NO": 1, "DOC_DT": "2026-01-05", "RECORDED_ENTRY": "Application for leave filed"},
        {"RE_NO": 2, "DOC_DT": "2026-06-25", "RECORDED_ENTRY": LEAVE_GRANTED_2026},
        {"RE_NO": 3, "DOC_DT": "2026-07-10", "RECORDED_ENTRY": HEARING_CMC_2026},
        {"RE_NO": 4, "DOC_DT": "2026-09-16", "RECORDED_ENTRY": HEARING_FR_2026},
        {"RE_NO": 5, "DOC_DT": "2026-10-20", "RECORDED_ENTRY": JUDGMENT_2026},
        {"RE_NO": 6, "DOC_DT": "2026-11-02", "RECORDED_ENTRY": TRANSLATION_2026},
    ]
    d = s4.derive_docket(s4.classify_docket_entries(docs, "IMM-1-26"), judgment_fallback=False)
    assert (d["leave_decision_date"], d["leave_result"]) == (date(2026, 6, 25), "granted")
    assert d["scheduled_hearing_date"] == date(2026, 9, 16)
    # the case conference is not the hearing of the application
    assert (d["hearing_date"], d["hearing_result"]) == (date(2026, 9, 16), "reserved")
    assert d["final_disposition_date"] == date(2026, 10, 20)
    assert d["final_disposition_source"] == "marker" and d["final_disposition_type"] == "judgment"
    one = [{"RE_NO": 1, "DOC_DT": "2026-05-29", "RECORDED_ENTRY": LEAVE_DISMISSED_2026}]
    d = s4.derive_docket(s4.classify_docket_entries(one, "IMM-2-26"), judgment_fallback=False)
    assert d["final_disposition_date"] == date(2026, 5, 29)
    assert d["final_disposition_type"] == "leave_decision"
