"""S3: A2AJ Canadian Case Law (Hugging Face parquet) -> derived decision metadata.

Verified 2026-11-15 (docs/sources.md S3): the public API caps results at 50 with no pagination
and forbids systematic scraping, so we use the bulk parquet files, one per court:
``https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main/{COURT}/train.parquet``.
Schema: dataset, citation_en/fr, citation2_en/fr, name_en/fr, document_date_en/fr, url_en/fr,
scraped_timestamp_en/fr, unofficial_text_en/fr, cases_cited_*, cases_citing_*,
citing_cases_count, upstream_license.

We never write decision text or party names to processed outputs. From each row we keep the
citation, decision date, URL, upstream licence, text length, and fields parsed from the first
``HEADER_CHARS`` characters of the text: hearing date(s), judgment date, docket/file number(s),
judges (public officials; kept), proceeding hints, and for TCC the procedure (informal/general)
from the file-number suffix. Parse rates per court-year are reported by ``validate`` and written
to data/processed/s3/parse_rates.parquet; misses are kept as rows with nulls, never dropped.

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
HEADER_CHARS = 4000

_MONTHS_EN = "january|february|march|april|may|june|july|august|september|october|november|december"
_MONTHS_FR = (
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|"
    "novembre|décembre|decembre"
)
MONTH_NUM = {
    **{m: i + 1 for i, m in enumerate(_MONTHS_EN.split("|"))},
    **{
        m: i + 1
        for i, m in enumerate(
            "janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre".split(
                "|"
            )
        )
    },
    "fevrier": 2,
    "aout": 8,
    "decembre": 12,
}
# "January 15, 2020" / "January 15 and 16, 2020" / "15 janvier 2020" / "2020-01-15" / "20200115"
DATE_EN = rf"(?:{_MONTHS_EN})\s+\d{{1,2}}(?:\s*(?:,|and|&|-|–|to)\s*\d{{1,2}})*,?\s+\d{{4}}"
DATE_FR = (
    rf"(?:les?\s+)?\d{{1,2}}(?:er)?(?:\s*(?:,|et|-|–|au)\s*\d{{1,2}}(?:er)?)*"
    rf"\s+(?:{_MONTHS_FR})\s+\d{{4}}"
)
DATE_ISO = r"\d{4}-\d{2}-\d{2}"
DATE_ANY = rf"({DATE_EN}|{DATE_FR}|{DATE_ISO})"
DATE_ANY_RE = re.compile(DATE_ANY, re.I)

# Hearing-date detection is keyword + window: find a hearing keyword, then take the first date
# within the next HEARING_WINDOW characters (at most two lines). Covers "Heard at Toronto,
# Ontario, on April 3, 2023", "Heard: November 20, 2023", "Audience tenue à Montréal (Québec),
# les 7 et 8 décembre 2021", "Appeal heard: October 7, 2020".
HEARING_KEYWORD_RE = re.compile(
    r"(?:appeal\s+heard|heard|hearing\s+date|date\s+of\s+hearing|hearing|"
    r"audience|entendu(?:e)?|date\s+de\s+l['’]audience)\s*:?",
    re.I,
)
HEARING_WINDOW = 160
JUDGMENT_RE = re.compile(
    rf"(?:judgment\s+(?:delivered|rendered)?(?:\s+at\s+[^,\n:]{{1,60}}?,?)?\s*(?:on)?|date\s+of\s+judgment|"
    rf"jugement\s+(?:rendu)?(?:\s+à\s+[^,\n:]{{1,60}}?,?)?\s*(?:le)?|date\s+du\s+jugement|decision\s+date|date)"
    rf"\s*:?\s*{DATE_ANY}",
    re.I,
)
DOCKET_RE = re.compile(
    r"(?:docket|dockets|file\s+no\.?|file\s+number|court\s+file\s+no\.?|dossier|dossiers|n[o°]\s+du\s+dossier|"
    r"n[o°]\s+de\s+dossier|no\.?\s+du\s+greffe)\s*s?\s*:?\s*([A-Z0-9][A-Z0-9()\-/ ,;&]{2,80})",
    re.I,
)
FILE_TOKEN_RE = re.compile(
    r"\b(?:IMM|T|A|DES|ITA|GST|ETA|CPP|EI|P|C|M|COA|CR|CV)-?\d{1,6}-?\d{0,4}\b|"
    r"\b\d{4}-\d{1,5}\((?:IT|GST|EI|CPP|OAS|EA)\)[GI]\b|\b\d{5}\b",
    re.I,
)
TCC_PROC_RE = re.compile(r"\((?:IT|GST|EI|CPP|OAS|EA)\)([GI])", re.I)
JUDGES_RE = re.compile(
    r"(?:present|coram|before|devant|en\s+présence\s+de|reasons\s+for\s+judgment\s+by|motifs\s+du\s+jugement\s+(?:par|de))"
    r"\s*:?\s*([^\n]{3,300})",
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


def parse_header(text: str | None, court: str) -> dict:
    """Parse derived fields from the start of a decision text. Returns a dict; missing -> None."""
    res = {
        "hearing_date": None,
        "hearing_dates_n": 0,
        "hearing_last_date": None,
        "judgment_date_text": None,
        "file_numbers": None,
        "tcc_procedure": None,
        "judges_line": None,
        "lower_court_date": None,
    }
    if not text:
        return res
    head = text[:HEADER_CHARS]
    dates: list[date] = []
    for m in HEARING_KEYWORD_RE.finditer(head):
        window = head[m.end() : m.end() + HEARING_WINDOW]
        # stay within the keyword's line and the next one
        parts = window.split("\n")
        window = "\n".join(parts[:2])
        dm = DATE_ANY_RE.search(window)
        if dm:
            dates.extend(_parse_date(dm.group(1)))
    dates = sorted(set(dates))
    if dates:
        res["hearing_date"] = dates[0]
        res["hearing_last_date"] = dates[-1]
        res["hearing_dates_n"] = len(dates)
    m = JUDGMENT_RE.search(head)
    if m:
        jd = _parse_date(m.group(1))
        res["judgment_date_text"] = jd[0] if jd else None
    files: list[str] = []
    for m in DOCKET_RE.finditer(head):
        files.extend(t.upper().replace(" ", "") for t in FILE_TOKEN_RE.findall(m.group(1)))
    if not files and court in {"FC", "FCA", "TCC"}:
        files = [t.upper() for t in FILE_TOKEN_RE.findall(head[:600]) if "-" in t or "(" in t]
    files = list(dict.fromkeys(f for f in files if f))
    res["file_numbers"] = ";".join(files) if files else None
    if court == "TCC":
        pm = TCC_PROC_RE.search(";".join(files) if files else head[:800])
        if pm:
            res["tcc_procedure"] = "general" if pm.group(1).upper() == "G" else "informal"
    jm = JUDGES_RE.search(head)
    if jm:
        res["judges_line"] = re.sub(r"\s+", " ", jm.group(1)).strip()[:200]
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
        pl.col("unofficial_text_en").str.slice(0, HEADER_CHARS).alias("_head_en"),
        pl.col("unofficial_text_fr").str.slice(0, HEADER_CHARS).alias("_head_fr"),
    ).collect()
    parsed = []
    for head_en, head_fr in zip(df["_head_en"], df["_head_fr"], strict=True):
        p = parse_header(head_en, court)
        if p["hearing_date"] is None and head_fr:
            pf = parse_header(head_fr, court)
            for k, v in pf.items():
                if p.get(k) in (None, 0) and v not in (None, 0):
                    p[k] = v
        parsed.append(p)
    pdf = pl.DataFrame(
        parsed,
        schema={
            "hearing_date": pl.Date,
            "hearing_dates_n": pl.Int32,
            "hearing_last_date": pl.Date,
            "judgment_date_text": pl.Date,
            "file_numbers": pl.Utf8,
            "tcc_procedure": pl.Utf8,
            "judges_line": pl.Utf8,
            "lower_court_date": pl.Date,
        },
    )
    out = (
        df.drop(["_head_en", "_head_fr"])
        .hstack(pdf)
        .with_columns(
            pl.coalesce(
                [
                    pl.col(c).cast(pl.Date)
                    for c in ("document_date_en", "document_date_fr")
                    if c in cols
                ]
            ).alias("decision_date"),
            pl.lit(court).alias("court"),
            pl.lit(meta["sha256"]).alias("raw_sha256"),
            pl.lit(meta["fetched_at"]).alias("fetched_at"),
        )
        .with_columns(
            (pl.col("decision_date") - pl.col("hearing_last_date"))
            .dt.total_days()
            .alias("reserve_days")
        )
    )
    return out


def parse(client: Client | None = None, courts: list[str] | None = None) -> pl.DataFrame:
    frames = []
    for court in courts or COURTS:
        path, meta = _parquet_for(court)
        if path is None:
            log.warning("S3 %s: parquet not cached; skipping", court)
            continue
        df = parse_court(court, path, meta)
        log.info(
            "S3 %s: %d decisions, hearing date parsed for %.1f%%",
            court,
            df.height,
            100 * df["hearing_date"].is_not_null().mean(),
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
            pl.col("file_numbers").is_not_null().mean().alias("file_rate"),
            pl.col("judges_line").is_not_null().mean().alias("judges_rate"),
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
        rate = recent["hearing_date"].is_not_null().mean() if recent.height else 0.0
        neg = recent.filter(pl.col("reserve_days") < 0).height
        huge = recent.filter(pl.col("reserve_days") > 1500).height
        log.info(
            "S3 %s: n=%d (since 2015: %d), hearing rate %.1f%%, reserve<0: %d, >1500d: %d",
            court,
            d.height,
            recent.height,
            100 * rate,
            neg,
            huge,
        )
        if recent.height and rate < 0.3:
            problems.append(f"{court}: hearing-date parse rate {rate:.1%} since 2015 (< 30%)")
        if recent.height and neg > 0.05 * recent.height:
            problems.append(f"{court}: {neg} negative reserve times (hearing after decision)")
    if problems:
        raise ValueError("S3 validation failed:\n  " + "\n  ".join(problems))
