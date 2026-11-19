"""S4: Refugee Law Lab "Luck of the Draw III" — Federal Court immigration dockets 1997–2022.

Verified 2026-11-15 (docs/sources.md S4): Hugging Face dataset
``refugee-law-lab/luck-of-the-draw-iii`` (CC BY-NC 4.0; public), one ``train.parquet`` (195 MB).
Fields: citation (docket number IMM-#-YY), year (filing year), name (style of cause — dropped at
parse), date_filed, city_filed, nature, class, track, documents (list of {RE_NO, DOCNO, DOC_DT,
RECORDED_ENTRY}), source_url, scraped_timestamp (November 2022).

Recorded-entry formats observed (2015–2022 samples):
  "Order rendered by The Honourable Mr. Justice X at Ottawa on 09-SEP-2019 granting the
   application for leave fixing the hearing at a Special Sitting at Vancouver on 27-NOV-2019 ..."
  "(Final decision) Order rendered by ... dismissing the application for leave Decision endorsed
   on the record ... Considered by the Court without personal appearance ..."
  "Toronto 13-NOV-2019 BEFORE The Honourable Mr. Justice X Language: E Before the Court:
   Judicial Review Result of Hearing: Matter reserved held in Court ..."
  "(Final decision) Reasons for Judgment and Judgment dated 12-MAR-2020 rendered by ... The
   Court's decision is with regard to Judicial Review Result: dismissed Filed on ..."
  "Notice of discontinuance on behalf of the applicant filed on 23-APR-2019"
Entries beginning "Copy of ..." / "Acknowledgment of Receipt ..." are documents placed on file
(often from another docket), not events. "(Final decision)" marks the Registry's final disposition.

Outputs (data/processed/s4/):
  dockets.parquet   one row per docket: filing info, counts, stage dates (leave decision + result,
                    scheduled hearing, hearing, judgment, discontinuance), final disposition
                    (date, type, result), censoring date (scrape date)
  entries.parquet   one row per recorded entry: docket, RE_NO, entry_date, entry_type, result,
                    hearing_subject, is_final — **no entry text, no style of cause**
  parse_log.parquet counts: dockets, entries, classified share, sealed dropped

Dockets whose entries mention sealing, confidentiality or a publication ban are dropped
(docs/HANDOFF.md section 6) and counted.

Bias statement: immigration (IMM) files only; snapshot as of November 2022 so files still open then
are right-censored; entry classification is regex-based (unclassified share reported);
baseline and validation source for the later S10 docket work.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

import polars as pl

from courtdelay.common import paths
from courtdelay.common.http import Client

log = logging.getLogger(__name__)

SOURCE = "s4_rll_fc_dockets"
URL = "https://huggingface.co/datasets/refugee-law-lab/luck-of-the-draw-iii/resolve/main/train.parquet"

SEALED_RE = re.compile(
    r"\bsealed\b|\bconfidential(?:ity)?\s+order\b|publication\s+ban|non-?publication|"
    r"\bsous\s+scell[ée]s?\b|interdiction\s+de\s+publication",
    re.I,
)
COPY_RE = re.compile(
    r"^\s*(?:\((?:final\s+decision|d[ée]cision\s+finale)\)\s*)?"
    r"(?:copy\s+of|copies\s+of|acknowledg?ment\s+of\s+receipt|copie\s+(?:certifi[ée]e\s+)?de|"
    r"accus[ée]\s+de\s+r[ée]ception|carte\s+d['’]accus[ée])",
    re.I,
)
# Owner decision 2026-11-19: files with a sealing or confidentiality mention are kept (they are
# public files with a sealed document, 0.3% of the total) and the mentions are counted per file.
DROP_MARKED_FILES = False

# The Registry marks the entry that ends a file. Older entries carry "(Final decision)" at the
# start; entries from the current system carry "Final Decision" on a line of its own after the
# text (found 2026-11-19: a start-only match saw the marker on no FCA file at all). A mention in
# running prose ("after a final decision in the Rule 51 appeal") is not a marker.
FINAL_RE = re.compile(
    r"^\s*\((?:final\s+decision|d[ée]cision\s+finale)\)"
    r"|^[ \t]*\(?[ \t]*(?:final\s+decision|d[ée]cision\s+finale)[ \t]*\)?[ \t\r]*$",
    re.I | re.M,
)

# ordered: first matching type wins (English and French recorded-entry wording)
ENTRY_TYPES: list[tuple[str, re.Pattern]] = [
    # an entry withdrawn from the public record (not a file event)
    ("removed_entry", re.compile(r"^\W*\*+\s*(?:removed|retir[ée])", re.I)),
    ("cancelled", re.compile(r"^\W*\*+\s*(?:cancelled|annul[ée])", re.I)),
    (
        "discontinuance",
        re.compile(r"\bdiscontinuance\b|d[ée]sistement|avis\s+de\s+d[ée]sistement", re.I),
    ),
    (
        "leave_decision",
        re.compile(
            r"(?:granting|dismissing|refusing|allowing|denying)\s+(?:in\s+part\s+)?(?:the\s+)?"
            r"(?:applications?\s+for\s+)?leave\b|"
            r"(?:rejetant|accueillant|accordant|refusant)\s+(?:en\s+partie\s+)?"
            r"(?:la\s+|les\s+)?demandes?\s+d['’]autorisation|"
            r"(?:application\s+for\s+leave|demande\s+d['’]autorisation)[^|]{0,200}?result\s*:|"
            r"leave\s+(?:to\s+commence\s+)?(?:is|was|be)\s+(?:granted|dismissed|refused|denied)|"
            r"autorisation\s+(?:est\s+)?(?:accord[ée]e|rejet[ée]e|refus[ée]e)",
            re.I | re.S,
        ),
    ),
    # Registry minutes of a hearing. Checked before "judgment" because minutes often say that
    # judgment was reserved or delivered from the bench. French minutes and the appeal court's
    # English wording were not recognised before 2026-11-19 (about 6,300 entries in S10).
    (
        "hearing",
        re.compile(
            r"^\W*this\s+matter\s+c(?:omes|ame)\s+on\s+for\s+hearing\b|"
            r"^\W*l['’]audition\s+de\s+cette\s+affaire\s+a\s+(?:eu\s+)?lieu|"
            r"^.{0,60}?\ben\s+pr[ée]sence\s+de\s.{0,200}?mati[èe]re\s+en\s+litige",
            re.I | re.S,
        ),
    ),
    (
        "judgment",
        re.compile(
            r"\bjudgments?\b(?!\s+and\s+reasons\s+to\s+be)|\bjugement\b|reasons\s+for\s+judgment|"
            r"motifs\s+du\s+jugement|(?:granting|dismissing|allowing)\s+the\s+application\s+for\s+"
            r"judicial\s+review|(?:rejetant|accueillant|accordant)\s+(?:en\s+partie\s+)?la\s+"
            r"demande\s+de\s+contr[ôo]le\s+judiciaire",
            re.I,
        ),
    ),
    (
        "hearing",
        re.compile(
            r"result\s+of\s+hearing|\bbefore\s+the\s+honou?rable\b.{0,120}?before\s+the\s+court|"
            r"r[ée]sultat\s+de\s+l['’]audience|devant\s+la\s+cour\s*:|"
            r"hearing\s+(?:held|took\s+place|commenced|continued|concluded)|audience\s+tenue|"
            r"minutes?\s+of\s+hearing|proc[èe]s-verbal\s+d['’]audience",
            re.I | re.S,
        ),
    ),
    (
        "hearing_scheduled",
        re.compile(
            r"fixing\s+the\s+hearing|fixant\s+l['’]audience|"
            r"scheduling\s+(?:the\s+)?time\s+and\s+place\s+of\s+(?:the\s+)?hearing|"
            r"hearing\s+(?:is\s+)?(?:fixed|scheduled|set\s+down)|"
            r"notice\s+of\s+hearing|avis\s+d['’]audience|requisition\s+for\s+hearing",
            re.I,
        ),
    ),
    ("order", re.compile(r"\border\b|\bordonnance\b", re.I)),
    ("direction", re.compile(r"\bdirection\b|\bdirective\b", re.I)),
    ("filing", re.compile(r"\bfiled\b|\bd[ée]pos[ée]e?\b|\breceived\b|\bre[çc]u", re.I)),
    ("correspondence", re.compile(r"\bletter\b|\blettre\b|\bcorrespondence\b|communication", re.I)),
]
RESULT_RE = re.compile(
    r"result(?:\s+of\s+hearing)?\s*:\s*(?:matter\s+)?([A-Za-z][A-Za-z\s\-]{2,40}?)"
    r"(?=\s+(?:filed|held|decision|style|[A-Z0-9])|[\.\n;]|$)",
    re.I,
)
VERB_RESULT = [
    (re.compile(r"\bin\s+part\b|\ben\s+partie\b", re.I), "granted_in_part"),
    (
        re.compile(
            r"\b(granting|allowing|granted|allowed|accord[ée]e|accueilli|accueillant|accordant)",
            re.I,
        ),
        "granted",
    ),
    (
        re.compile(
            r"\b(dismissing|refusing|denying|dismissed|refused|denied|rejet[ée]e|refus[ée]e|"
            r"rejetant|refusant)",
            re.I,
        ),
        "dismissed",
    ),
    (re.compile(r"\breserved\b|en\s+d[ée]lib[ée]r[ée]", re.I), "reserved"),
    (re.compile(r"\badjourned\b|\bajourn", re.I), "adjourned"),
]
SUBJECT_RE = re.compile(
    r"(?:before\s+the\s+court|mati[èe]re\s+en\s+litige)\s*:\s*"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s/'’()]{2,40}?)"
    r"(?=\s+(?:doc\.|result|r[ée]sultat|on\s+behalf|de\s+la\s+part|language|langue)|$)",
    re.I,
)
# hearing subjects that are not a hearing of the proceeding itself
NON_MERITS_RE = re.compile(
    r"motion|requ[êe]te|conf[ée]rence|m[ée]diation|meeting|r[ée]union|neutral\s+evaluation|"
    r"next\s+steps|show\s+cause|status\s+review|[ée]tat\s+de\s+l['’]instance",
    re.I,
)
FIXED_DATE_RE = re.compile(
    r"(?:fixing\s+the\s+hearing.{0,80}?\bon|fixant\s+l['’]audience.{0,80}?\ble)\s+"
    r"(\d{1,2}-[A-Za-zÉÛéû]{3,4}-\d{4})",
    re.I | re.S,
)
FR_MON = {
    "JANV": "JAN",
    "FÉV": "FEB",
    "FEV": "FEB",
    "MARS": "MAR",
    "AVR": "APR",
    "MAI": "MAY",
    "JUIN": "JUN",
    "JUIL": "JUL",
    "AOÛ": "AUG",
    "AOU": "AUG",
    "SEPT": "SEP",
    "OCT": "OCT",
    "NOV": "NOV",
    "DÉC": "DEC",
    "DEC": "DEC",
}


def classify_entry(text: str | None) -> str:
    if not text:
        return "other"
    if COPY_RE.match(text):
        return "copy_on_file"
    for name, rx in ENTRY_TYPES:
        if rx.search(text):
            return name
    return "other"


def entry_result(text: str | None) -> str | None:
    """Outcome for decision-like entries: granted / granted_in_part / dismissed / reserved /
    adjourned. Uses the 'Result:' field when present, else the operative verb."""
    if not text:
        return None
    m = RESULT_RE.search(text)
    seg = m.group(1) if m else text
    for rx, label in VERB_RESULT:
        if rx.search(seg):
            return label
    return None


def hearing_subject(text: str | None) -> str | None:
    if not text:
        return None
    m = SUBJECT_RE.search(text)
    if not m:
        return None
    s = m.group(1).strip().lower()
    if "judicial review" in s or "contrôle judiciaire" in s or "controle judiciaire" in s:
        return "judicial_review"
    if "motion" in s or "requête" in s or "requete" in s:
        return "motion"
    return s[:40]


def parse_entry_date(s) -> date | None:
    if s is None:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    t = str(s).strip()
    fm = re.fullmatch(r"(\d{1,2})-([A-Za-zÉÛéû]{3,4})-(\d{4})", t)
    if fm and fm.group(2).upper() in FR_MON:
        t = f"{fm.group(1)}-{FR_MON[fm.group(2).upper()]}-{fm.group(3)}"
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%Y/%m/%d", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(t[:20], fmt).date()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    return None


def fetch(client: Client) -> str:
    r = client.download(URL, source=SOURCE)
    log.info("S4: %s (%s)", r.path, "cached" if r.from_cache else "downloaded")
    return str(r.path)


def _parquet():
    import json

    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if meta["url"] == URL and 200 <= meta["status"] < 300:
            return raw / meta["file"], meta
    raise FileNotFoundError("S4: parquet not cached; run fetch first")


def classify_docket_entries(docs: list[dict], docket: str) -> list[dict]:
    """Classify a docket's recorded entries; returns dicts without the entry text."""
    out = []
    for d in docs:
        text = d.get("RECORDED_ENTRY") or ""
        et = classify_entry(text)
        e = {
            "docket": docket,
            "re_no": _int(d.get("RE_NO")),
            "entry_date": parse_entry_date(d.get("DOC_DT")),
            "entry_type": et,
            "result": entry_result(text)
            if et in {"leave_decision", "judgment", "hearing", "order"}
            else None,
            "hearing_subject": hearing_subject(text) if et == "hearing" else None,
            "is_final": et not in {"cancelled", "removed_entry"} and bool(FINAL_RE.search(text)),
            "_fixed": None,
        }
        if et in {"leave_decision", "hearing_scheduled"}:
            fm = FIXED_DATE_RE.search(text)
            if fm:
                e["_fixed"] = parse_entry_date(fm.group(1))
        out.append(e)
    return out


def derive_docket(entries: list[dict], *, judgment_fallback: bool = True) -> dict:
    """Stage dates from a docket's classified entries (sorted by date, then RE_NO).

    The end of a file is the Registry's final-decision marker. Without one, the fallback is the
    earliest of a discontinuance, a dismissed leave application and, when ``judgment_fallback``
    is set, the first judgment-typed entry. S10 turns that last one off: the judgment pattern
    matches any entry that mentions a judgment, and it was closing pending files."""
    ents = sorted(
        entries,
        key=lambda e: (e["entry_date"] or date.min, e["re_no"] if e["re_no"] is not None else 0),
    )
    out = {
        "leave_decision_date": None,
        "leave_result": None,
        "scheduled_hearing_date": None,
        "hearing_date": None,
        "hearing_result": None,
        "judgment_date": None,
        "judgment_result": None,
        "discontinuance_date": None,
        "final_disposition_date": None,
        "final_disposition_type": None,
        "final_disposition_result": None,
        "final_disposition_source": None,  # "marker" (Registry marker) or "fallback"
        "first_entry_date": ents[0]["entry_date"] if ents else None,
        "last_entry_date": ents[-1]["entry_date"] if ents else None,
        "n_entries": len(ents),
    }
    cancelled = None
    for e in ents:
        t, d = e["entry_type"], e["entry_date"]
        if t == "leave_decision" and out["leave_decision_date"] is None:
            out["leave_decision_date"], out["leave_result"] = d, e.get("result")
            if e.get("_fixed") and out["scheduled_hearing_date"] is None:
                out["scheduled_hearing_date"] = e["_fixed"]
        elif t == "hearing_scheduled" and out["scheduled_hearing_date"] is None:
            out["scheduled_hearing_date"] = e.get("_fixed") or d
        elif (
            t == "hearing"
            and out["hearing_date"] is None
            # motions, case conferences and mediations are not the hearing of the proceeding
            and not NON_MERITS_RE.search(e.get("hearing_subject") or "")
        ):
            out["hearing_date"], out["hearing_result"] = d, e.get("result")
        elif t == "judgment" and out["judgment_date"] is None:
            out["judgment_date"], out["judgment_result"] = d, e.get("result")
        elif t == "discontinuance" and out["discontinuance_date"] is None:
            out["discontinuance_date"] = d
        elif t == "cancelled" and cancelled is None:
            cancelled = d
        if e["is_final"] and out["final_disposition_date"] is None and d is not None:
            out["final_disposition_date"] = d
            out["final_disposition_type"] = {
                "leave_decision": "leave_decision",
                "judgment": "judgment",
                "discontinuance": "discontinuance",
                "order": "order",
            }.get(t, t)
            out["final_disposition_result"] = e.get("result")
            out["final_disposition_source"] = "marker"
    if out["final_disposition_date"] is None:
        # no Registry marker: earliest of discontinuance, leave dismissed, judgment
        cands = []
        if out["discontinuance_date"]:
            cands.append((out["discontinuance_date"], "discontinuance", None))
        # "****** CANCELLED ******" marks a cancelled document; it ends the file only when no
        # substantive entry follows it
        later = [
            e
            for e in ents
            if cancelled
            and e["entry_date"]
            and e["entry_date"] > cancelled
            and e["entry_type"]
            not in {"copy_on_file", "removed_entry", "correspondence", "other", "cancelled"}
        ]
        if cancelled and not later and not cands:
            cands.append((cancelled, "cancelled", None))
        if out["leave_decision_date"] and out["leave_result"] == "dismissed":
            cands.append((out["leave_decision_date"], "leave_decision", "dismissed"))
        if judgment_fallback and out["judgment_date"]:
            cands.append((out["judgment_date"], "judgment", out["judgment_result"]))
        if cands:
            d, t, r = min(cands, key=lambda c: c[0])
            out["final_disposition_date"], out["final_disposition_type"] = d, t
            out["final_disposition_result"] = r
            out["final_disposition_source"] = "fallback"
    return out


def parse(client: Client | None = None) -> dict[str, pl.DataFrame]:
    path, meta = _parquet()
    lf = pl.scan_parquet(path)
    cols = lf.collect_schema().names()
    keep = [
        c
        for c in (
            "citation",
            "year",
            "date_filed",
            "city_filed",
            "nature",
            "class",
            "track",
            "source_url",
            "scraped_timestamp",
        )
        if c in cols
    ]
    df = lf.select(*keep, "documents").collect()
    log.info("S4: %d dockets in parquet", df.height)
    docket_rows, entry_rows = [], []
    sealed = 0
    marked = 0
    unclassified = 0
    n_entries = 0
    for row in df.iter_rows(named=True):
        docs = row.get("documents") or []
        n_marked = sum(bool(SEALED_RE.search(d.get("RECORDED_ENTRY") or "")) for d in docs)
        if n_marked:
            marked += 1
            if DROP_MARKED_FILES:
                sealed += 1
                continue
        ents = classify_docket_entries(docs, row["citation"])
        n_entries += len(ents)
        unclassified += sum(e["entry_type"] == "other" for e in ents)
        entry_rows.extend({k: v for k, v in e.items() if k != "_fixed"} for e in ents)
        docket_rows.append(
            {
                "docket": row["citation"],
                "filing_year": row.get("year"),
                "date_filed": parse_entry_date(row.get("date_filed")),
                "city_filed": row.get("city_filed"),
                "nature": row.get("nature"),
                "class": row.get("class"),
                "track": row.get("track"),
                "scraped": parse_entry_date(row.get("scraped_timestamp")),
                "source_url": row.get("source_url"),
                "n_sealed_text_entries": n_marked,
                **derive_docket(ents),
            }
        )
    dockets = pl.DataFrame(docket_rows, infer_schema_length=None).with_columns(
        pl.lit(meta["sha256"]).alias("raw_sha256"), pl.lit(meta["fetched_at"]).alias("fetched_at")
    )
    entries = pl.DataFrame(entry_rows, infer_schema_length=None)
    out = paths.processed_dir() / "s4"
    out.mkdir(exist_ok=True)
    dockets.write_parquet(out / "dockets.parquet")
    entries.write_parquet(out / "entries.parquet")
    pl.DataFrame(
        {
            "dockets_in": [df.height],
            "dockets_kept": [dockets.height],
            "sealed_dropped": [sealed],
            "sealed_marked_kept": [marked - sealed],
            "entries": [n_entries],
            "unclassified_share": [unclassified / max(n_entries, 1)],
        }
    ).write_parquet(out / "parse_log.parquet")
    log.info(
        "S4: %d dockets kept (%d sealed dropped), %d entries, %.1f%% unclassified",
        dockets.height,
        sealed,
        n_entries,
        100 * unclassified / max(n_entries, 1),
    )
    return {"dockets": dockets, "entries": entries}


def _int(v):
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def validate(frames: dict[str, pl.DataFrame]) -> None:
    d = frames["dockets"]
    problems = []
    if d.height < 50_000:
        problems.append(f"only {d.height} dockets (expected >100k)")
    yrs = d["filing_year"].drop_nulls()
    if len(yrs) == 0 or yrs.min() > 1998 or yrs.max() < 2021:
        problems.append(
            f"filing years {yrs.min() if len(yrs) else None}..{yrs.max() if len(yrs) else None}"
        )
    for col in ("leave_decision_date", "hearing_date", "judgment_date", "discontinuance_date"):
        bad = d.filter(pl.col(col).is_not_null() & (pl.col(col) < pl.col("date_filed"))).height
        if bad > 0.01 * d.height:
            problems.append(f"{col}: {bad} dockets with stage date before filing")
    lr = d.filter(pl.col("leave_decision_date").is_not_null())
    share_leave = lr.height / max(d.height, 1)
    res = (
        dict(
            zip(
                *lr["leave_result"]
                .fill_null("unknown")
                .value_counts()
                .sort("leave_result")
                .to_dict()
                .values(),
                strict=True,
            )
        )
        if lr.height
        else {}
    )
    log.info(
        "S4: %d dockets; %.0f%% with leave decision %s; %.0f%% hearing; %.0f%% judgment; "
        "%.0f%% discontinued; %.0f%% with a final disposition",
        d.height,
        100 * share_leave,
        res,
        100 * d["hearing_date"].is_not_null().mean(),
        100 * d["judgment_date"].is_not_null().mean(),
        100 * d["discontinuance_date"].is_not_null().mean(),
        100 * d["final_disposition_date"].is_not_null().mean(),
    )
    if share_leave < 0.5:
        problems.append(f"only {share_leave:.0%} of dockets have a leave decision (expected most)")
    unknown = res.get("unknown", 0) / max(lr.height, 1)
    if unknown > 0.2:
        problems.append(f"{unknown:.0%} of leave decisions have no parsed result")
    by_year = (
        d.group_by("filing_year")
        .agg(
            pl.len().alias("n"),
            pl.col("leave_decision_date").is_not_null().mean().alias("leave_rate"),
            (pl.col("leave_result") == "granted").mean().alias("granted_share"),
            (pl.col("leave_decision_date") - pl.col("date_filed"))
            .dt.total_days()
            .median()
            .alias("filed_to_leave_med_days"),
            (pl.col("final_disposition_date") - pl.col("date_filed"))
            .dt.total_days()
            .median()
            .alias("filed_to_final_med_days"),
        )
        .sort("filing_year")
    )
    log.info("S4 by filing year:\n%s", by_year)
    if problems:
        raise ValueError("S4 validation failed:\n  " + "\n  ".join(problems))
