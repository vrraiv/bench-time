"""S10 + S11: Federal Court and Federal Court of Appeal dockets (Tier 2).

Verified 2026-11-16 from the Court's own page scripts (docs/sources.md S10): the "Court Files" page
calls JSON endpoints on www.fct-cf.ca with ``division`` = "t" (Federal Court) or "a" (Federal Court
of Appeal) and ``courtnumber`` (e.g. IMM-1234-23, T-567-24, A-89-25):

  GET /CourtFilesAndDecisions/proceedingQueriesAddInfo?division=&courtnumber=   file information
  GET /CourtFilesAndDecisions/proceedingQueriesRE?division=&courtnumber=        recorded entries

Two requests per file at the client's 4 s per-host spacing (single-threaded), every response cached
under data/raw/s10_fc_fca_dockets/ (gitignored, local only; responses include party names). The
parser keeps file number, dates, entry types and outcomes only; names are dropped at parse time.

Sampling plan (owner decision 2026-11-16; docs/methods.md E1):
  FCA ("A-")         census by filing year
  FC general ("T-")  census by filing year
  FC immigration     simple random sample of 1,000 files per filing year from 2023 on
                     (Refugee Law Lab covers 1997-2022)
Docket numbers are sequential within a year (N = 1, 2, ...). A census walks N upward and stops after
``STOP_AFTER_MISSES`` consecutive numbers that do not exist. A sample first finds the year's
highest existing N by galloping search, then draws N uniformly without replacement (seeded);
non-existent numbers are recorded as misses and replaced from the reserve draw.

Everything is resume-safe: the plan (sample lists, seeds, frame sizes) is written to
``plan_<stratum>.json`` before crawling, and the HTTP cache means a restarted run never re-fetches.
Progress is appended to ``progress_<stratum>.jsonl``. The client refuses all of this while
COURTDELAY_CONTACT is unset.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import asdict, dataclass

from courtdelay.common import paths
from courtdelay.common.http import Client, FetchError

log = logging.getLogger(__name__)

SOURCE = "s10_fc_fca_dockets"
BASE = "https://www.fct-cf.ca/CourtFilesAndDecisions"
ADDINFO = f"{BASE}/proceedingQueriesAddInfo"
ENTRIES = f"{BASE}/proceedingQueriesRE"
TIER = 2
STOP_AFTER_MISSES = 200
SEED = 20261116


@dataclass(frozen=True)
class Stratum:
    name: str  # e.g. "FCA-2024"
    prefix: str  # "A", "T", "IMM"
    division: str  # "a" or "t"
    year: int  # filing year (4-digit)
    mode: str  # "census" | "sample"
    n_sample: int = 0

    def number(self, n: int) -> str:
        return f"{self.prefix}-{n}-{self.year % 100:02d}"


def default_plan(
    fca_years=range(2010, 2027), fc_general_years=range(2018, 2027), imm_years=range(2023, 2027)
) -> list[Stratum]:
    plan = [Stratum(f"FCA-{y}", "A", "a", y, "census") for y in fca_years]
    plan += [Stratum(f"FCT-{y}", "T", "t", y, "census") for y in fc_general_years]
    plan += [Stratum(f"IMM-{y}", "IMM", "t", y, "sample", 1000) for y in imm_years]
    # overlap sample (owner approval 2026-11-18): 300 files from the last filing year the Refugee
    # Law Lab series covers, to check that S4 and this source measure the same stages alike
    plan.append(Stratum("IMM-2022", "IMM", "t", 2022, "sample", 300))
    return plan


# -- requests -------------------------------------------------------------------------------


def _get(client: Client, url: str, s: Stratum, number: str):
    return client.get(
        url, source=SOURCE, tier=TIER, params={"division": s.division, "courtnumber": number}
    )


def exists(payload) -> bool:
    """True if an additional-info response describes a real file. The response shape is
    confirmed in the pilot; until then accept any non-empty 'data' list or non-empty object."""
    if payload is None:
        return False
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        return bool(data) if isinstance(data, list | dict) else bool(payload)
    if isinstance(payload, list):
        return len(payload) > 0
    return False


MAX_CONSECUTIVE_ERRORS = 5
_consecutive_errors = 0


class CrawlAborted(RuntimeError):
    """Raised after MAX_CONSECUTIVE_ERRORS failed requests in a row (site down, TLS failure,
    blocking). The cache keeps everything fetched so far; rerunning resumes."""


def _record_failure(s: Stratum, number: str, exc: Exception) -> None:
    global _consecutive_errors
    _consecutive_errors += 1
    with (paths.raw_dir(SOURCE) / f"failures_{s.name}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"docket": number, "error": str(exc)[:300]}) + "\n")
    log.warning("%s %s: %s", s.name, number, exc)
    if _consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        raise CrawlAborted(
            f"{_consecutive_errors} consecutive request failures; last: {exc}"
        ) from exc


def fetch_file(client: Client, s: Stratum, n: int) -> bool | None:
    """Fetch both endpoints for one file number. Returns True (file exists, both fetched),
    False (no such file) or None (a request failed: neither a hit nor a miss; logged to
    failures_<stratum>.jsonl for a later retry)."""
    global _consecutive_errors
    number = s.number(n)
    try:
        info = _get(client, ADDINFO, s, number)
        try:
            payload = info.json()
        except ValueError:
            payload = None
        if not exists(payload):
            _consecutive_errors = 0
            return False
        _get(client, ENTRIES, s, number)
    except FetchError as exc:
        _record_failure(s, number, exc)
        return None
    _consecutive_errors = 0
    return True


def highest_number(client: Client, s: Stratum, hint: int = 1000) -> int:
    """Galloping then binary search for the highest existing N in a year. Files are sequential, so
    existence is (nearly) monotone; runs of missing numbers (withdrawn or sealed files) up to ~50
    long are tolerated by probing N, N+3, N+10, N+25 and N+50. Underestimating the frame would
    silently drop the year's latest filings, so this errs towards probing more."""

    def any_exists(n: int) -> bool:
        return any(fetch_file(client, s, n + k) is True for k in (0, 3, 10, 25, 50))

    lo, hi = 0, max(hint, 1)
    while any_exists(hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if any_exists(mid):
            lo = mid
        else:
            hi = mid
    return lo


def _progress(s: Stratum, row: dict) -> None:
    with (paths.raw_dir(SOURCE) / f"progress_{s.name}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def crawl_census(client: Client, s: Stratum, *, start: int = 1) -> dict:
    misses, n, found = 0, start, 0
    while misses < STOP_AFTER_MISSES:
        r = fetch_file(client, s, n)
        if r is True:
            found, misses = found + 1, 0
        elif r is False:
            misses += 1
        if n % 50 == 0:
            _progress(s, {"n": n, "found": found})
        n += 1
    result = {"stratum": s.name, "last_n_probed": n - 1, "found": found}
    _progress(s, {"done": True, **result})
    return result


def make_sample_plan(client: Client, s: Stratum, hint: int) -> dict:
    plan_path = paths.raw_dir(SOURCE) / f"plan_{s.name}.json"
    if plan_path.exists():
        return json.loads(plan_path.read_text())
    max_n = highest_number(client, s, hint)
    rng = random.Random(f"{SEED}-{s.name}")
    order = list(range(1, max_n + 1))
    rng.shuffle(order)
    plan = {"stratum": asdict(s), "frame_max_n": max_n, "seed": f"{SEED}-{s.name}", "order": order}
    plan_path.write_text(json.dumps(plan))
    return plan


def crawl_sample(client: Client, s: Stratum, hint: int = 8000) -> dict:
    plan = make_sample_plan(client, s, hint)
    found, tried = 0, 0
    for n in plan["order"]:
        if found >= s.n_sample:
            break
        tried += 1
        if fetch_file(client, s, n) is True:
            found += 1
        if tried % 50 == 0:
            _progress(s, {"tried": tried, "found": found})
    result = {"stratum": s.name, "frame_max_n": plan["frame_max_n"], "tried": tried, "found": found}
    _progress(s, {"done": True, **result})
    return result


# -- list sample: immigration files opened before 2022 and still open in November 2022 ----------
#
# Owner approval 2026-11-22. The Court's pending count includes immigration files older than our
# 2022+ sample. The Refugee Law Lab dockets (S4) give every such file as of November 2022; this
# stratum draws from the ones S4 shows without an ending and reads their state today, to see how
# many are still open and when the others closed. Files S4 shows as ended are assumed to have
# stayed ended.

PRE2022 = "IMM-PRE2022"
PRE2022_GROUPS = {  # filing-year group -> files to fetch
    "2021": 300,  # 1,092 in the frame, all active in 2021-22
    "2018-2020": 150,  # 347 in the frame
    "2011-2017": 150,  # about 5,000, last active 2013-2018: mostly endings S4 does not show
    "to-2010": 60,  # about 1,100, last active in their filing year
}


def pre2022_group(filing_year: int) -> str:
    if filing_year >= 2021:
        return "2021"
    if filing_year >= 2018:
        return "2018-2020"
    return "2011-2017" if filing_year >= 2011 else "to-2010"


def pre2022_plan_path():
    return paths.raw_dir(SOURCE) / f"plan_{PRE2022}.json"


def make_pre2022_plan() -> dict:
    """Frame: S4 files filed before 2022 with no ending recorded at the 2022 scrape, in four
    filing-year groups; each group's files in seeded random order. Written once."""
    import polars as pl

    plan_path = pre2022_plan_path()
    if plan_path.exists():
        return json.loads(plan_path.read_text())
    d = pl.read_parquet(paths.processed_dir() / "s4" / "dockets.parquet").filter(
        (pl.col("filing_year") < 2022) & pl.col("final_disposition_date").is_null()
    )
    groups = {}
    for g in PRE2022_GROUPS:
        nos = sorted(
            r["docket"]
            for r in d.select("docket", "filing_year").iter_rows(named=True)
            if pre2022_group(r["filing_year"]) == g
        )
        random.Random(f"{SEED}-{PRE2022}-{g}").shuffle(nos)
        groups[g] = {"frame_n": len(nos), "n_sample": PRE2022_GROUPS[g], "order": nos}
    plan = {"stratum": PRE2022, "seed": f"{SEED}-{PRE2022}-<group>", "groups": groups}
    plan_path.write_text(json.dumps(plan))
    return plan


def crawl_pre2022(client: Client, limit: int | None = None) -> dict:
    """``limit`` caps the files per group (pilot)."""
    plan = make_pre2022_plan()
    result = {"stratum": PRE2022}
    for g, grp in plan["groups"].items():
        want = min(grp["n_sample"], limit or grp["n_sample"])
        found = tried = 0
        for docket in grp["order"]:
            if found >= want:
                break
            prefix, n, yy = docket.split("-")
            s = Stratum(
                PRE2022, prefix, "t", 1900 + int(yy) if int(yy) > 50 else 2000 + int(yy), "list"
            )
            tried += 1
            if fetch_file(client, s, int(n)) is True:
                found += 1
        result[g] = {"frame_n": grp["frame_n"], "tried": tried, "found": found}
        _progress(Stratum(PRE2022, "IMM", "t", 0, "list"), {"group": g, **result[g]})
    return result


def run_stratum(client: Client, s: Stratum) -> dict:
    return crawl_census(client, s) if s.mode == "census" else crawl_sample(client, s)


def fetch(client: Client, strata: list[str] | None = None) -> list[dict]:
    plan = default_plan()
    out = []
    if strata:
        # the pre-2022 list sample runs only when named; "IMM-PRE2022:40" caps each group at 40
        for name in strata:
            if name.split(":")[0] == PRE2022:
                limit = int(name.split(":")[1]) if ":" in name else None
                out.append(crawl_pre2022(client, limit))
        plan = [s for s in plan if s.name in strata]
    return out + [run_stratum(client, s) for s in plan]


# -- parse ---------------------------------------------------------------------------------

# Fields kept from the file-information record. STYLE_OF_CAUSE, Party and Ships are never read.
INFO_FIELDS = {
    "COURT_NO": "docket",
    "DIVISION": "division",
    "OFF_CD": "office",
    "PRCDG_TYPE": "proceeding_type_code",
    "ENGLISH_PROCEEDING_TYPE": "proceeding_type",
    "ENGLISH_NATURE_DESC": "nature",
    "ENGLISH_PROCEEDING_CLASS": "proceeding_class",
    "LANG_CD": "language",
}


# Owner decision 2026-11-19: keep files that carry a confidentiality marker; count the markers.
DROP_MARKED_FILES = False
REGISTRATION_RE = r"copy of decision|certificate"
PUBLICATION_BAN_RE = r"publication\s+ban|non-?publication|interdiction\s+de\s+publication"


# An appeal's opening entries usually name the file appealed from ("Notice of Appeal filed on ...
# against a decision ... dated 12-MAR-2021 in T-123-19"). A court file number, not a name.
LOWER_FC_NO_RE = r"\b(T|IMM|DES|ITA|GST|P)-0*(\d{1,5})-(\d{2})\b"
LOWER_TCC_NO_RE = r"\b((?:19|20)\d{2})-0*(\d{1,5})\s*\(([A-Z]{2,4})\)\s*(APP|G|I)?(?![A-Za-z])"
LOWER_DATED_RE = r"\b(?:dated|dat[ée]e?\s+du|en\s+date\s+du)\s+(\d{1,2}-[A-Za-zÉÛéû]{3,4}-\d{4})"


def appeal_from(entries: list[dict]) -> tuple[str | None, str | None]:
    """(lower-court file number, date of the decision appealed from) read from an appeal's first
    six entries; (None, None) when they name no file."""
    import re

    first = sorted(entries, key=lambda e: ((e.get("DOC_DT") or "")[:10], e.get("RE_NO") or 0))[:6]
    for e in first:
        t = e.get("RECORDED_ENTRY") or ""
        m = re.search(LOWER_FC_NO_RE, t)
        if m:
            number = f"{m.group(1)}-{int(m.group(2))}-{m.group(3)}"
        else:
            m = re.search(LOWER_TCC_NO_RE, t)
            if not m:
                continue
            number = f"{m.group(1)}-{int(m.group(2))}({m.group(3)}){m.group(4) or ''}"
        dm = re.search(LOWER_DATED_RE, t, re.I)
        return number, dm.group(1) if dm else None
    return None, None


# One order made in a lead file can end many files: the Registry places a copy on each ("Copy of
# Order dated 27-APR-2020 rendered by ... placed on file. Original filed on Court File No.
# T-2126-18") and the copy carries no final-decision marker. Found 2026-11-22: 381 Federal Court
# files we counted as open carry a copy of an order that ended its own file on that date (213
# from one order dismissing a list of actions against the Crown in 2020, 74 from one striking
# another list in 2023), and the Court's disposition counts include them.
COPY_OF_DECISION_RE = re.compile(
    r"^\s*(?:copy of|copie d[eu']\s*(?:la |l')?)\s*(?:reasons for )?"
    r"(?:order|judgment|ordonnance|jugement|reasons|motifs)[^\n]{0,60}?"
    r"(?:dated|en date du)\s+(\d{1,2}-[A-Za-zéû]{3,4}-\d{4})",
    re.I,
)
ORIGINAL_ON_RE = re.compile(
    r"(?:court file no\.?|dossier[^\n]{0,30}?)\s*((?:T|A|IMM)-\d+-\d\d)\b", re.I
)


def copies_of_decisions(texts: list[str], own: str | None) -> list[tuple[str, str]]:
    """(file the original is on, decision date as written) for each copy of an order or judgment
    from another file placed on this one."""
    out = []
    for t in texts:
        m, src = COPY_OF_DECISION_RE.search(t), ORIGINAL_ON_RE.search(t)
        if m and src and src.group(1).upper() != (own or "").upper():
            out.append((src.group(1).upper(), m.group(1)))
    return out


def add_lead_file_endings(rows: list[dict]) -> int:
    """Fill ``lead_order_end_date`` / ``lead_order_file`` on files with no ending of their own
    that carry a copy of a decision which ended the file it was made in, on that date. Kept apart
    from ``final_disposition_date``: whether the tables should count these is the owner's call.
    Returns the number of files filled."""
    from courtdelay.sources import s4_rll_fc_dockets as s4

    ended = {
        (r["division"], r["docket"]): (r["final_disposition_date"], r["final_disposition_type"])
        for r in rows
        if r.get("final_disposition_date") is not None
    }
    n = 0
    for r in rows:
        r["lead_order_end_date"], r["lead_order_file"] = None, None
        copies = r.pop("_copies", [])
        if r.get("final_disposition_date") is not None:
            continue
        for lead, written in copies:
            end = ended.get((r["division"], lead))
            if end and end[1] != "discontinuance" and s4.parse_entry_date(written) == end[0]:
                r["lead_order_end_date"], r["lead_order_file"] = end[0], lead
                n += 1
                break
    return n


def ms_date(v):
    """'/Date(1735794000000)/' (UTC milliseconds) -> local (Eastern) calendar date. The Court stores
    midnight Eastern, i.e. 04:00 UTC in daylight time and 05:00 UTC in standard time (a few carry a
    daytime clock time). Subtracting 4 hours gives the intended day in both seasons; subtracting 5
    put daylight-time filings on the previous day (found with the IMM-2022 overlap, 2026-11-19).
    No tz database is used: tzdata is not installed on the Windows dev machine."""
    import re
    from datetime import UTC, datetime, timedelta

    if not v:
        return None
    m = re.search(r"(-?\d+)", str(v))
    if not m:
        return None
    return (datetime.fromtimestamp(int(m.group(1)) / 1000, UTC) - timedelta(hours=4)).date()


def parse_file(info: dict, entries: list[dict], fetched_at: str) -> tuple[dict | None, list[dict]]:
    """One docket -> (docket row, entry rows), names dropped.

    Confidentiality markers are counted per file, not acted on (owner decision 2026-11-19: the
    court publishes these files, so the markers are presumed to mean a sealed document or a
    commercial confidentiality order, not a sealed proceeding; pending practitioner review).
    With ``DROP_MARKED_FILES`` set, a marked file returns (None, []) as the handoff first asked."""
    import re

    from courtdelay.sources import s4_rll_fc_dockets as s4

    texts = [e.get("RECORDED_ENTRY") or "" for e in entries]
    n_flag = sum(str(e.get("IS_CONFIDENTIAL", "N")).upper() == "Y" for e in entries)
    n_sealed = sum(bool(s4.SEALED_RE.search(t)) for t in texts)
    n_ban = sum(bool(re.search(PUBLICATION_BAN_RE, t, re.I)) for t in texts)
    if DROP_MARKED_FILES and (n_flag or n_sealed):
        return None, []
    docket = info.get("COURT_NO")
    docs = [
        {
            "RE_NO": e.get("RE_NO"),
            "DOC_DT": (e.get("DOC_DT") or "")[:10] or None,
            # the structured copy flag is more reliable than text rules
            "RECORDED_ENTRY": ("Copy of " if str(e.get("IS_COPY", "N")).upper() == "Y" else "")
            + (e.get("RECORDED_ENTRY") or ""),
        }
        for e in entries
    ]
    ents = s4.classify_docket_entries(docs, docket)
    track = next(
        (e.get("ENGLISH_TRACK_NAME") for e in entries if e.get("ENGLISH_TRACK_NAME")), None
    )
    prefix, num, yy = (docket.split("-") + [None, None])[:3] if docket else (None, None, None)
    lower_no, lower_dt = appeal_from(entries) if prefix == "A" else (None, None)
    row = {k_out: info.get(k_in) for k_in, k_out in INFO_FIELDS.items()}
    row.update(
        {
            "prefix": prefix,
            "number": int(num) if num and num.isdigit() else None,
            "docket_year": 2000 + int(yy) if yy and yy.isdigit() else None,
            "date_filed": ms_date(info.get("FILE_DT")),
            "track": track,
            "scraped": fetched_at[:10],
            # a tribunal decision or certificate registered for enforcement: not a proceeding
            # the court decides, and most never get a closing entry
            "is_registration": bool(
                re.search(REGISTRATION_RE, info.get("ENGLISH_NATURE_DESC") or "", re.I)
            ),
            "appeal_from_file": lower_no,
            "appeal_from_decision_date": s4.parse_entry_date(lower_dt) if lower_dt else None,
            "n_confidential_flag_entries": n_flag,
            "n_sealed_text_entries": n_sealed,
            "n_publication_ban_entries": n_ban,
            "_copies": copies_of_decisions(texts, docket),
            **s4.derive_docket(ents, judgment_fallback=False),
        }
    )
    return row, [{k: v for k, v in e.items() if k != "_fixed"} for e in ents]


def _cached_pairs():
    """Yield ((division, docket), info record, entry records, fetched_at) from the cache."""
    from urllib.parse import parse_qs, urlsplit

    raw = paths.raw_dir(SOURCE)
    info, ents = {}, {}
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if not 200 <= meta["status"] < 300:
            continue
        q = parse_qs(urlsplit(meta["url"]).query)
        key = (q.get("division", [""])[0], q.get("courtnumber", [""])[0])
        target = info if "proceedingQueriesAddInfo" in meta["url"] else ents
        target[key] = (raw / meta["file"], meta["fetched_at"])
    for key, (path, fetched_at) in info.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("data"):
            continue
        if key not in ents:
            continue
        ep = json.loads(ents[key][0].read_text(encoding="utf-8"))
        yield key, payload["data"][0], ep.get("data") or [], fetched_at


def parse(client: Client | None = None):
    import polars as pl

    dockets, entries, dropped, dropped_nos = [], [], 0, []
    # files of the pre-2022 list sample go to their own table: they are not part of the census
    # or of the filing-year samples, and no other table should count them
    listed, older = {}, []
    if pre2022_plan_path().exists():
        for g, grp in json.loads(pre2022_plan_path().read_text())["groups"].items():
            listed.update({no: (g, grp["frame_n"]) for no in grp["order"]})
    for key, info, ents, fetched_at in _cached_pairs():
        row, erows = parse_file(info, ents, fetched_at)
        if row is not None and key[0].lower() == "t" and row["docket"] in listed:
            g, frame_n = listed[row["docket"]]
            older.append({**row, "frame_group": g, "frame_n": frame_n})
            continue
        if row is None:
            dropped += 1
            # file number only: lets the decision link tell "dropped by us" from "never found"
            dropped_nos.append({"docket": info.get("COURT_NO") or key[1]})
            continue
        dockets.append(row)
        entries.extend(erows)
    out = paths.processed_dir() / "s10"
    out.mkdir(exist_ok=True)
    n_lead = add_lead_file_endings(dockets)
    log.info("S10: %d open files carry a copy of a lead file's closing decision", n_lead)
    for r in older:
        r.pop("_copies", None)
    d = pl.DataFrame(
        dockets,
        infer_schema_length=None,
        schema_overrides={"lead_order_end_date": pl.Date, "lead_order_file": pl.String},
    )
    e = pl.DataFrame(entries, infer_schema_length=None)
    if d.height:
        d.write_parquet(out / "dockets.parquet")
        e.write_parquet(out / "entries.parquet")
        pl.DataFrame(dropped_nos, schema={"docket": pl.String}).write_parquet(
            out / "dropped_confidential.parquet"
        )
    if older:
        pl.DataFrame(older, infer_schema_length=None).write_parquet(out / "imm_pre2022.parquet")
    log.info("S10: %d dockets parsed, %d dropped as confidential/sealed", d.height, dropped)
    log.info("S10: %d files of the pre-2022 immigration list sample", len(older))
    return {"dockets": d, "entries": e, "dropped": dropped}


def validate(frames) -> None:
    import polars as pl

    d = frames["dockets"]
    if d.height == 0:
        raise ValueError("S10: no dockets parsed")
    by = (
        d.group_by(["prefix", "docket_year"])
        .agg(
            pl.len().alias("n"),
            pl.col("final_disposition_date").is_not_null().mean().alias("disposed_share"),
            (pl.col("date_filed").dt.year() != pl.col("docket_year"))
            .mean()
            .alias("filed_other_year"),
        )
        .sort(["prefix", "docket_year"])
    )
    log.info("S10 by stratum:\n%s", by)
    bad = d.filter(pl.col("date_filed").is_null()).height
    if bad > 0.01 * d.height:
        raise ValueError(f"S10: {bad} dockets without a filing date")
