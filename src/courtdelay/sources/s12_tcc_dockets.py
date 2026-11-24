"""S12: Tax Court of Canada dockets (Tier 2), census by filing year.

Verified 2026-11-16 from the Court's own page scripts (docs/sources.md S12). The "Find a Court File"
page (https://www.tcc-cci.ca/en/pages/find-a-court-file, script /Content/js/base/data.js) calls:

  GET /en/tcc/pq/appealnumber/courtnumber?courtnumber=<prefix>&lang=e   file list (prefix match)
  GET /en/tcc/pq/appealnumberRE?appealnumber=<number>&lang=e            recorded entries

The court-number search is a prefix match: "2024-1" returns every 2024 file whose number starts
with 1 (1,093 rows in the pilot, uncapped; ``Count`` equals the row count). Nine listing requests
("YYYY-1" .. "YYYY-9") therefore enumerate a filing year, then one entries request per file.
Requests go through the shared client: single-threaded, 4 s per host (www.tcc-cci.ca; a different
host from the Federal Court crawl, which may run at the same time). Raw responses include appellant
and representative names; they stay in the local raw cache and are never parsed into outputs.

Listing rows carry PROCEDURE (General / Informal), STATUS, DISPOSITION (text), FILED_DATE, NATURE,
ACTCODE, HEARING_LOC, SELF_IND (self-represented) and CONFIDENTIAL_IND. Recorded entries are short
standard labels (INFO) with a date (CREATED_DATE): "Notice of Appeal", "Reply to Notice of
Appeal", "Appeal Scheduled", "Notice of Hearing", "Minutes of Hearing ...", "Judgment",
"File Closed", adjournments ("Adj. ..."), discontinuances.

Bias statement: file numbers whose year differs from the filing date are kept with both; files
open at the scrape are right-censored; confidential files are dropped and counted.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s12_tcc_dockets"
TIER = 2
BASE = "https://www.tcc-cci.ca/en/tcc/pq"
LIST_URL = f"{BASE}/appealnumber/courtnumber"
RE_URL = f"{BASE}/appealnumberRE"
DEFAULT_YEARS = range(2018, 2027)
MAX_CONSECUTIVE_ERRORS = 5
# "2024-1(IT)I", "2024-10(GST)G", "2018-4718(EI)" (no procedure suffix: EI/CPP appeals),
# "2018-80(GST)APP" (applications, e.g. for an extension of time to appeal)
NUMBER_RE = re.compile(r"^(\d{4})-(\d+)\((\w+)\)(G|I|APP)?$")

_consecutive_errors = 0


class CrawlAborted(RuntimeError):
    """Raised after MAX_CONSECUTIVE_ERRORS failed requests in a row. Rerunning resumes."""


def _failure(year: int, what: str, exc: Exception) -> None:
    global _consecutive_errors
    _consecutive_errors += 1
    with (paths.raw_dir(SOURCE) / f"failures_{year}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"what": what, "error": str(exc)[:300]}) + "\n")
    log.warning("TCC %s %s: %s", year, what, exc)
    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        raise CrawlAborted(f"{_consecutive_errors} consecutive request failures; last: {exc}")


def _ok() -> None:
    global _consecutive_errors
    _consecutive_errors = 0


def list_year(client: Client, year: int) -> list[str]:
    """All file numbers for a filing year via nine prefix queries. Returns sorted numbers."""
    numbers: set[str] = set()
    for d in range(1, 10):
        prefix = f"{year}-{d}"
        try:
            r = client.get(
                LIST_URL, source=SOURCE, tier=TIER, params={"courtnumber": prefix, "lang": "e"}
            )
            rows = r.json().get("data") or []
            _ok()
        except (FetchError, ValueError) as exc:
            _failure(year, f"list {prefix}", exc)
            continue
        for row in rows:
            nbr = (row.get("APPEAL_NBR") or "").strip()
            if nbr.startswith(prefix):
                numbers.add(nbr)
    return sorted(numbers, key=lambda n: (len(n), n))


def fetch_year(client: Client, year: int) -> dict:
    numbers = list_year(client, year)
    fetched = 0
    for i, nbr in enumerate(numbers, 1):
        try:
            client.get(RE_URL, source=SOURCE, tier=TIER, params={"appealnumber": nbr, "lang": "e"})
            fetched += 1
            _ok()
        except FetchError as exc:
            _failure(year, nbr, exc)
        if i % 100 == 0:
            _progress(year, {"files": len(numbers), "entries_fetched": fetched})
    result = {"year": year, "files": len(numbers), "entries_fetched": fetched}
    _progress(year, {"done": True, **result})
    return result


def _progress(year: int, row: dict) -> None:
    with (paths.raw_dir(SOURCE) / f"progress_{year}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def fetch(client: Client, strata: list[str] | None = None) -> list[dict]:
    """``strata`` are filing years as strings (e.g. ["2024"]); default 2018-2026."""
    years = [int(s) for s in strata] if strata else list(DEFAULT_YEARS)
    return [fetch_year(client, y) for y in years]


# -- parse -------------------------------------------------------------------------------------

LIST_FIELDS = {
    "APPEAL_NBR": "docket",
    "PROCEDURE": "procedure",
    "STATUS": "status",
    "DISPOSITION": "disposition",
    "NATURE": "nature",
    "ACTCODE": "act_code",
    "HEARING_LOC": "hearing_location",
    "SELF_IND": "self_represented",
    "LANG": "language",
}

# (entry type, pattern on the INFO label); first match wins
ENTRY_TYPES: list[tuple[str, re.Pattern]] = [
    ("notice_of_appeal", re.compile(r"^notice of appeal\b", re.I)),
    ("reply", re.compile(r"^(?:amended )?reply to (?:the )?notice of appeal", re.I)),
    # withdrawal of the appeal itself, not of a motion, an intervention, a bill of costs or part
    # of the appeal
    (
        "discontinuance",
        re.compile(
            r"^notice of withdrawal(?!.* of intervention)|^withdrawal accepted|discontinu"
            r"|d[ée]sistement",
            re.I,
        ),
    ),
    ("file_closed", re.compile(r"^file closed", re.I)),
    ("hearing_held", re.compile(r"^minutes of hearing", re.I)),
    ("adjournment", re.compile(r"^adj(?:\.|ournment)", re.I)),
    ("scheduled", re.compile(r"^appeal scheduled|^notice of hearing", re.I)),
    ("status_hearing", re.compile(r"status hearing", re.I)),
    # the case is ready and a hearing date is requested (general procedure): the start of the
    # wait that is attributable to the court's calendar
    (
        "hearing_requested",
        re.compile(
            r"^(?:joint )?application (?:for|to fix) (?:a )?hearing|^request for hearing", re.I
        ),
    ),
    ("case_mgmt_held", re.compile(r"^case management conference held", re.I)),
    ("adjournment_requested", re.compile(r"^request for adjournment", re.I)),
    # the judgment itself: not its mailing, translation, publication, or a Federal Court one
    (
        "judgment",
        re.compile(
            r"^(?:amended )?judgment\b"
            r"(?!.*\b(?:sent|remailed|translation|transmitted|published|from f[.]c[.]c)\b)",
            re.I,
        ),
    ),
    ("consent", re.compile(r"consent (?:to judgment|allowed|dismissed)", re.I)),
    # bare outcome entries end the file ("Dismissed", "Allowed", "Quashed", "Dism. for failure
    # to appear", "File Cancelled"); some files have no other end event
    (
        "outcome",
        re.compile(
            r"^dism[.] for failure to appear"
            r"|^(?:dismissed|allowed(?: in part)?|quashed|file cancelled)[ ]*$",
            re.I,
        ),
    ),
    # the court's own adjournment of a hearing, as distinct from one a party requested
    ("court_adjournment", re.compile(r"^hearing adjourned by tcc", re.I)),
    ("settlement_conf_held", re.compile(r"^settlement conference held", re.I)),
    (
        "abeyance_released",
        re.compile(r"^(?:released from pending|unhold appeal|reactivate appeal)", re.I),
    ),
    # abeyance pauses the file at a party's request (often pending a related decision): time
    # in abeyance is not calendar delay, so it is recorded separately
    ("abeyance_requested", re.compile(r"^request to be held in abeyance", re.I)),
    ("abeyance", re.compile(r"^held in abeyance(?! denied)", re.I)),
    ("case_mgmt_scheduled", re.compile(r"^case management conference scheduled", re.I)),
    ("order", re.compile(r"\border\b", re.I)),
]


# court STATUS values (lower case prefixes) meaning the appeal has not been decided or closed;
# any status ending in "scheduled" is also active
ACTIVE_STATUS_PREFIXES = (
    "case management in progress",
    "ready to be scheduled",
    "not ready to be scheduled",
    "hold",
    "awaiting timetable",
    "settled",
    "settlement received",
)


# "Minutes of Hearing" is recorded for any sitting: the trial, but also motions, status
# hearings, case management and conference calls (practitioner, round 1, TC-6; in the census
# the entry most often follows "Case Management Conference scheduled"). A sitting is read as
# the trial from what was set down before it.
MINUTES_RX = re.compile(r"^minutes of hearing", re.I)
# sets the appeal itself down for hearing (for an application file, the application)
# ("Order Hearing Fixed" and "Notice of Hearing" are not used: they also accompany show-cause
# hearings and motions)
TRIAL_SET_RX = re.compile(
    r"^appeal scheduled|^continuation of appeal scheduled|^appeal hearing reassigned"
    r"|^application scheduled",
    re.I,
)
# minutes with an exhibit list: evidence was taken, so the appeal itself was heard
EXHIBITS_RX = re.compile(r"^minutes of hearing and exhibit list", re.I)
# sets down something else that will produce its own minutes
OTHER_SET_RX = re.compile(
    r"^case management conference scheduled|^trial management scheduled"
    r"|^motion\b.*\bscheduled|^show cause scheduled|^status hearing scheduled"
    r"|^notice of status hearing|^settlement conference scheduled"
    r"|^pre-hearing conference scheduled|^returnable date for notice of motion",
    re.I,
)
# on the day itself: marks the sitting as a conference or a motion
OTHER_DAY_RX = re.compile(
    r"^case management conference held|^trial management held|^show cause held"
    r"|^status hearing heard|^settlement conference held|^interim motion .* at hearing"
    r"|^motion to dismiss/quash .* at hearing|^conference call",
    re.I,
)
# on the day itself: only happens at the hearing of the appeal
TRIAL_DAY_RX = re.compile(
    r"^reserved decision at hearing|^consent allowed at hearing"
    r"|^withdrawal accepted at hearing|^dism[.] for failure to appear",
    re.I,
)
TRIAL_OFF_RX = re.compile(r"^adj[.] prior to hearing|^hearing adjourned by tcc", re.I)
OTHER_DONE_RX = re.compile(
    r"^case management conference (?:held|adjourned)|^trial management held|^show cause held"
    r"|^status hearing heard|^adj[.] of status hearing|^settlement conference held"
    r"|^withdrawal of (?:notice of )?motion|^interim motion .* prior to hearing",
    re.I,
)


def classify_sittings(entries: list[tuple[date | None, str]]) -> list[tuple[date, str]]:
    """Each date with a "Minutes of Hearing" entry -> (date, kind), kind one of "trial",
    "other" (conference, motion, status or show-cause hearing) or "unclassified" (nothing on
    the file says what was set down). Entries are (date, label); order within a day is unknown,
    so a day is read as a whole."""
    days: dict[date, list[str]] = {}
    for d, label in entries:
        if d is not None:
            days.setdefault(d, []).append((label or "").strip())
    out, trial_set, other_set, last_set = [], False, 0, None
    for d in sorted(days):
        labels = days[d]
        if any(MINUTES_RX.search(x) for x in labels):
            if any(TRIAL_DAY_RX.search(x) or EXHIBITS_RX.search(x) for x in labels):
                kind = "trial"
            elif any(OTHER_DAY_RX.search(x) for x in labels) or other_set:
                kind = "other"
                other_set = max(0, other_set - 1)
            elif trial_set:
                kind = "trial"
            else:
                kind = "unclassified"
            out.append((d, kind))
        else:
            # a conference or motion that was held, adjourned or withdrawn with no minutes
            # entry is no longer waiting for one
            done = sum(bool(OTHER_DONE_RX.search(x)) for x in labels)
            other_set = max(0, other_set - done)
        # what this day sets down for later days
        for x in labels:
            if OTHER_SET_RX.search(x):
                other_set += 1
                last_set = "other"
            elif TRIAL_SET_RX.search(x):
                trial_set = True
                last_set = "trial"
            elif TRIAL_OFF_RX.search(x):
                # an adjournment before the hearing cancels whatever was set down last
                if last_set == "other" and other_set:
                    other_set -= 1
                else:
                    trial_set = False
    return out


def classify(label: str | None) -> str:
    t = (label or "").strip()
    for name, rx in ENTRY_TYPES:
        if rx.search(t):
            return name
    return "other"


def _d(v) -> date | None:
    s = str(v or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def parse_file(listing: dict, entries: list[dict], fetched_at: str) -> tuple[dict | None, list]:
    """One file -> (row, entry rows) with no names. (None, []) for confidential files."""
    if str(listing.get("CONFIDENTIAL_IND") or "N").upper() == "Y" or any(
        str(e.get("CONFIDENTIAL_IND") or "N").upper() == "Y" for e in entries
    ):
        return None, []
    nbr = listing.get("APPEAL_NBR") or ""
    m = NUMBER_RE.match(nbr.replace(" ", ""))
    ents = sorted(
        (
            {
                "docket": nbr,
                "entry_date": _d(e.get("CREATED_DATE")),
                "entry_type": classify(e.get("INFO")),
            }
            for e in entries
        ),
        key=lambda e: e["entry_date"] or date.min,
    )

    sittings = classify_sittings([(_d(e.get("CREATED_DATE")), e.get("INFO")) for e in entries])
    trial_days = {d for d, k in sittings if k == "trial"}
    for e in ents:
        if e["entry_type"] == "hearing_held" and e["entry_date"] in trial_days:
            e["entry_type"] = "trial_held"

    def first(t):
        return next((e["entry_date"] for e in ents if e["entry_type"] == t), None)

    # Filing date: the listing's FILED_DATE when plausible. It is missing for most applications
    # and occasionally mistyped (year 0026) or years away from the file number's year, so fall
    # back to the notice of appeal entry, then to the first recorded entry; the source is kept.
    year = int(m.group(1)) if m else None

    def plausible(d):
        return d is not None and (year is None or abs(d.year - year) <= 1)

    listed = _d(listing.get("FILED_DATE"))
    first_entry = next((e["entry_date"] for e in ents if e["entry_date"]), None)
    filed, filed_source = None, None
    for cand, src in (
        (listed, "listing"),
        (first("notice_of_appeal"), "notice_of_appeal"),
        (first_entry, "first_entry"),
    ):
        if plausible(cand):
            filed, filed_source = cand, src
            break

    row = {out: listing.get(k) for k, out in LIST_FIELDS.items()}
    row.update(
        {
            "docket_year": int(m.group(1)) if m else None,
            "number": int(m.group(2)) if m else None,
            "act_suffix": m.group(3) if m else None,
            "procedure_suffix": {"G": "General", "I": "Informal", "APP": "Application"}.get(
                m.group(4)
            )
            if m
            else None,
            "is_application": bool(m and m.group(4) == "APP"),
            # EI, CPP and OAS appeals carry an act suffix but no G/I letter: they follow their
            # own procedural rules, so group them by act rather than as "no procedure"
            "procedure_group": (
                {"G": "General", "I": "Informal", "APP": "Application"}.get(m.group(4))
                or {"EI": "EI", "CPP": "CPP", "OAS": "OAS"}.get(m.group(3), "Other / unlettered")
            )
            if m
            else "Unparsed",
            "date_filed": filed,
            "date_filed_source": filed_source,
            "listed_filed_date_implausible": listed is not None and not plausible(listed),
            "reply_date": first("reply"),
            "first_scheduled_date": first("scheduled"),
            # first sitting of any kind, and the first read as the trial (see MINUTES_RX)
            "first_hearing_date": min((d for d, _ in sittings), default=None),
            # not before the filing date: in a file that began as an extension
            # application, the hearing of that application is not the trial of the appeal
            "first_trial_date": min(
                (d for d in trial_days if filed is None or d >= filed), default=None
            ),
            "n_sittings": len(sittings),
            "n_trial_sittings": len(trial_days),
            "n_other_sittings": sum(k == "other" for _, k in sittings),
            "n_unclassified_sittings": sum(k == "unclassified" for _, k in sittings),
            "hearing_requested_date": first("hearing_requested"),
            "n_case_mgmt_conferences": sum(e["entry_type"] == "case_mgmt_held" for e in ents),
            "n_adjournment_requests": sum(e["entry_type"] == "adjournment_requested" for e in ents),
            "judgment_date": first("judgment"),
            "discontinuance_date": first("discontinuance"),
            "closed_date": first("file_closed"),
            "outcome_entry_date": first("outcome"),
            "abeyance_released_date": first("abeyance_released"),
            "n_court_adjournments": sum(e["entry_type"] == "court_adjournment" for e in ents),
            "n_settlement_conferences": sum(
                e["entry_type"] == "settlement_conf_held" for e in ents
            ),
            "abeyance_date": first("abeyance"),
            "n_abeyance_entries": sum(e["entry_type"] == "abeyance" for e in ents),
            "n_adjournments": sum(e["entry_type"] == "adjournment" for e in ents),
            "n_entries": len(ents),
            "scraped": fetched_at[:10],
        }
    )
    ends = [
        d
        for d in (
            row["closed_date"],
            row["judgment_date"],
            row["discontinuance_date"],
            row["outcome_entry_date"],
        )
        if d
    ]
    # The court's own status decides whether the file has ended. Files it lists as still active
    # (in case management, on hold, waiting for or given a hearing date, settlement pending)
    # often carry a judgment or withdrawal on a motion, which is not the end of the appeal:
    # 18,713 of 18,722 "Closed" files have a "File Closed" entry, almost no active ones do.
    status = (row.get("status") or "").strip().lower()
    row["court_status_active"] = status.startswith(ACTIVE_STATUS_PREFIXES) or status.endswith(
        "scheduled"
    )
    if row["court_status_active"]:
        row["final_disposition_date"] = None
    else:
        row["final_disposition_date"] = row["closed_date"] or (min(ends) if ends else None)
    row["first_entry_date"] = first_entry
    return row, ents


def _cached_json(url_contains: str):
    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if url_contains in meta["url"] and 200 <= meta["status"] < 300:
            yield meta, json.loads((raw / meta["file"]).read_text(encoding="utf-8"))


LEDGER = "_listing_ledger.json"


def listing_ledger() -> dict[str, dict]:
    """Every file the court's search has ever listed for us, with the row as last listed and
    the date it was last listed (``_last_listed``).

    The weekly refresh re-fetches each year's listing over the cached copy, so the cache holds
    only what the court lists today. Between 16 and 19 November 2026 the court's listing
    shrank from 29,714 files to about 4,700 with no pattern we could find; files that drop out
    of the listing stay in the census through this ledger (raw data, contains names, stays in
    data/raw). Updated from the cache on every parse."""
    path = paths.raw_dir(SOURCE) / LEDGER
    ledger = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for meta, j in _cached_json("/appealnumber/courtnumber"):
        for row in j.get("data") or []:
            nbr = (row.get("APPEAL_NBR") or "").strip()
            if nbr:
                ledger[nbr] = {**row, "_last_listed": meta["fetched_at"][:10]}
    path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    return ledger


def parse(client: Client | None = None):
    import polars as pl

    listing = listing_ledger()
    latest = max((r["_last_listed"] for r in listing.values()), default=None)
    entries: dict[str, tuple[list, str]] = {}
    for meta, j in _cached_json("/appealnumberRE"):
        nbr = meta["url"].split("appealnumber=")[1].split("&")[0]
        from urllib.parse import unquote

        entries[unquote(nbr)] = (j.get("data") or [], meta["fetched_at"])
    rows, erows, dropped, missing = [], [], 0, 0
    for nbr, lrow in listing.items():
        if nbr not in entries:
            missing += 1
            continue
        ents, fetched_at = entries[nbr]
        row, er = parse_file(lrow, ents, fetched_at)
        if row is None:
            dropped += 1
            continue
        # still on the court's public listing at our latest reading of it?
        row["last_listed"] = _d(lrow.get("_last_listed"))
        row["listed_now"] = lrow.get("_last_listed") == latest
        rows.append(row)
        erows.extend(er)
    out = paths.processed_dir() / "s12"
    out.mkdir(exist_ok=True)
    d = pl.DataFrame(rows, infer_schema_length=None)
    e = pl.DataFrame(erows, infer_schema_length=None)
    if d.height:
        d.write_parquet(out / "dockets.parquet")
        e.write_parquet(out / "entries.parquet")
    log.info(
        "S12: %d files parsed, %d confidential dropped, %d listed but entries not yet fetched",
        d.height,
        dropped,
        missing,
    )
    return {"dockets": d, "entries": e, "dropped": dropped, "missing": missing}


def validate(frames) -> None:
    import polars as pl

    d = frames["dockets"]
    if d.height == 0:
        raise ValueError("S12: no files parsed")
    by = (
        d.group_by(["docket_year", "procedure"])
        .agg(
            pl.len().alias("n"),
            pl.col("final_disposition_date").is_not_null().mean().alias("closed_share"),
            pl.col("first_hearing_date").is_not_null().mean().alias("heard_share"),
        )
        .sort(["docket_year", "procedure"])
    )
    log.info("S12 by year and procedure:\n%s", by)
    log.info(
        "S12 filing date source:\n%s\n%d listed filing dates rejected as implausible",
        d.group_by("date_filed_source").len().sort("len", descending=True),
        d["listed_filed_date_implausible"].sum(),
    )
    other = frames["entries"].filter(pl.col("entry_type") == "other").height
    log.info("S12: %d of %d entries unclassified", other, frames["entries"].height)
