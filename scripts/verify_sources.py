"""Verify candidate source URLs through the shared client (cached, rate-limited, in manifest).

Usage: uv run python scripts/verify_sources.py [--out summary.json] [SOURCE_ID ...]

For each URL: fetch the host's robots.txt once, GET the URL, record status, final URL,
content type, size, HTML <title>, robots verdict, and (for HTML) links whose text or href
match discovery keywords. Tier 3 hosts are refused by the client itself. Tier 2 entries here
are landing/terms pages only, never docket queries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from courtdelay.common import http

KEYWORDS = re.compile(
    r"statistic|annual report|rapport annuel|year in review|r[ée]trospective|workload|"
    r"court files|dossiers|terms|conditions|avis|notice|\.pdf|\.csv|\.xlsx|judges|juges",
    re.I,
)

CANDIDATES: dict[str, list[str]] = {
    "S1": [
        "https://www.statcan.gc.ca/en/developers/wds/user-guide",
        "https://www150.statcan.gc.ca/t1/wds/rest/getCubeMetadata",  # POST handled specially
        "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/35100029/en",
        "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3510002901",
        "https://www.statcan.gc.ca/en/reference/licence",
    ],
    "S2": [
        "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/35100112/en",
        "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/35100114/en",
    ],
    "S3": [
        "https://api.a2aj.ca/",
        "https://api.a2aj.ca/docs",
        "https://api.a2aj.ca/openapi.json",
        "https://huggingface.co/api/datasets/a2aj/canadian-case-law",
        "https://huggingface.co/api/datasets/a2aj/canadian-case-law/tree/main",
        "https://www.a2aj.ca/",
    ],
    "S4": [
        "https://huggingface.co/api/datasets/refugee-law-lab/luck-of-the-draw-iii",
        "https://huggingface.co/api/datasets/refugee-law-lab/luck-of-the-draw-iii/tree/main",
    ],
    "S5": [
        "https://www.scc-csc.ca/case-dossier/stat/index-eng.aspx",
        "https://www.scc-csc.ca/review-revue/2024/index-eng.aspx",
        "https://www.scc-csc.ca/review-revue/2023/index-eng.aspx",
        "https://www.scc-csc.ca/review-revue/index-eng.aspx",
        "https://www.scc-csc.ca/terms-avis/notice-enonce-eng.aspx",
    ],
    "S6": [
        "https://www.ontariocourts.ca/coa/",
        "https://www.ontariocourts.ca/coa/publications/",
        "https://www.ontariocourts.ca/coa/annual-report/",
    ],
    "S7": [
        "https://www.ontariocourts.ca/ocj/statistics/",
        "https://www.ontariocourts.ca/ocj/stats-criminal/",
        "https://www.ontariocourts.ca/en/terms-of-use/",
        "https://www.ontariocourts.ca/ocj/legal/",
        "https://collections.ola.org/",
        "https://collections.ola.org/ser/283147",
        "https://collections.ola.org/ser/108774",
    ],
    "S8": [
        "https://www.fct-cf.gc.ca/en/pages/about-the-court/statistics",
        "https://www.fct-cf.gc.ca/en/pages/about-the-court",
        "https://www.fct-cf.ca/",
        "https://www.fca-caf.ca/en/pages/about-the-court/statistics",
        "https://www.fca-caf.ca/en/pages/about-the-court",
        "https://www.tcc-cci.gc.ca/en/pages/about-the-court/statistics",
        "https://www.tcc-cci.gc.ca/en/pages/about-the-court",
        "https://www.tcc-cci.ca/",
        "https://www.cas-satj.gc.ca/en/publications/ar/index.shtml",
        "https://www.cas-satj.gc.ca/en/publications/index.shtml",
    ],
    "S9": [
        "https://www.fja.gc.ca/appointments-nominations/judges-juges-eng.aspx",
        "https://www.fja-cmf.gc.ca/appointments-nominations/judges-juges-eng.aspx",
        "https://www.fja.gc.ca/home-accueil/index-eng.html",
        (
            "https://web.archive.org/cdx/search/cdx?url=fja.gc.ca/appointments-nominations/"
            "judges-juges-eng.aspx&output=json&fl=timestamp,original,statuscode,digest"
            "&collapse=timestamp:6&limit=20"
        ),
        (
            "https://web.archive.org/cdx/search/cdx?url=fja-cmf.gc.ca/appointments-nominations/"
            "judges-juges-eng.aspx&output=json&fl=timestamp,original,statuscode,digest"
            "&collapse=timestamp:6&limit=20"
        ),
    ],
    # Tier 2: landing / terms pages only. No docket queries.
    "S10": [
        "https://www.fct-cf.gc.ca/en/court-files-and-decisions/court-files",
        "https://www.fct-cf.gc.ca/en/pages/important-notices",
    ],
    "S11": [
        "https://www.fca-caf.ca/en/pages/court-files",
        "https://www.fca-caf.ca/en/pages/important-notices",
    ],
    "S12": [
        "https://www.tcc-cci.gc.ca/en/pages/court-files",
        "https://www.tcc-cci.gc.ca/en/pages/important-notices",
    ],
}


def summarize(resp: http.Response, robots: str | None) -> dict:
    row: dict = {
        "url": resp.url,
        "final_url": resp.final_url,
        "status": resp.status,
        "content_type": resp.content_type.split(";")[0],
        "bytes": len(resp.content),
        "from_cache": resp.from_cache,
        "robots_allows": http.robots_allows(robots, resp.final_url),
    }
    if "html" in row["content_type"]:
        soup = BeautifulSoup(resp.content, "lxml")
        row["title"] = (soup.title.get_text(strip=True) if soup.title else "")[:120]
        links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            href = urljoin(resp.final_url, a["href"])
            if KEYWORDS.search(text) or KEYWORDS.search(href):
                links.append(f"{text[:70]} -> {href}")
        row["links"] = sorted(set(links))[:80]
    elif "json" in row["content_type"]:
        row["preview"] = resp.text[:600]
    else:
        row["preview"] = resp.text[:300]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="verify_summary.json")
    ap.add_argument("--extra", help="JSON file {source_id: [urls]} merged into CANDIDATES")
    ap.add_argument("sources", nargs="*")
    args = ap.parse_args()
    if args.extra:
        with open(args.extra, encoding="utf-8") as fh:
            for k, v in json.load(fh).items():
                CANDIDATES.setdefault(k, []).extend(v)
    wanted = [s.upper() for s in args.sources] or list(CANDIDATES)
    results: dict[str, list[dict]] = {}
    robots_cache: dict[str, str | None] = {}
    with http.Client() as client:
        for sid in wanted:
            results[sid] = []
            for url in CANDIDATES[sid]:
                host = urlsplit(url).netloc
                if host not in robots_cache:
                    try:
                        robots_cache[host] = http.robots_txt(client, url, source="verify")
                    except Exception as exc:  # noqa: BLE001
                        robots_cache[host] = None
                        print(f"[{sid}] robots.txt {host}: {exc}", file=sys.stderr)
                try:
                    if url.endswith("getCubeMetadata"):
                        resp = client.post_json(url, [{"productId": 35100029}], source="verify")
                    else:
                        resp = client.get(url, source="verify")
                    row = summarize(resp, robots_cache[host])
                except Exception as exc:  # noqa: BLE001
                    row = {"url": url, "error": f"{type(exc).__name__}: {exc}"}
                row["robots_txt"] = (robots_cache[host] or "")[:1500]
                results[sid].append(row)
                print(f"[{sid}] {row.get('status', 'ERR')} {url} -> {row.get('final_url', '')}")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, ensure_ascii=False)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
