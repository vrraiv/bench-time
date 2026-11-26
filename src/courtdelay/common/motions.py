"""Motions and interlocutory orders: what an order was about, and what a motion asked for.

Shared by the Federal Court / FCA docket parser (S10) and the published-decision parser (S3).
Returns categories and counts only; no entry or decision text leaves these functions.

The registry writes each order entry in a fixed form (read locally, 2026-11-25):
"Order dated ... rendered by ... Matter considered with[out] personal appearance. The Court's
decision is with regard to <motion doc. no. N | letter from ... | case management conference |
status review | judicial review | trial of the matter ...> Result: <granted | dismissed | text>
... Interlocutory Decision | Final Decision". From 2026 the form is "Order (Interlocutory) dated
... regarding doc # N - letter - informal motion result - ...". The trailing tag is the
registry's own interlocutory / final classification.
"""

from __future__ import annotations

import re

# What a motion or an interlocutory order is about. A text may carry several topics.
# Costs are left out: "without costs" closes most orders.
TOPICS: dict[str, re.Pattern] = {
    k: re.compile(v, re.I)
    for k, v in {
        "extension": r"extension of (?:the )?time|time .{0,60}\bis extended\b"
        r"|extend (?:the )?(?:time|deadline)|prorog|proroger|prolongation",
        "stay": r"\bstay(?:ed|ing)?\b|\bsursis\b|suspension de l.instance",
        "strike": r"\bstrik(?:e|ing)\b|\bstruck\b|radiation|radi[ée]",
        "summary": r"summary (?:judgment|trial)|jugement sommaire|proc[èe]s sommaire",
        "confidentiality": r"confidential|protective order|rule 151|r[èe]gle 151|sealed|scell"
        r"|ordonnance de protection",
        "amend": r"\bamend(?:ed|ment|ing)?\b|modifi(?:er|cation)",
        "security_for_costs": r"security for costs|cautionnement pour (?:les )?d[ée]pens",
        "discovery": r"\bcompel|further answers|answers? to (?:the )?questions|undertakings"
        r"|refusals|production of documents|affidavit of documents|interrogatoire"
        r"|cross-examination",
        "intervention": r"\binterven(?:e|er|ers|ing|tion|ant|ante)\b",
        "case_management": r"specially[- ]managed|case management judge|rule 383|gestion "
        r"sp[ée]ciale|juge responsable de la gestion",
        "adjournment": r"\badjourn|ajourn|postpone|remise de l.audience",
        "timetable": r"timetable|schedule of (?:the )?(?:remaining|next) steps|next steps"
        r"|[ée]ch[ée]ancier",
        "consolidation": r"consolidat|joinder|joined with|r[ée]union d",
        "representation": r"rule 120|r[èe]gle 120|cease to act|removal of (?:the )?solicitor"
        r"|solicitor of record|represent the (?:corporation|partnership|company)",
        "injunction": r"injunction|injonction|anton piller|norwich",
        "record": r"certified (?:tribunal )?record|appeal book|dossier certifi[ée]",
    }.items()
}


def topics(text: str | None) -> list[str]:
    """Topics named in a text, in the order of TOPICS."""
    if not text:
        return []
    return [k for k, rx in TOPICS.items() if rx.search(text)]


# An order or judgment entry. "Reasons for order and order" is one decision; a standalone
# "Reasons for ..." entry accompanies an order entry and is not counted again.
ORDER_RE = re.compile(
    r"^\s*(?:\((?:final decision|d[ée]cision finale)\)\s*)?"
    r"(?:(?:reasons for (?:order|judgment) and |motifs (?:de l.ordonnance|du jugement) et )"
    r"(?:the )?)?"
    r"(?:order|ordonnance|judgment|jugement)\b(?!\s+\(time and place\))(?!\s+scheduling)",
    re.I,
)
SCHEDULING_RE = re.compile(r"time and place|scheduling time|heure et (?:le )?lieu", re.I)
REGARDING_RE = re.compile(r"with regard to|regarding|concerning|concernant", re.I)
RESULT_CUT_RE = re.compile(r"\bresult\s*[:\-]|r[ée]sultat|\bfiled on\b|d[ée]pos[ée]", re.I)
# older form: "Order rendered by ... at Toronto on 01-MAY-2023 granting letter dated ..."
RENDERED_ON_RE = re.compile(r"\bon\s+\d{1,2}-[A-Za-zÉÛéû]{3,4}-\d{4}\s+(.*)", re.I | re.S)
RESULT_RE = re.compile(r"(?:result|r[ée]sultat)\s*[:\-]\s*(.*)", re.I | re.S)
INTERLOC_RE = re.compile(
    r"interlocutory decision|\(interlocutory\)|d[ée]cision interlocutoire|\(interlocutoire\)",
    re.I,
)
FINAL_TAG_RE = re.compile(r"final decision|\(final\)|d[ée]cision finale|\(finale?\)", re.I)
REGARDING_KINDS = [
    ("informal_request", r"letter|informal|lettre|request"),
    ("motion", r"motion|requ[êe]te"),
    ("conference", r"conference|meeting|dispute resolution|conf[ée]rence|r[ée]union"),
    ("status_review", r"status review|show cause|examen de l.[ée]tat|justifier"),
    (
        "court_own_motion",
        r"ex proprio motu|de son propre chef|order dated|directions? of the court",
    ),
    (
        "merits",
        r"judicial review|trial|appeal|application|action|contr[ôo]le judiciaire"
        r"|proc[èe]s|appel|demande",
    ),
]


def order_detail(text: str | None) -> dict:
    """For an order entry: what it was about, the registry's interlocutory tag and the topics.
    All None for an entry that is not an order (scheduling orders count as not an order)."""
    out = {"order_regarding": None, "order_interlocutory": None, "order_topics": None}
    if not text or not ORDER_RE.search(text) or SCHEDULING_RE.search(text[:200]):
        return out
    m = REGARDING_RE.search(text) or RENDERED_ON_RE.search(text)
    regarding = ""
    if m:
        tail = text[m.end() : m.end() + 400] if m.re is REGARDING_RE else m.group(1)[:400]
        cut = RESULT_CUT_RE.search(tail)
        regarding = tail[: cut.start()] if cut else tail[:200]
    kind = next(
        (k for k, rx in REGARDING_KINDS if re.search(rx, regarding, re.I)),
        "other",
    )
    out["order_regarding"] = kind
    if INTERLOC_RE.search(text):
        out["order_interlocutory"] = True
    elif FINAL_TAG_RE.search(text):
        out["order_interlocutory"] = False
    r = RESULT_RE.search(text)
    t = topics(regarding + " " + (r.group(1) if r else ""))
    out["order_topics"] = ",".join(t) or None
    return out


MOTION_FILED_RE = re.compile(
    r"^\s*(?:confidential\s+)?(?:notice of motion|avis de requ[êe]te)", re.I
)
INFORMAL_RE = re.compile(
    r"^\s*letter\b.{0,200}?\binformal\b|^\s*lettre\b.{0,200}?\binformelle", re.I | re.S
)
CANCELLED_RE = re.compile(r"\*+\s*cancel|\*+\s*annul", re.I)


def motion_filing(text: str | None) -> str | None:
    """'formal' for a notice of motion, 'informal' for a letter making an informal request."""
    if not text or CANCELLED_RE.search(text[:40]):
        return None
    if MOTION_FILED_RE.search(text):
        return "formal"
    if INFORMAL_RE.search(text):
        return "informal"
    return None


def file_procedure(details: list[dict], filings: list[str | None]) -> dict:
    """Per-file counts from the order details and motion filings of its entries."""
    orders = [d for d in details if d["order_regarding"] is not None]
    out = {
        "n_motions_filed": sum(f == "formal" for f in filings),
        "n_informal_requests": sum(f == "informal" for f in filings),
        "n_orders": len(orders),
        # registry tag, else inferred (an untagged order that is not the file's final entry)
        "n_interlocutory_orders": sum(
            d["order_interlocutory"] is True or d.get("order_interlocutory_inferred") is True
            for d in orders
        ),
        "n_interlocutory_orders_inferred": sum(
            d.get("order_interlocutory_inferred") is True for d in orders
        ),
        "n_orders_untagged": sum(d["order_interlocutory"] is None for d in orders),
        "n_orders_on_motions": sum(d["order_regarding"] == "motion" for d in orders),
        "n_orders_on_requests": sum(d["order_regarding"] == "informal_request" for d in orders),
        "n_conference_orders": sum(d["order_regarding"] == "conference" for d in orders),
        "n_status_review_orders": sum(d["order_regarding"] == "status_review" for d in orders),
    }
    for k in TOPICS:
        out[f"n_orders_{k}"] = sum(k in (d["order_topics"] or "").split(",") for d in orders)
    return out
