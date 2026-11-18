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
    ("discontinuance", re.compile(r"discontinu|d[ée]sistement|withdraw", re.I)),
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
    ("judgment", re.compile(r"^(?:amended )?judgment\b(?!.*\bsent\b)", re.I)),
    ("consent", re.compile(r"consent (?:to judgment|allowed|dismissed)", re.I)),
    # a bare "Dismissed" entry ends the file; 42 files (2018-2026) have no other end event
    ("dismissed", re.compile(r"^dismissed\b", re.I)),
    # abeyance pauses the file at a party's request (often pending a related decision): time
    # in abeyance is not calendar delay, so it is recorded separately
    ("abeyance_requested", re.compile(r"^request to be held in abeyance", re.I)),
    ("abeyance", re.compile(r"^held in abeyance", re.I)),
    ("case_mgmt_scheduled", re.compile(r"^case management conference scheduled", re.I)),
    ("order", re.compile(r"\border\b", re.I)),
]


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

    def first(t):
        return next((e["entry_date"] for e in ents if e["entry_type"] == t), None)

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
            "date_filed": _d(listing.get("FILED_DATE")) or first("notice_of_appeal"),
            "reply_date": first("reply"),
            "first_scheduled_date": first("scheduled"),
            "first_hearing_date": first("hearing_held"),
            "hearing_requested_date": first("hearing_requested"),
            "n_case_mgmt_conferences": sum(e["entry_type"] == "case_mgmt_held" for e in ents),
            "n_adjournment_requests": sum(e["entry_type"] == "adjournment_requested" for e in ents),
            "judgment_date": first("judgment"),
            "discontinuance_date": first("discontinuance"),
            "closed_date": first("file_closed"),
            "dismissed_date": first("dismissed"),
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
            row["dismissed_date"],
        )
        if d
    ]
    row["final_disposition_date"] = row["closed_date"] or (min(ends) if ends else None)
    return row, ents


def _cached_json(url_contains: str):
    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if url_contains in meta["url"] and 200 <= meta["status"] < 300:
            yield meta, json.loads((raw / meta["file"]).read_text(encoding="utf-8"))


def parse(client: Client | None = None):
    import polars as pl

    listing: dict[str, dict] = {}
    for _meta, j in _cached_json("/appealnumber/courtnumber"):
        for row in j.get("data") or []:
            if row.get("APPEAL_NBR"):
                listing[row["APPEAL_NBR"].strip()] = row
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
    other = frames["entries"].filter(pl.col("entry_type") == "other").height
    log.info("S12: %d of %d entries unclassified", other, frames["entries"].height)
