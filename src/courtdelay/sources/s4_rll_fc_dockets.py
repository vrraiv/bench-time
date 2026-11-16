"""S4: Refugee Law Lab "Luck of the Draw III" — Federal Court immigration dockets 1997–2022.

Verified 2026-11-15 (docs/sources.md S4): Hugging Face dataset
``refugee-law-lab/luck-of-the-draw-iii`` (CC BY-NC 4.0; public), one ``train.parquet`` (195 MB).
Fields: citation (docket number IMM-#-YY), year (filing year), name (style of cause — dropped at
parse), date_filed, city_filed, nature, class, track, documents (list of {RE_NO, DOCNO, DOC_DT,
RECORDED_ENTRY}), source_url, scraped_timestamp (November 2022).

Outputs (data/processed/s4/):
  dockets.parquet   one row per docket with filing info, counts, and stage dates derived from the
                    recorded entries: leave decision (+ result), hearing, judgment, discontinuance,
                    final disposition (date + type), censoring date (scrape date)
  entries.parquet   one row per recorded entry: docket, RE_NO, entry_date, entry_type (classified);
                    **the entry text and the style of cause are not kept**
  parse_log.parquet counts: dockets, entries, classified share, sealed dropped

Dockets whose entries mention sealing, confidentiality or a publication ban are dropped
(docs/HANDOFF.md section 6) and counted.

Bias statement: immigration (IMM) files only; snapshot as of November 2022 so files still open then
are right-censored; entry classification is regex-based and imperfect (unclassified share reported);
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

# ordered: first matching type wins
ENTRY_TYPES: list[tuple[str, re.Pattern]] = [
    ("discontinuance", re.compile(r"notice\s+of\s+discontinuance|d[ée]sistement", re.I)),
    (
        "leave_decision",
        re.compile(
            r"(?:application\s+for\s+leave|demande\s+d['’]autorisation).{0,200}?result\s*:|"
            r"leave\s+(?:to\s+commence\s+)?(?:is|was)\s+(?:granted|dismissed|refused|denied)|"
            r"(?:granting|dismissing|refusing)\s+(?:the\s+)?(?:application\s+for\s+)?leave|"
            r"autorisation\s+(?:est\s+)?(?:accord[ée]e|rejet[ée]e|refus[ée]e)",
            re.I | re.S,
        ),
    ),
    (
        "judgment",
        re.compile(
            r"\bjudgment\b(?!\s+and\s+reasons\s+to\s+be)|\bjugement\b|reasons\s+for\s+(?:judgment|order)|"
            r"motifs\s+(?:du\s+jugement|de\s+l['’]ordonnance)",
            re.I,
        ),
    ),
    (
        "hearing",
        re.compile(
            r"hearing\s+(?:held|took\s+place|commenced|continued|concluded)|audience\s+tenue|"
            r"heard\s+(?:at|in)\s+[A-Z]|minutes?\s+of\s+hearing|proc[èe]s-verbal\s+d['’]audience",
            re.I,
        ),
    ),
    (
        "hearing_scheduled",
        re.compile(
            r"hearing\s+(?:is\s+)?(?:fixed|scheduled|set\s+down)|notice\s+of\s+hearing|"
            r"avis\s+d['’]audience|requisition\s+for\s+hearing",
            re.I,
        ),
    ),
    ("order", re.compile(r"\border\b|\bordonnance\b", re.I)),
    ("direction", re.compile(r"\bdirection\b|\bdirective\b", re.I)),
    ("filing", re.compile(r"\bfiled\b|\bd[ée]pos[ée]e?\b|\breceived\b|\bre[çc]u", re.I)),
    ("correspondence", re.compile(r"\bletter\b|\blettre\b|\bcorrespondence\b|communication", re.I)),
]
RESULT_RE = re.compile(r"result\s*:\s*([A-Za-z][A-Za-z\s\-]{2,40}?)(?:[\.\n;]|$)", re.I)
GRANT_RE = re.compile(r"\b(granted|allowed|accord[ée]e|accueilli)", re.I)
DISMISS_RE = re.compile(r"\b(dismissed|refused|denied|rejet[ée]e|refus[ée]e)", re.I)


def classify_entry(text: str | None) -> str:
    if not text:
        return "other"
    for name, rx in ENTRY_TYPES:
        if rx.search(text):
            return name
    return "other"


def leave_result(text: str | None) -> str | None:
    if not text:
        return None
    m = RESULT_RE.search(text)
    seg = m.group(1) if m else text[-200:]
    if GRANT_RE.search(seg):
        return "granted"
    if DISMISS_RE.search(seg):
        return "dismissed"
    return None


def parse_entry_date(s) -> date | None:
    if s is None:
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    t = str(s).strip()
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


def derive_docket(docket: str, entries: list[dict]) -> dict:
    """Stage dates from a docket's classified entries (sorted by date, then RE_NO)."""
    ents = sorted(
        entries,
        key=lambda e: (e["entry_date"] or date.min, e["re_no"] if e["re_no"] is not None else 0),
    )
    out = {
        "leave_decision_date": None,
        "leave_result": None,
        "first_hearing_scheduled_date": None,
        "hearing_date": None,
        "judgment_date": None,
        "discontinuance_date": None,
        "final_disposition_date": None,
        "final_disposition_type": None,
        "first_entry_date": ents[0]["entry_date"] if ents else None,
        "last_entry_date": ents[-1]["entry_date"] if ents else None,
        "n_entries": len(ents),
    }
    for e in ents:
        t, d = e["entry_type"], e["entry_date"]
        if t == "leave_decision" and out["leave_decision_date"] is None:
            out["leave_decision_date"], out["leave_result"] = d, e.get("leave_result")
        elif t == "hearing_scheduled" and out["first_hearing_scheduled_date"] is None:
            out["first_hearing_scheduled_date"] = d
        elif t == "hearing" and out["hearing_date"] is None:
            out["hearing_date"] = d
        elif t == "judgment" and (out["judgment_date"] is None or d and d > out["judgment_date"]):
            out["judgment_date"] = d
        elif t == "discontinuance" and out["discontinuance_date"] is None:
            out["discontinuance_date"] = d
    # final disposition: earliest of discontinuance, leave dismissed, judgment
    cands = []
    if out["discontinuance_date"]:
        cands.append((out["discontinuance_date"], "discontinued"))
    if out["leave_decision_date"] and out["leave_result"] == "dismissed":
        cands.append((out["leave_decision_date"], "leave_dismissed"))
    if out["judgment_date"]:
        cands.append((out["judgment_date"], "judgment"))
    if cands:
        out["final_disposition_date"], out["final_disposition_type"] = min(cands)
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
    unclassified = 0
    n_entries = 0
    for row in df.iter_rows(named=True):
        docs = row.get("documents") or []
        texts = [d.get("RECORDED_ENTRY") or "" for d in docs]
        if any(SEALED_RE.search(t) for t in texts):
            sealed += 1
            continue
        ents = []
        for d, t in zip(docs, texts, strict=True):
            et = classify_entry(t)
            n_entries += 1
            unclassified += et == "other"
            e = {
                "docket": row["citation"],
                "re_no": _int(d.get("RE_NO")),
                "entry_date": parse_entry_date(d.get("DOC_DT")),
                "entry_type": et,
                "leave_result": leave_result(t) if et == "leave_decision" else None,
            }
            ents.append(e)
            entry_rows.append({k: v for k, v in e.items() if k != "leave_result"})
        derived = derive_docket(row["citation"], ents)
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
                **derived,
            }
        )
    dockets = pl.DataFrame(docket_rows, infer_schema_length=None)
    entries = pl.DataFrame(entry_rows, infer_schema_length=None)
    out = paths.processed_dir() / "s4"
    out.mkdir(exist_ok=True)
    dockets = dockets.with_columns(
        pl.lit(meta["sha256"]).alias("raw_sha256"), pl.lit(meta["fetched_at"]).alias("fetched_at")
    )
    dockets.write_parquet(out / "dockets.parquet")
    entries.write_parquet(out / "entries.parquet")
    logdf = pl.DataFrame(
        {
            "dockets_in": [df.height],
            "dockets_kept": [dockets.height],
            "sealed_dropped": [sealed],
            "entries": [n_entries],
            "unclassified_share": [unclassified / max(n_entries, 1)],
        }
    )
    logdf.write_parquet(out / "parse_log.parquet")
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
    res = lr["leave_result"].value_counts().sort("leave_result") if lr.height else None
    log.info(
        "S4: %d dockets, %.0f%% with leave decision (%s); %.0f%% judgment, %.0f%% discontinued",
        d.height,
        100 * share_leave,
        res.to_dicts() if res is not None else None,
        100 * d["judgment_date"].is_not_null().mean(),
        100 * d["discontinuance_date"].is_not_null().mean(),
    )
    if share_leave < 0.5:
        problems.append(f"only {share_leave:.0%} of dockets have a leave decision (expected most)")
    by_year = (
        d.group_by("filing_year")
        .agg(
            pl.len().alias("n"),
            pl.col("leave_decision_date").is_not_null().mean().alias("leave_rate"),
            (pl.col("leave_decision_date") - pl.col("date_filed"))
            .dt.total_days()
            .median()
            .alias("filed_to_leave_med_days"),
        )
        .sort("filing_year")
    )
    log.info("S4 by filing year:\n%s", by_year)
    if problems:
        raise ValueError("S4 validation failed:\n  " + "\n  ".join(problems))
