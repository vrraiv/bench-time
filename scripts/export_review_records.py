"""Working copies of the court records named in the current Questions for review list, as PDFs,
for the practitioner to read without using the courts' search pages.

    uv run --no-sync python scripts/export_review_records.py <out folder>

Reads only the raw cache (data/raw/s10_fc_fca_dockets, data/raw/s12_tcc_dockets): no requests
are made. Finds every Federal Court and Tax Court file number in data/review/questions.json
(question text and reference tables) and writes one PDF per file, "FC T-501-18.pdf" or
"TCC 2018-1523(IT).pdf", rendered with headless Microsoft Edge.

The PDFs reproduce the public record as the court's file search showed it, INCLUDING NAMES of
parties, counsel and deponents. They are private working copies for the practitioner (owner
decision 2026-11-23): never put them on the site, in the repository or in data/processed.
Pass the output folder on the command line; do not write it into any file.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

FC_RE = re.compile(r"\b(?:T|A|IMM)-\d{1,5}-\d{2}\b")
TCC_RE = re.compile(r"\b\d{4}-\d{1,5}\([A-Z]{1,4}\)(?:APP|G|I)?(?![A-Za-z])")

FC_SEARCH = "https://www.fct-cf.ca/en/court-files-and-decisions/court-files"
TCC_SEARCH = "https://www.tcc-cci.ca/en/pages/find-a-court-file"


_META: dict[Path, list[dict]] = {}


def _metas(folder: Path) -> list[dict]:
    """Successful cache entries of one source, read once."""
    if folder not in _META:
        out = []
        for mf in folder.glob("*.meta.json"):
            m = json.loads(mf.read_text(encoding="utf-8"))
            if 200 <= m.get("status", 0) < 300:
                out.append(m)
        _META[folder] = out
    return _META[folder]


def _load(folder: Path, m: dict):
    return json.loads((folder / m["file"]).read_text(encoding="utf-8"))


def _date(v) -> str:
    s = str(v or "")
    if m := re.match(r"/Date\((-?\d+)\)/", s):
        return datetime.fromtimestamp(int(m.group(1)) / 1000, UTC).strftime("%Y-%m-%d")
    return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else s


def _e(v) -> str:
    return html.escape("" if v in (None, "None") else str(v).strip())


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
body {{ font: 10.5pt/1.35 "Segoe UI", Arial, sans-serif; margin: 18mm 14mm; color: #111; }}
h1 {{ font-size: 15pt; margin: 0 0 4px; }}
.note {{ font-size: 9pt; color: #444; border: 1px solid #bbb; padding: 6px 8px;
  margin: 8px 0 12px; }}
dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px; margin: 0 0 12px; }}
dt {{ font-weight: 600; color: #333; }} dd {{ margin: 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9.5pt; }}
th, td {{ border: 1px solid #ccc; padding: 3px 5px; vertical-align: top; text-align: left; }}
th {{ background: #eee; }} tr {{ page-break-inside: avoid; }}
.conf {{ font-weight: 600; }}
</style></head><body>{body}</body></html>"""


def _note(court: str, fetched: str, search: str) -> str:
    return (
        f'<div class="note">Copy of the public record shown by the {court} file search '
        f"({_e(search)}), as read by the Docket Watch project on {_e(fetched[:10])}. The live "
        "record may have changed since. Working copy for practitioner review only: it contains "
        "names. Please do not forward or publish.</div>"
    )


def fc_record(number: str):
    folder = RAW / "s10_fc_fca_dockets"
    div = "a" if number.startswith("A-") else "t"
    info = ents = None
    for m in _metas(folder):
        if m["url"].endswith(f"division={div}&courtnumber={number}"):
            if "proceedingQueriesAddInfo" in m["url"]:
                info = (m, _load(folder, m))
            elif "proceedingQueriesRE" in m["url"]:
                ents = (m, _load(folder, m))
    if not info or not ents:
        return None
    i = (info[1].get("data") or [{}])[0]
    rows = sorted(
        ents[1].get("data") or [], key=lambda r: int(float(r.get("RE_NO") or 0)), reverse=True
    )
    court = "Federal Court of Appeal" if div == "a" else "Federal Court"
    parties = i.get("Party")
    if isinstance(parties, list):
        parties = "; ".join(str(p) for p in parties if p)
    head = [
        ("Court file", number),
        ("Court", court),
        ("Style of cause", i.get("STYLE_OF_CAUSE")),
        ("Nature of proceeding", i.get("ENGLISH_NATURE_DESC")),
        ("Class", i.get("ENGLISH_PROCEEDING_CLASS")),
        ("Filing date", _date(i.get("FILE_DT"))),
        ("Office", i.get("ENGLISH_CITY_NAME")),
        ("Parties", parties),
        ("Recorded entries", len(rows)),
    ]
    trs = "".join(
        f"<tr><td>{_e(r.get('RE_NO')).split('.')[0]}</td><td>{_e(_date(r.get('DOC_DT')))}</td>"
        f"<td>{_e(r.get('ENGLISH_OFFICE_NAME'))}</td><td"
        f"{' class=conf' if r.get('IS_CONFIDENTIAL') == 'Y' else ''}>"
        f"{_e(r.get('RECORDED_ENTRY'))}</td></tr>"
        for r in rows
    )
    body = (
        f"<h1>{court}: {_e(number)}</h1>{_note(court, ents[0]['fetched_at'], FC_SEARCH)}"
        + "<dl>"
        + "".join(f"<dt>{k}</dt><dd>{_e(v)}</dd>" for k, v in head)
        + "</dl><table><tr><th>ID</th><th>Date</th><th>Office</th><th>Recorded entry</th></tr>"
        + trs
        + "</table>"
    )
    return f"FC {number}", PAGE.format(title=_e(number), body=body)


_TCC_LISTING: dict[str, dict] | None = None


def tcc_record(number: str):
    global _TCC_LISTING
    folder = RAW / "s12_tcc_dockets"
    if _TCC_LISTING is None:
        _TCC_LISTING = {}
        for m in _metas(folder):
            if "/appealnumber/courtnumber" in m["url"]:
                for r in _load(folder, m).get("data") or []:
                    if r.get("APPEAL_NBR"):
                        _TCC_LISTING[r["APPEAL_NBR"].strip()] = r
    ents = None
    for m in _metas(folder):
        if "/appealnumberRE" in m["url"]:
            if unquote(m["url"].split("appealnumber=")[1].split("&")[0]) == number:
                ents = (m, _load(folder, m))
                break
    if not ents:
        return None
    rows = sorted(ents[1].get("data") or [], key=lambda r: str(r.get("CREATED_DATE")))
    # file details from the year listing; every entry row repeats them, so fall back to those
    lr = _TCC_LISTING.get(number) or {}
    if not lr.get("NATURE"):
        # not in the cached year listing: use the processed table (no names there)
        import polars as pl

        p = pl.read_parquet(ROOT / "data" / "processed" / "s12" / "dockets.parquet")
        hit = p.filter(pl.col("docket") == number).to_dicts()
        if hit:
            h = hit[0]
            lr = {
                **lr,
                "NATURE": h.get("nature"),
                "ACTNAME": h.get("act_code"),
                "PROCEDURE": h.get("procedure"),
                "HEARING_LOC": h.get("hearing_location"),
                "FILED_DATE": h.get("date_filed"),
                "STATUS": h.get("status"),
                "DISPOSITION": h.get("disposition"),
                "DISPOSITION_DATE": h.get("closed_date"),
            }
    name = " ".join(x for x in (lr.get("APPELLANT_FIRST_NAME"), lr.get("APPELLANT_SURNAME")) if x)
    head = [
        ("Court file", number),
        ("Appellant", name),
        ("Nature", lr.get("NATURE")),
        ("Act", lr.get("ACTNAME")),
        ("Procedure", lr.get("PROCEDURE")),
        ("Hearing location", lr.get("HEARING_LOC")),
        ("Filed", _date(lr.get("FILED_DATE"))),
        ("Status", lr.get("STATUS")),
        ("Disposition", lr.get("DISPOSITION")),
        ("Disposition date", _date(lr.get("DISPOSITION_DATE"))),
        ("Docket entries", len(rows)),
    ]
    trs = "".join(
        f"<tr><td>{_e(_date(r.get('CREATED_DATE')))}</td><td>{_e(r.get('INFO'))}</td>"
        f"<td>{_e(r.get('NOTE_TEXT'))}</td></tr>"
        for r in rows
    )
    body = (
        f"<h1>Tax Court of Canada: {_e(number)}</h1>"
        f"{_note('Tax Court of Canada', ents[0]['fetched_at'], TCC_SEARCH)}<dl>"
        + "".join(f"<dt>{k}</dt><dd>{_e(v)}</dd>" for k, v in head)
        + "</dl><table><tr><th>Date</th><th>Entry</th><th>Note</th></tr>"
        + trs
        + "</table>"
    )
    return f"TCC {number}", PAGE.format(title=_e(number), body=body)


def numbers() -> tuple[list[str], list[str]]:
    q = json.loads((ROOT / "data" / "review" / "questions.json").read_text(encoding="utf-8"))
    text = [i["question"] for i in q["issues"]]
    for g in q["groups"]:
        text.append(g.get("intro", ""))
        for t in g.get("tables", []):
            text.extend(" ".join(r) for r in t["rows"])
    blob = "\n".join(text)
    tcc = sorted(set(TCC_RE.findall(blob)))
    fc = sorted(set(FC_RE.findall(blob)))
    return fc, tcc


def main(out: str) -> None:
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    fc, tcc = numbers()
    done, missing = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for n, fn in [(n, fc_record) for n in fc] + [(n, tcc_record) for n in tcc]:
            rec = fn(n)
            if rec is None:
                missing.append(n)
                continue
            name, page = rec
            h = Path(tmp) / "page.html"
            h.write_text(page, encoding="utf-8")
            pdf = outdir / f"{name}.pdf"
            subprocess.run(
                [
                    str(EDGE),
                    "--headless=new",
                    "--disable-gpu",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}",
                    h.as_uri(),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            done.append(pdf.name)
    print(f"{len(done)} PDFs written; not in our records: {', '.join(missing) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
