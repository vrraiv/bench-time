from courtdelay.common import motions

# synthetic entries modelled on the registry's wording; no real names or files
MOTION_ORDER = (
    "Order dated 12-MAR-2021 rendered by Associate Judge Example Matter considered without "
    "personal appearance The Court's decision is with regard to motion in writing doc. no. 16 "
    "Result: granted. The time to serve the affidavit is extended by 30 days. Filed on "
    "12-MAR-2021 copies sent to parties entered in J. & O. Book Interlocutory Decision"
)
LETTER_ORDER = (
    "Order dated 02-JUN-2022 rendered by The Honourable Justice Example Matter considered "
    "without personal appearance The Court's decision is with regard to letter from plaintiff "
    "dated 01-JUN-2022 re: confidentiality order Result: granted Filed on 02-JUN-2022"
)
NEW_FORM = (
    "Order (Interlocutory) dated 2026-03-02 issued by Associate Judge Example without personal "
    "appearance regarding doc # 52 - letter - informal motion result - the appeal is stayed"
)
OLD_FORM = (
    "Order rendered by Associate Judge Example at Toronto on 01-MAY-2023 granting letter dated "
    "April 12, 2023 from applicant: the timetable is amended"
)
FINAL = (
    "(Final decision) Order dated 05-JAN-2024 rendered by Justice Example The Court's decision "
    "is with regard to judicial review (s.18) Result: dismissed Final Decision"
)


def test_order_detail():
    d = motions.order_detail(MOTION_ORDER)
    assert d == {
        "order_regarding": "motion",
        "order_interlocutory": True,
        "order_topics": "extension",
    }
    d = motions.order_detail(LETTER_ORDER)
    assert d["order_regarding"] == "informal_request" and d["order_interlocutory"] is None
    assert d["order_topics"] == "confidentiality"
    d = motions.order_detail(NEW_FORM)
    assert (d["order_regarding"], d["order_interlocutory"], d["order_topics"]) == (
        "informal_request",
        True,
        "stay",
    )
    d = motions.order_detail(OLD_FORM)
    assert d["order_regarding"] == "informal_request" and "amend" in d["order_topics"]
    d = motions.order_detail(FINAL)
    assert d["order_regarding"] == "merits" and d["order_interlocutory"] is False
    # not orders: scheduling orders, copies of orders from other files, filings
    assert (
        motions.order_detail("Order (time and place) dated 01-JAN-2020")["order_regarding"] is None
    )
    assert (
        motions.order_detail("Copy of Order dated 20-APR-2015 placed on file")["order_regarding"]
        is None
    )
    assert (
        motions.order_detail("Notice of motion on behalf of the applicant")["order_regarding"]
        is None
    )


def test_motion_filing_and_file_counts():
    assert motions.motion_filing("Notice of Motion contained within a motion record") == "formal"
    assert motions.motion_filing("Avis de requête qui se trouve dans le dossier") == "formal"
    assert motions.motion_filing("Letter from respondent re: informal request for extension") == (
        "informal"
    )
    assert motions.motion_filing("****** CANCELLED ****** Notice of Motion") is None
    assert motions.motion_filing("Motion Record in response to motion doc. no. 4") is None
    details = [motions.order_detail(t) for t in (MOTION_ORDER, LETTER_ORDER, FINAL)]
    details[1]["order_interlocutory_inferred"] = True
    c = motions.file_procedure(details, ["formal", "informal", None])
    assert c["n_motions_filed"] == 1 and c["n_informal_requests"] == 1
    assert c["n_orders"] == 3 and c["n_interlocutory_orders"] == 2
    assert c["n_interlocutory_orders_inferred"] == 1 and c["n_orders_untagged"] == 1
    assert c["n_orders_on_motions"] == 1 and c["n_orders_extension"] == 1


def test_judgment_and_combined_entries_are_decisions():
    assert (
        motions.order_detail(
            "Judgment dated 03-JUN-2020 rendered by Justice Example concerning motion doc. no. 4"
        )["order_regarding"]
        == "motion"
    )
    assert (
        motions.order_detail(
            "Reasons for Order and Order dated 05-MAY-2021 rendered by Justice Example"
        )["order_regarding"]
        is not None
    )
    # a standalone reasons entry goes with its order entry and is not counted twice
    assert (
        motions.order_detail("Reasons for Judgment rendered by Justice Example")["order_regarding"]
        is None
    )
