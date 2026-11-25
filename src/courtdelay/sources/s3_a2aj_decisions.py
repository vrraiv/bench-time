"""S3: A2AJ Canadian Case Law (Hugging Face parquet) -> derived decision metadata.

Verified 2026-11-15 (docs/sources.md S3): the public API caps results at 50 with no pagination
and forbids systematic scraping, so we use the bulk parquet files, one per court:
``https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main/{COURT}/train.parquet``.
Schema: dataset, citation_en/fr, citation2_en/fr, name_en/fr, document_date_en/fr, url_en/fr,
scraped_timestamp_en/fr, unofficial_text_en/fr, cases_cited_*, cases_citing_*,
citing_cases_count, upstream_license.

Text layout (observed): A2AJ prepends site metadata lines ("Court (s) Database", "Date",
"Neutral citation", "File numbers" / "Case number", "Judges" for SCC) before "Decision Content".
Hearing dates live in different places per court: SCC and ONCA in the header ("Heard:",
"Appeal heard:"), TCC in the header ("Appeal heard on …"), FCA in the header ("Heard at … on …")
or, for motions, "Dealt with in writing without appearance of parties", and **FC at the very end**
in the solicitors-of-record block ("DATE OF HEARING: …"). So we scan both the first
``HEAD_CHARS`` and the last ``TAIL_CHARS`` characters.

We never write decision text or party names to processed outputs. Kept per row: citation,
decision date, URL, upstream licence, text length, and parsed fields: hearing date(s),
hearing mode (oral / written / unknown), docket/file number(s), judges line (public officials,
header lines only), TCC procedure (informal/general from the file-number suffix), ONCA
lower-court decision date. Parse rates per court-year are written to
data/processed/s3/parse_rates.parquet; misses are kept as rows with nulls, never dropped.

Licence: A2AJ's own work MIT; each row's ``upstream_license`` (court terms) governs reuse.
Treat as non-commercial, attribution, not-to-be-indexed until tabulated.

Bias statement: published written decisions only; oral rulings and unreported decisions are
absent; the hearing date is parsed from unofficial text and may be missing or wrong.
"""

from __future__ import annotations

import logging
import re
from datetime import date

import polars as pl

from courtdelay.common import paths
from courtdelay.common.http import Client

log = logging.getLogger(__name__)

SOURCE = "s3_a2aj_decisions"
HF = "https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main/{court}/train.parquet"
COURTS = ["SCC", "FCA", "FC", "TCC", "ONCA"]
HEAD_CHARS = 4000
TAIL_CHARS = 3000
# the closing "solicitors / counsel of record" page; Tax Court decisions put footnotes after it
PAGE_CHARS = 9000

_MONTHS_EN = "january|february|march|april|may|june|july|august|september|october|november|december"
_MONTHS_FR = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|"
    "novembre|décembre|decembre"
)
_FR_LIST = "janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre"
MONTH_NUM = {
    **{m: i + 1 for i, m in enumerate(_MONTHS_EN.split("|"))},
    **{m: i + 1 for i, m in enumerate(_FR_LIST.split("|"))},
    "fevrier": 2,
    "aout": 8,
    "decembre": 12,
}
# "January 15, 2020" / "January 15 and 16, 2020" / "15 janvier 2020" / "les 7 et 8 décembre 2021"
# / "2020-01-15"
_ORD = r"(?:st|nd|rd|th)?"
DATE_EN = (
    rf"(?:{_MONTHS_EN})\s+\d{{1,2}}{_ORD}(?:\s*(?:,|and|&|-|–|to)\s*\d{{1,2}}{_ORD})*,?\s+\d{{4}}"
)
DATE_FR = (
    rf"(?:les?\s+)?\d{{1,2}}(?:er)?(?:\s*(?:,|et|-|–|au)\s*\d{{1,2}}(?:er)?)*"
    rf"\s+(?:{_MONTHS_FR})\s+\d{{4}}"
)
DATE_ISO = r"\d{4}-\d{2}-\d{2}"
DATE_ANY = rf"({DATE_EN}|{DATE_FR}|{DATE_ISO})"
DATE_ANY_RE = re.compile(DATE_ANY, re.I)

# Hearing-date detection is keyword + window: find a hearing keyword, then take the first date
# within the next HEARING_WINDOW characters (at most two lines).
HEARING_KEYWORD_RE = re.compile(
    r"(?:appeal\s+heard|appeals?\s+heard|reference\s+of\s+a\s+matter\s+heard|motion\s+heard|"
    r"heard|hearing\s+date|date\s+of\s+hearing|place\s+and\s+date\s+of\s+hearing|hearing|"
    r"audience|entendu(?:e|s|es)?|date\s+de\s+l['’]audience)\s*:?",
    re.I,
)
HEARING_WINDOW = 160
WRITTEN_RE = re.compile(
    r"dealt\s+with\s+in\s+writing|without\s+(?:the\s+)?(?:personal\s+)?appearance\s+of\s+(?:the\s+)?parties|"
    r"in\s+writing\s+without\s+appearance|decided\s+on\s+the\s+basis\s+of\s+(?:the\s+)?written|"
    r"jug[ée]\s+sur\s+dossier|sans\s+comparution\s+des\s+parties|affaire\s+jug[ée]e\s+sur\s+dossier|"
    r"motion\s+in\s+writing|requ[êe]te\s+[ée]crite",
    re.I,
)
JUDGMENT_RE = re.compile(
    rf"(?:judgment\s+(?:delivered|rendered)?(?:\s+at\s+[^,\n:]{{1,60}}?,?)?\s*(?:on)?|date\s+of\s+judgment|"
    rf"jugement\s+(?:rendu)?(?:\s+à\s+[^,\n:]{{1,60}}?,?)?\s*(?:le)?|date\s+du\s+jugement|decision\s+date|date)"
    rf"\s*:?\s*{DATE_ANY}",
    re.I,
)
# A2AJ metadata lines ("File numbers\nIMM-441-20" / "Case number\n36639") and court header lines.
META_FILES_RE = re.compile(
    r"^(?:File numbers?|Case number|Num[ée]ros? de dossier)\s*\n([^\n]{1,120})", re.M | re.I
)
DOCKET_RE = re.compile(
    r"^(?:docket|dockets|file\s+no\.?|file\s+number|court\s+file\s+no\.?|dossier|dossiers|n[o°]\s+du\s+dossier|"
    r"n[o°]\s+de\s+dossier|no\.?\s+du\s+greffe)\s*s?\s*:?\s*([A-Z0-9][A-Z0-9()\-/ ,;&]{2,80})",
    re.I | re.M,
)
FILE_TOKEN_RE = re.compile(
    r"\b(?:IMM|T|A|DES|ITA|GST|ETA|CPP|EI|P|C|M|COA|CR|CV|\d{2}-A)-?\d{1,6}-?\d{0,4}\b|"
    # Tax Court: 2019-123(IT)G, 2019-123(GST)APP, and EI/CPP/OAS files with no procedure letter
    r"\b\d{2,4}-\d{1,5}\([A-Z]{2,4}\)(?:(?:APP|G|I)(?![A-Za-z]))?|\b\d{5}\b|\bCOA-\d{2}-(?:CR|CV|OM)-\d{3,5}\b",
    re.I,
)
TCC_PROC_RE = re.compile(r"\((?:IT|GST|EI|CPP|OAS|EA)\)([GI])", re.I)
# judges: header lines only (anchored at line start), never free text
JUDGES_RE = re.compile(
    # header labels only: "PRESENT:", "Coram:", "Before:", "CORAM:\nNOËL C.J." (colon required,
    # which keeps sentences such as "Before the court were..." out)
    r"^(?:present|coram|before|devant|en\s+présence\s+de)\s*:\s*\n?([^\n]{3,200})|"
    r"^coram\s*\n([^\n]{3,200})|"
    r"^judges\s*\n([^\n]{3,200})",  # SCC metadata block; 'Judges and Taxing Officers' nav excluded
    re.I | re.M,
)
SCC_HEADNOTE_SINGLE_RE = re.compile(
    rf"^(\d{{4}}):\s*((?:{_MONTHS_EN})\s+\d{{1,2}})\s*\.\s*$", re.I | re.M
)
# SCC headnote (pre-2016 texts): "2013: February 14; 2013: October 3." = hearing; judgment
SCC_HEADNOTE_DATES_RE = re.compile(
    rf"(\d{{4}}):\s*((?:{_MONTHS_EN})\s+\d{{1,2}})\s*;\s*(\d{{4}}):\s*((?:{_MONTHS_EN})\s+\d{{1,2}})\s*\.",
    re.I,
)
LOWER_COURT_DATE_RE = re.compile(
    rf"on\s+appeal\s+from.{{0,300}}?dated\s+{DATE_ANY}|"
    rf"en\s+appel.{{0,300}}?(?:daté|datée|en\s+date)\s+du\s+{DATE_ANY}",
    re.I | re.S,
)


def _parse_date(s: str) -> list[date]:
    """Return every date in a matched string (handles 'January 15 and 16, 2020')."""
    s = s.strip().lower().replace("1er", "1")
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    out: list[date] = []
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return [date(int(m[1]), int(m[2]), int(m[3]))]
        except ValueError:
            return []
    year = re.search(r"(\d{4})$", s)
    if not year:
        return []
    y = int(year[1])
    mon = next((k for k in MONTH_NUM if re.search(rf"\b{k}\b", s)), None)
    if mon is None:
        return []
    days = [int(d) for d in re.findall(r"\b(\d{1,2})\b", s[: year.start()])]
    for d in days:
        try:
            out.append(date(y, MONTH_NUM[mon], d))
        except ValueError:
            continue
    return out


def _hearing_dates(text: str) -> list[date]:
    dates: list[date] = []
    for m in HEARING_KEYWORD_RE.finditer(text):
        window = text[m.end() : m.end() + HEARING_WINDOW]
        window = "\n".join(window.split("\n")[:2])  # keyword line and the next one
        dm = DATE_ANY_RE.search(window)
        if dm:
            dates.extend(_parse_date(dm.group(1)))
    return dates


def _file_numbers(head: str, court: str) -> list[str]:
    files: list[str] = []
    m = META_FILES_RE.search(head)
    if m:
        files.extend(t.upper().replace(" ", "") for t in FILE_TOKEN_RE.findall(m.group(1)))
    if not files:
        for m in DOCKET_RE.finditer(head):
            files.extend(t.upper().replace(" ", "") for t in FILE_TOKEN_RE.findall(m.group(1)))
    return list(dict.fromkeys(f for f in files if f))


# -- the closing page ------------------------------------------------------------------------
# Federal Court, Federal Court of Appeal and Tax Court decisions end with a page of labelled
# fields: file number, style of cause, place and date of hearing, the judge and kind of
# decision, the date signed, appearances and counsel. (Pointed out by an outside lawyer,
# 2026-11-25.) Only the fields below are kept; style of cause, appearances and counsel are
# never read into the output.
PAGE_START_RE = re.compile(
    r"^\s*(?:STYLES? OF CAUSE|INTITUL[ÉE]S?(?: DE LA CAUSE)?)\s*:", re.M | re.I
)
PAGE_LABEL_RE = re.compile(r"^\s*([A-ZÀ-Ü][A-Za-zÀ-ÿ0-9 ,./&'’()\-]{2,90}?)\s*:\s*(.*)$")
PLACE_LBL = re.compile(r"^(?:PLACE OF (?:THE )?HEARING|LIEU DE L.AUDIENCE)$", re.I)
HEARING_LBL = re.compile(r"^(?:DATES? OF (?:THE )?HEARING|DATES? DE L.AUDIENCE)$", re.I)
DATED_LBL = re.compile(
    r"^(?:DATED|DATE OF (?:AMENDED |ORAL )?(?:JUDGMENTS?|ORDER|DECISION)(?: AND REASONS"
    r"(?: FOR JUDGMENT)?)?|DATE DU JUGEMENT(?: ET DES MOTIFS)?|DATE DE L.ORDONNANCE"
    r"(?: ET DES MOTIFS)?|DATE DES MOTIFS DU JUGEMENT ET DU JUGEMENT|DATE DE LA DÉCISION)$",
    re.I,
)
REASONS_DATE_LBL = re.compile(
    r"^(?:DATE OF (?:ORAL )?REASONS(?: FOR (?:JUDGMENT|ORDER))?|DATE DES MOTIFS)$", re.I
)
WRITTEN_LBL = re.compile(
    r"^(?:WRITTEN (?:REPRESENTATIONS|SUBMISSIONS)(?: BY)?|OBSERVATIONS ÉCRITES(?: PAR)?)$",
    re.I,
)
# the label that names the judge also says what was given: judgment, order, reasons
DECISION_LBL = re.compile(
    r"(?:JUDGE?MENT|ORDER|REASONS|BENCH|DIRECTION|DECISION|ASSESSMENT|JUGEMENT|ORDONNANCE"
    r"|MOTIFS|BANC|DÉCISION|TAXATION)",
    re.I,
)
REMOTE_VIDEO_RE = re.compile(r"vid[ée]o|visioconf|zoom|teams|virtual|virtuel|webex", re.I)
REMOTE_PHONE_RE = re.compile(r"t[ée]l[ée]conf|t[ée]l[ée]phon", re.I)


def page_fields(text: str | None) -> dict:
    """Fields of the closing page, or all None when there is no page."""
    out = {
        "page_found": False,
        "page_place_kind": None,
        "page_hearing_last_date": None,
        "page_decision_kind": None,
        "page_from_bench": None,
        "page_judges": None,
        "page_dated": None,
        "page_reasons_date": None,
        "page_written": None,
    }
    if not text:
        return out
    starts = list(PAGE_START_RE.finditer(text))
    if not starts:
        return out
    # the page begins a few labels before the style of cause (docket / citation lines)
    seg = text[max(0, starts[-1].start() - 400) :]
    fields: list[tuple[str, str]] = []
    for line in seg.splitlines():
        line = line.strip()
        if not line:
            continue
        m = PAGE_LABEL_RE.match(line)
        # a label's first word is in capitals ("JUDGMENT and reasons:" occurs)
        first = re.match(r"[^\W\d_]+", m.group(1)) if m else None
        if m and first and len(first.group(0)) >= 2 and first.group(0).isupper():
            fields.append((" ".join(m.group(1).split()).upper(), m.group(2).strip()))
        elif fields and not fields[-1][1]:
            fields[-1] = (fields[-1][0], line)
    if not fields:
        return out
    out["page_found"] = True
    for label, value in fields:
        if PLACE_LBL.match(label) and out["page_place_kind"] is None:
            out["page_place_kind"] = (
                "video"
                if REMOTE_VIDEO_RE.search(value)
                else "telephone"
                if REMOTE_PHONE_RE.search(value)
                else "in person"
                if value
                else None
            )
        elif HEARING_LBL.match(label) and out["page_hearing_last_date"] is None:
            d = _parse_date(value)
            out["page_hearing_last_date"] = max(d) if d else None
        elif REASONS_DATE_LBL.match(label) and out["page_reasons_date"] is None:
            d = _parse_date(value)
            out["page_reasons_date"] = max(d) if d else None
        elif DATED_LBL.match(label) and out["page_dated"] is None:
            d = _parse_date(value)
            out["page_dated"] = max(d) if d else None
        elif WRITTEN_LBL.match(label):
            out["page_written"] = True
        elif DECISION_LBL.search(label) and not label.startswith("DATE"):
            u = label.upper()
            # "DELIVERED FROM THE BENCH BY" usually follows the "REASONS ... BY" label
            bench = bool(re.search(r"BENCH|BANC", u))
            out["page_from_bench"] = bool(out["page_from_bench"]) or bench
            if out["page_decision_kind"] is not None:
                continue
            out["page_decision_kind"] = (
                "costs"
                if re.search(r"ASSESSMENT|TAXATION", u)
                else "judgment"
                if re.search(r"JUDGE?MENT|JUGEMENT", u)
                else "order"
                if re.search(r"ORDER|ORDONNANCE", u)
                else "direction"
                if re.search(r"DIRECTION", u)
                else "reasons"
            )
            # the judge, as a linking key only (never published; CLAUDE.md)
            out["page_judges"] = value[:200] or None
    if out["page_place_kind"] is None and out["page_written"]:
        out["page_place_kind"] = "written"
    return out


def parse_header(text: str | None, court: str, tail: str | None = None) -> dict:
    """Parse derived fields from the start (and optional end) of a decision text."""
    res = {
        "hearing_date": None,
        "hearing_dates_n": 0,
        "hearing_last_date": None,
        "hearing_mode": None,
        "judgment_date_text": None,
        "file_numbers": None,
        "tcc_procedure": None,
        "judges_line": None,
        "lower_court_date": None,
    }
    if not text:
        return res
    head = text[:HEAD_CHARS]
    tail = tail if tail is not None else text[-TAIL_CHARS:]
    dates = sorted(set(_hearing_dates(head) + _hearing_dates(tail)))
    if not dates and court == "SCC":
        # older S.C.R.-style headnote: "2013: February 14; 2013: October 3." (heard; judgment)
        hm = SCC_HEADNOTE_DATES_RE.search(text[: HEAD_CHARS * 2])
        if hm:
            dates = _parse_date(f"{hm.group(2)}, {hm.group(1)}")
        else:
            # judgment from the bench: a single "2006: June 23." line after "File No."
            sm = SCC_HEADNOTE_SINGLE_RE.search(text[: HEAD_CHARS * 2])
            if sm:
                dates = _parse_date(f"{sm.group(2)}, {sm.group(1)}")
    if dates:
        res["hearing_date"], res["hearing_last_date"] = dates[0], dates[-1]
        res["hearing_dates_n"] = len(dates)
        res["hearing_mode"] = "oral"
    if WRITTEN_RE.search(head) or WRITTEN_RE.search(tail):
        res["hearing_mode"] = "written" if not dates else "oral+written"
    m = JUDGMENT_RE.search(head)
    if m:
        jd = _parse_date(m.group(1))
        res["judgment_date_text"] = jd[0] if jd else None
    files = _file_numbers(head, court)
    res["file_numbers"] = ";".join(files) if files else None
    if court == "TCC":
        pm = TCC_PROC_RE.search(";".join(files) if files else head[:800])
        if pm:
            res["tcc_procedure"] = "general" if pm.group(1).upper() == "G" else "informal"
    jm = JUDGES_RE.search(head)
    if jm:
        line = re.sub(r"\s+", " ", next((g for g in jm.groups() if g), "")).strip()
        # keep only judge-like content: stop at party markers
        line = re.split(r"\b(?:between|entre)\b", line, flags=re.I)[0].strip(" :;,")
        res["judges_line"] = line[:200] if line else None
    if court == "ONCA":
        lm = LOWER_COURT_DATE_RE.search(head)
        if lm:
            ld = _parse_date(lm.group(1) or lm.group(2) or "")
            res["lower_court_date"] = ld[0] if ld else None
    return res


# -- fetch / parse / validate -----------------------------------------------------------------


def fetch(client: Client, courts: list[str] | None = None) -> dict[str, str]:
    out = {}
    for court in courts or COURTS:
        r = client.download(HF.format(court=court), source=SOURCE)
        log.info("S3 %s: %s (%s)", court, r.path, "cached" if r.from_cache else "downloaded")
        out[court] = str(r.path)
    return out


def _parquet_for(court: str):
    import json

    raw = paths.raw_dir(SOURCE)
    for mf in raw.glob("*.meta.json"):
        meta = json.loads(mf.read_text())
        if meta["url"].endswith(f"/{court}/train.parquet") and 200 <= meta["status"] < 300:
            return raw / meta["file"], meta
    return None, None


PARSED_SCHEMA = {
    "hearing_date": pl.Date,
    "hearing_dates_n": pl.Int32,
    "hearing_last_date": pl.Date,
    "hearing_mode": pl.Utf8,
    "judgment_date_text": pl.Date,
    "file_numbers": pl.Utf8,
    "tcc_procedure": pl.Utf8,
    "judges_line": pl.Utf8,
    "lower_court_date": pl.Date,
}
PAGE_SCHEMA = {
    "page_found": pl.Boolean,
    "page_place_kind": pl.Utf8,
    "page_hearing_last_date": pl.Date,
    "page_decision_kind": pl.Utf8,
    "page_from_bench": pl.Boolean,
    "page_judges": pl.Utf8,
    "page_dated": pl.Date,
    "page_reasons_date": pl.Date,
    "page_written": pl.Boolean,
}


def parse_court(court: str, path, meta: dict) -> pl.DataFrame:
    lf = pl.scan_parquet(path)
    cols = lf.collect_schema().names()
    want = [
        c
        for c in (
            "dataset",
            "citation_en",
            "citation_fr",
            "document_date_en",
            "document_date_fr",
            "url_en",
            "url_fr",
            "upstream_license",
            "citing_cases_count",
        )
        if c in cols
    ]
    df = lf.select(
        *want,
        pl.col("unofficial_text_en").str.len_chars().alias("text_len_en"),
        pl.col("unofficial_text_fr").str.len_chars().alias("text_len_fr"),
        pl.col("unofficial_text_en").str.slice(0, HEAD_CHARS).alias("_head_en"),
        pl.col("unofficial_text_en").str.slice(-TAIL_CHARS).alias("_tail_en"),
        pl.col("unofficial_text_fr").str.slice(0, HEAD_CHARS).alias("_head_fr"),
        pl.col("unofficial_text_fr").str.slice(-TAIL_CHARS).alias("_tail_fr"),
        pl.col("unofficial_text_en").str.slice(-PAGE_CHARS).alias("_page_en"),
        pl.col("unofficial_text_fr").str.slice(-PAGE_CHARS).alias("_page_fr"),
    ).collect()
    parsed, pages = [], []
    for page_en, page_fr in zip(df["_page_en"], df["_page_fr"], strict=True):
        pg = page_fields(page_en)
        if not pg["page_found"]:
            pg = page_fields(page_fr)
        pages.append(pg)
    for head_en, tail_en, head_fr, tail_fr in zip(
        df["_head_en"], df["_tail_en"], df["_head_fr"], df["_tail_fr"], strict=True
    ):
        p = parse_header(head_en, court, tail_en) if head_en else parse_header(None, court)
        if (p["hearing_date"] is None or p["file_numbers"] is None) and head_fr:
            pf = parse_header(head_fr, court, tail_fr)
            for k, v in pf.items():
                if p.get(k) in (None, 0) and v not in (None, 0):
                    p[k] = v
        parsed.append(p)
    pdf = pl.DataFrame(parsed, schema=PARSED_SCHEMA).hstack(pl.DataFrame(pages, schema=PAGE_SCHEMA))
    date_cols = [c for c in ("document_date_en", "document_date_fr") if c in cols]
    out = (
        df.drop(["_head_en", "_tail_en", "_head_fr", "_tail_fr", "_page_en", "_page_fr"])
        .hstack(pdf)
        .with_columns(
            pl.coalesce([pl.col(c).cast(pl.Date) for c in date_cols]).alias("decision_date"),
            pl.lit(court).alias("court"),
            pl.lit(meta["sha256"]).alias("raw_sha256"),
            pl.lit(meta["fetched_at"]).alias("fetched_at"),
        )
        .with_columns(
            (pl.col("decision_date") - pl.col("hearing_last_date"))
            .dt.total_days()
            .alias("_reserve_raw")
        )
        .with_columns(
            # a hearing date after the decision date is a parse error (another date in the
            # window); keep the row, null the duration, and flag it
            pl.when(pl.col("_reserve_raw") >= 0)
            .then(pl.col("_reserve_raw"))
            .otherwise(None)
            .alias("reserve_days"),
            (pl.col("_reserve_raw") < 0).fill_null(False).alias("hearing_after_decision"),
        )
        .drop("_reserve_raw")
    )
    # drop tz-aware datetimes (tzdata not guaranteed on Windows; dates are what we keep)
    return out.drop(date_cols)


def parse(client: Client | None = None, courts: list[str] | None = None) -> pl.DataFrame:
    frames = []
    for court in courts or COURTS:
        path, meta = _parquet_for(court)
        if path is None:
            log.warning("S3 %s: parquet not cached; skipping", court)
            continue
        df = parse_court(court, path, meta)
        log.info(
            "S3 %s: %d decisions, hearing date parsed for %.1f%%, written %.1f%%",
            court,
            df.height,
            100 * df["hearing_date"].is_not_null().mean(),
            100 * (df["hearing_mode"] == "written").mean(),
        )
        frames.append(df)
    if not frames:
        raise FileNotFoundError("S3: no cached parquet; run fetch first")
    all_df = pl.concat(frames, how="diagonal_relaxed")
    out = paths.processed_dir() / "s3"
    out.mkdir(exist_ok=True)
    all_df.write_parquet(out / "decisions_meta.parquet")
    rates = (
        all_df.with_columns(pl.col("decision_date").dt.year().alias("year"))
        .group_by(["court", "year"])
        .agg(
            pl.len().alias("n"),
            pl.col("hearing_date").is_not_null().mean().alias("hearing_rate"),
            (pl.col("hearing_mode") == "written").mean().alias("written_share"),
            pl.col("file_numbers").is_not_null().mean().alias("file_rate"),
            pl.col("judges_line").is_not_null().mean().alias("judges_rate"),
            pl.col("page_found").mean().alias("page_rate"),
            pl.col("page_place_kind").is_not_null().mean().alias("page_place_rate"),
            pl.col("page_decision_kind").is_not_null().mean().alias("page_kind_rate"),
            pl.col("page_dated").is_not_null().mean().alias("page_dated_rate"),
            (pl.col("page_dated") == pl.col("decision_date")).mean().alias("page_dated_agrees"),
            (pl.col("page_place_kind") == "video").mean().alias("video_share"),
            pl.col("reserve_days").median().alias("reserve_days_median"),
            pl.col("reserve_days").quantile(0.9).alias("reserve_days_p90"),
        )
        .sort(["court", "year"])
    )
    rates.write_parquet(out / "parse_rates.parquet")
    lic = (
        all_df.group_by(["court", "upstream_license"])
        .len()
        .sort(["court", "len"], descending=[False, True])
    )
    lic.write_parquet(out / "upstream_licences.parquet")
    return all_df


def validate(df: pl.DataFrame) -> None:
    problems = []
    for court in sorted(set(df["court"])):
        d = df.filter(pl.col("court") == court)
        recent = d.filter(pl.col("decision_date").dt.year() >= 2015)
        oral = recent.filter(pl.col("hearing_mode").fill_null("unknown") != "written")
        rate = oral["hearing_date"].is_not_null().mean() if oral.height else 0.0
        neg = recent.filter(pl.col("hearing_after_decision")).height
        huge = recent.filter(pl.col("reserve_days") > 1500).height
        log.info(
            "S3 %s: n=%d (since 2015: %d), hearing rate among non-written %.1f%%, "
            "written %d, reserve<0: %d, >1500d: %d",
            court,
            d.height,
            recent.height,
            100 * rate,
            recent.height - oral.height,
            neg,
            huge,
        )
        if oral.height and rate < 0.3:
            problems.append(f"{court}: hearing-date parse rate {rate:.1%} since 2015 (< 30%)")
        if recent.height and neg > 0.05 * recent.height:
            problems.append(f"{court}: {neg} negative reserve times (hearing after decision)")
        leak = d.filter(
            pl.col("judges_line").str.contains(
                r"(?i)\b(applicant|respondent|appellant|plaintiff)\b"
            )
        ).height
        if leak:
            problems.append(f"{court}: {leak} judges_line values look like party text")
    if problems:
        raise ValueError("S3 validation failed:\n  " + "\n  ".join(problems))
