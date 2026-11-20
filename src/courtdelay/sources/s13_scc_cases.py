"""S13: Supreme Court of Canada case information (one docket page per file).

Owner approval 2026-11-19, for the leave-application stage of appeal chains. Tier 2 rules apply:
robots and terms recorded in docs/sources.md, one request at a time at the default spacing, and
names dropped at parse.

Frame: the court's own site map lists every case page
(``/cases-dossiers/search-recherche/{case number}``). The site's search form is not used (it
queries a third-party search service). One request per file. Links on the pages (some point to
other sites) are never followed.

Each page has a docket table (Date, Proceeding, Filed by), then Parties, Counsel, Summary and a
"Lower court rulings" block. Kept: the case number; the court appealed from with its file number,
neutral citation and judgment date; and each docket entry's date and *type* (leave application
filed, submitted to the Court, leave decision, hearing, judgment, closed). Not kept: party and
counsel names, the style of cause, entry text, the "Filed by" column, the summary.
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s13_scc_cases"
TIER = 2
SITEMAP = "https://www.scc-csc.ca/en/sitemap.xml"
CASE_URL = "https://www.scc-csc.ca/cases-dossiers/search-recherche/{n}/"
CASE_RE = re.compile(r"/cases-dossiers/search-recherche/(\d{5})/?<")
MAX_CONSECUTIVE_ERRORS = 5
SEED = 20261119
#: first case number of the default frame (files opened from about 2010)
FIRST_CASE = 33500


class CrawlAborted(RuntimeError):
    """Five failed requests in a row (site down or blocking). The cache keeps what was fetched."""


def list_cases(client: Client) -> list[int]:
    """Case numbers from the court's site map, ascending."""
    xml = client.get(SITEMAP, source=SOURCE, tier=TIER).text
    return sorted({int(n) for n in CASE_RE.findall(xml)})


def fetch(client: Client, strata: list[str] | None = None, first_case: int = FIRST_CASE) -> dict:
    """Fetch case pages. ``strata``: ["pilot"] fetches 20 seeded-random recent cases; otherwise
    every case from ``first_case`` up. Resumable: cached pages are not requested again."""
    cases = [n for n in list_cases(client) if n >= first_case]
    if strata and "pilot" in strata:
        cases = sorted(random.Random(SEED).sample([n for n in cases if n >= 38000], 20))
    errors, fetched, failed = 0, 0, 0
    for i, n in enumerate(cases, 1):
        try:
            client.get(CASE_URL.format(n=n), source=SOURCE, tier=TIER)
            fetched, errors = fetched + 1, 0
        except FetchError as exc:
            failed, errors = failed + 1, errors + 1
            log.warning("S13 case %s: %s", n, exc)
            if errors >= MAX_CONSECUTIVE_ERRORS:
                raise CrawlAborted(f"{errors} failed requests in a row; last: {exc}") from exc
        if i % 100 == 0:
            _progress({"at": n, "fetched": fetched, "failed": failed, "of": len(cases)})
    result = {"cases": len(cases), "fetched": fetched, "failed": failed}
    _progress({"done": True, **result})
    return result


def _progress(row: dict) -> None:
    with (paths.raw_dir(SOURCE) / "progress.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


# -- parse --------------------------------------------------------------------------------------

# Matched against the Registry's standard label (the text before the first comma). First match
# wins. Wording confirmed on the 20-page pilot of 2026-11-19.
ENTRY_TYPES: list[tuple[str, re.Pattern]] = [
    ("leave_filed", re.compile(r"^application for leave to appeal$", re.I)),
    ("leave_submitted", re.compile(r"^all materials on application for leave submitted", re.I)),
    ("leave_notice", re.compile(r"^notice of application for leave to appeal$", re.I)),
    (
        "leave_decision",
        re.compile(r"^judgment of the court on the applications? for leave to appeal$", re.I),
    ),
    (
        "cross_leave_decision",
        re.compile(r"^judgment of the court on the applications? for leave to cross", re.I),
    ),
    ("leave_discontinued", re.compile(r"^discontinuance of the application for leave", re.I)),
    ("appeal_perfected", re.compile(r"^appeal perfected for hearing", re.I)),
    ("leave_closed", re.compile(r"^close file on leave", re.I)),
    ("notice_of_appeal", re.compile(r"^notice of appeal$", re.I)),
    ("hearing", re.compile(r"^hearing of the appeal", re.I)),
    ("judgment_reserved", re.compile(r"^judgment reserved", re.I)),
    ("judgment", re.compile(r"^judgment on the appeal rendered", re.I)),
    ("discontinuance", re.compile(r"^notice of discontinuance", re.I)),
    ("closed", re.compile(r"^appeal closed|^close file", re.I)),
    # a standard form the parties file; counted, never read as a sealing marker on its own
    ("access_certificate", re.compile(r"^certificate \(on limitations to public access\)", re.I)),
]
# "... from the judgment of the <court>, Number <file>, <citation>, dated <date>, is <result>"
# The court is read only when it directly follows "judgment(s) of the" / "order of the", so a
# judge's name ("the direction of ... J.A. of the ...") is never captured.
LEAVE_TEXT_RE = re.compile(
    r"from the (?:judgments?|orders?|decisions?) of the (?P<court>[^,]+?), Numbers?,? "
    r"(?P<body>.+?),? dated? (?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})"
    r"(?:.*?\b(?:is|are) (?P<result>granted|dismissed|quashed|remanded))?",
    re.S,
)
CITE_RE = re.compile(r"\b\d{4} [A-Z]{2,6} \d+\b")
# counted per file, as for the Federal Court files; files are kept (aggregates only)
MARKER_RE = re.compile(r"pub-?ban|publication ban|sealed|sealing|confidential", re.I)
COMPLETED_RE = re.compile(r"completed on:? (\d{4}-\d{2}-\d{2})", re.I)
# the Registry's short result label, on its own line at the end of a leave-judgment entry
RESULT_LABELS = [
    ("granted", re.compile(r"^granted", re.I)),
    ("dismissed", re.compile(r"^dismissed", re.I)),
    ("quashed", re.compile(r"^quashed", re.I)),
    ("remanded", re.compile(r"^remand", re.I)),
    ("oral_hearing", re.compile(r"^oral hearing ordered", re.I)),
]
RESULT_RANK = {"granted": 0, "remanded": 1, "quashed": 2, "dismissed": 3, "oral_hearing": 4}


def classify(label: str | None) -> str:
    t = (label or "").split(",")[0].strip()
    for name, rx in ENTRY_TYPES:
        if rx.search(t):
            return name
    return "other"


def _d(s: str | None) -> date | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (s or "").strip())
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _long_date(s: str | None) -> date | None:
    try:
        return datetime.strptime((s or "").strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def result_label(label: str | None) -> str | None:
    """Leave result from the Registry's short label ("Dismissed, with costs" -> dismissed)."""
    t = (label or "").strip()
    return next((name for name, rx in RESULT_LABELS if rx.search(t)), None)


def _file_tokens(body: str) -> list[str]:
    """Lower-court file numbers in a "Numbers X and Y, <citation>" passage: pieces with a digit
    that are not neutral citations."""
    pieces = re.split(r",|;|\band\b|\bet\b", CITE_RE.sub(" ", re.sub(r"\(.*?\)", " ", body)))
    out = [" ".join(x.split()) for x in pieces]
    return [x for x in out if re.search(r"\d", x) and len(x) <= 30]


def leave_details(text: str) -> dict:
    """Court appealed from, its file number(s), citation and judgment date, and the leave
    result, from the wording of the Registry's leave-judgment entry. Empty when the wording
    does not match."""
    m = LEAVE_TEXT_RE.search(text or "")
    if not m:
        return {}
    files = _file_tokens(m.group("body"))
    cite = CITE_RE.search(m.group("body"))
    return {
        "court_appealed_from": m.group("court").strip(),
        "lower_court_file": files[0] if files else None,
        "lower_court_files": "; ".join(files) or None,
        "lower_court_citation": cite.group(0) if cite else None,
        "lower_court_judgment_date": _long_date(m.group("date")),
        "leave_result": (m.group("result") or "").lower() or None,
    }


def lower_rulings(main) -> dict:
    """Fallback for files with no leave judgment yet: the last row of the page's "Lower court
    rulings" block (date, court, then citation and file numbers)."""
    head = next(
        (h for h in main.find_all(["h3", "h4", "h5"]) if "Lower court rulings" in h.get_text()),
        None,
    )
    block = head.find_next("div") if head else None
    rows = block.find_all("div", class_="row") if block else []
    parsed = []
    for row in rows:
        cell = row.find("div")
        parts = [p.strip() for p in cell.get_text("\n").split("\n") if p.strip()] if cell else []
        if len(parts) >= 2 and _long_date(parts[0]):
            parsed.append(parts)
    if not parsed:
        return {}
    parts = parsed[-1]
    rest = " ".join(parts[2:])
    cite = CITE_RE.search(rest)
    files = _file_tokens(rest)
    out = {
        "court_appealed_from": parts[1],
        "lower_court_file": files[0] if files else None,
        "lower_court_files": "; ".join(files) or None,
        "lower_court_citation": cite.group(0) if cite else None,
        "lower_court_judgment_date": _long_date(parts[0]),
        "n_lower_rulings": len(parsed),
    }
    if len(parsed) >= 2 and parsed[0][1] != parts[1]:
        # the earliest ruling listed, when it is from a different court (the court of first
        # instance for most files)
        out["first_ruling_court"] = parsed[0][1]
        out["first_ruling_date"] = _long_date(parsed[0][0])
    return out


def parse_page(html: str, case_no: int, fetched_at: str) -> tuple[dict, list[dict]]:
    """One case page -> (case row, entry rows). No names, no entry text."""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    entries, leave, completed, markers = [], [], None, 0
    for tb in main.find_all("table"):
        hdr = [" ".join(th.get_text().split()).lower() for th in tb.find_all("th")]
        if not (hdr and hdr[0] == "date" and any("proceeding" in h for h in hdr)):
            continue
        for tr in tb.find_all("tr"):
            tds = tr.find_all("td")
            cells = [" ".join(td.get_text().split()) for td in tds]
            if len(cells) >= 2 and _d(cells[0]):
                et = classify(cells[1])
                markers += bool(MARKER_RE.search(cells[1]))
                if et == "leave_decision":
                    lines = [x.strip() for x in tds[1].get_text("\n").split("\n") if x.strip()]
                    det = leave_details(cells[1])
                    res = result_label(lines[-1] if len(lines) > 1 else None)
                    leave.append((_d(cells[0]), res or det.get("leave_result"), det))
                elif et == "leave_filed" and (m := COMPLETED_RE.search(cells[1])):
                    completed = min(filter(None, [completed, _d(m.group(1))]))
                entries.append({"case_no": case_no, "entry_date": _d(cells[0]), "entry_type": et})
        break

    def first(t: str) -> date | None:
        ds = [e["entry_date"] for e in entries if e["entry_type"] == t]
        return min(ds) if ds else None

    origin = {
        "court_appealed_from": None,
        "lower_court_file": None,
        "lower_court_files": None,
        "lower_court_citation": None,
        "lower_court_judgment_date": None,
        "n_lower_rulings": 0,
        "first_ruling_court": None,
        "first_ruling_date": None,
    }
    origin.update(lower_rulings(main))
    # Unit is the file. A file can carry more than one leave judgment (several applications,
    # a remand, an oral hearing ordered first). The file's leave decision is the latest one;
    # where several fall on that date, the most favourable result is taken. The court appealed
    # from is read from the earliest leave judgment whose wording gives it.
    last = max((d for d, _, _ in leave), default=None)
    results = [r for d, r, _ in leave if d == last and r]
    for _, _, det in sorted(leave, key=lambda x: x[0]):
        if det:
            origin.update({k: v for k, v in det.items() if v is not None and k != "leave_result"})
            break
    origin["leave_result"] = min(results, key=lambda r: RESULT_RANK.get(r, 9), default=None)
    origin["leave_granted_any"] = any(r == "granted" for _, r, _ in leave) if leave else None
    row = {
        "case_no": case_no,
        "scraped": fetched_at[:10],
        "n_entries": len(entries),
        "first_entry_date": min((e["entry_date"] for e in entries), default=None),
        "leave_filed_date": first("leave_filed"),
        "leave_submitted_date": first("leave_submitted"),
        "leave_completed_date": completed,
        "leave_notice_date": first("leave_notice"),
        "leave_first_decision_date": first("leave_decision"),
        "leave_decision_date": last,
        "n_leave_decision_dates": len({d for d, _, _ in leave}),
        "leave_discontinued_date": first("leave_discontinued"),
        "appeal_perfected_date": first("appeal_perfected"),
        "notice_of_appeal_date": first("notice_of_appeal"),
        "hearing_date": first("hearing"),
        "judgment_date": first("judgment"),
        "closed_date": max(
            (e["entry_date"] for e in entries if e["entry_type"] in {"closed", "leave_closed"}),
            default=None,
        ),
        "n_restriction_marker_entries": markers,
        "n_access_certificates": sum(e["entry_type"] == "access_certificate" for e in entries),
        **origin,
    }
    return row, entries


def _cached_pages():
    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        m = re.search(r"/search-recherche/(\d{5})/?$", meta["url"])
        if m and 200 <= meta["status"] < 300:
            html = (raw / meta["file"]).read_text(encoding="utf-8")
            yield int(m.group(1)), html, meta["fetched_at"]


def parse(client: Client | None = None):
    import polars as pl

    cases, entries = [], []
    for case_no, html, fetched_at in _cached_pages():
        row, ents = parse_page(html, case_no, fetched_at)
        cases.append(row)
        entries.extend(ents)
    out = paths.processed_dir() / "s13"
    out.mkdir(exist_ok=True)
    c = pl.DataFrame(cases, infer_schema_length=None)
    e = pl.DataFrame(entries, infer_schema_length=None)
    if c.height:
        c.write_parquet(out / "cases.parquet")
        e.write_parquet(out / "entries.parquet")
    log.info("S13: %d case pages parsed, %d entries", c.height, e.height)
    return {"cases": c, "entries": e}


def validate(frames) -> None:
    import polars as pl

    c, e = frames["cases"], frames["entries"]
    if c.height == 0:
        raise ValueError("S13: no case pages parsed")
    empty = c.filter(pl.col("n_entries") == 0).height
    other = e.filter(pl.col("entry_type") == "other").height
    decided = c.filter(pl.col("leave_decision_date").is_not_null())
    log.info(
        "S13: %d cases; %d with no docket entries; %.0f%% of entries unclassified (filings and "
        "correspondence); leave filed found for %.0f%%, leave decision for %.0f%%; among decided, "
        "result read for %.0f%% and court appealed from for %.0f%%; court known for %.0f%% of all",
        c.height,
        empty,
        100 * other / max(e.height, 1),
        100 * c["leave_filed_date"].is_not_null().mean(),
        100 * c["leave_decision_date"].is_not_null().mean(),
        100 * (decided["leave_result"].is_not_null().mean() or 0),
        100 * (decided["court_appealed_from"].is_not_null().mean() or 0),
        100 * c["court_appealed_from"].is_not_null().mean(),
    )
    if empty > 0.2 * c.height:
        raise ValueError(f"S13: {empty} of {c.height} pages have no docket table")
