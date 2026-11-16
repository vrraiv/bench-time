"""Shared HTTP client: on-disk cache, single-threaded per-host rate limit, honest User-Agent,
append-only provenance manifest, and tier guards.

Every network request in this project goes through ``Client``. Source modules never import
httpx directly.

Cache layout: ``data/raw/<source>/<key>.<ext>`` with a sidecar ``<key>.meta.json``. The key is
sha256(method | url | body | vintage)[:24]. Only 2xx responses are served from cache; errors are
logged to the manifest but re-attempted on the next run. Passing ``vintage="2026-11"`` stores a
fresh copy alongside earlier ones for sources that change in place (StatCan tables, FJA page).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from courtdelay import __version__
from courtdelay.common import paths

log = logging.getLogger(__name__)

CONTACT_ENV = "COURTDELAY_CONTACT"

#: Default seconds between requests to the same host (court websites).
DEFAULT_DELAY = 4.0

#: Hosts whose published terms / nature permit faster polling. Seconds between requests.
FAST_HOSTS: dict[str, float] = {
    "www150.statcan.gc.ca": 1.0,  # StatCan Web Data Service (public API)
    "api.a2aj.ca": 1.0,  # A2AJ API
    "huggingface.co": 1.0,
    "datasets-server.huggingface.co": 1.0,
    "web.archive.org": 2.0,  # Wayback: polite but it is built for this
}

#: Tier 3 hosts: never request, not even robots.txt (see docs/HANDOFF.md section 3).
BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "calendly.com",
        "ontariocourtdates.ca",
        "canlii.org",
        "canlii.ca",
        "ontariocourts.on.ca",  # Ontario Courts Public Portal; distinct from ontariocourts.ca
    }
)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class Tier3Error(RuntimeError):
    """Raised for any request to a Tier 3 host."""


class ContactRequiredError(RuntimeError):
    """Raised for Tier 2 (docket) requests while COURTDELAY_CONTACT is unset."""


class FetchError(RuntimeError):
    """Raised when a request fails after retries or returns a non-2xx status."""

    def __init__(self, url: str, status: int | None, detail: str = ""):
        self.url, self.status = url, status
        super().__init__(f"{status} {url} {detail}".strip())


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _host_blocked(host: str) -> bool:
    return any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)


def user_agent() -> str:
    contact = os.environ.get(CONTACT_ENV, "").strip()
    if not contact:
        warnings.warn(
            f"{CONTACT_ENV} is unset; User-Agent will say so. Tier 2 requests are refused.",
            stacklevel=2,
        )
        contact = "contact not configured"
    return f"bench-time/{__version__} (court-delay research; {contact})"


_EXT = {
    "application/json": "json",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/octet-stream": "bin",
    "application/x-parquet": "parquet",
    "application/vnd.apache.parquet": "parquet",
}


def _ext_for(content_type: str, url: str) -> str:
    ct = content_type.split(";")[0].strip().lower()
    if ct in _EXT:
        return _EXT[ct]
    tail = urlsplit(url).path.rsplit(".", 1)
    if len(tail) == 2 and 1 <= len(tail[1]) <= 7 and tail[1].isalnum():
        return tail[1].lower()
    return "bin"


@dataclass(frozen=True)
class Response:
    url: str
    final_url: str
    status: int
    content: bytes
    content_type: str
    path: Path
    fetched_at: str
    from_cache: bool

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)


class Client:
    """Single-threaded, caching, rate-limited HTTP client.

    ``clock``/``sleep`` are injectable so tests don't wait. ``transport`` lets tests use
    ``httpx.MockTransport``.
    """

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        default_delay: float = DEFAULT_DELAY,
        timeout: float = 60.0,
        manifest: Path | None = None,
    ):
        self._http = httpx.Client(
            transport=transport,
            headers={"User-Agent": user_agent()},
            timeout=timeout,
            follow_redirects=True,
        )
        self._clock, self._sleep = clock, sleep
        self._default_delay = default_delay
        self._last_request: dict[str, float] = {}
        self._manifest = manifest

    # -- public API ---------------------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        source: str,
        tier: int = 1,
        params: dict | None = None,
        vintage: str = "",
        refresh: bool = False,
    ) -> Response:
        return self.request(
            "GET", url, source=source, tier=tier, params=params, vintage=vintage, refresh=refresh
        )

    def post_json(
        self,
        url: str,
        body,
        *,
        source: str,
        tier: int = 1,
        vintage: str = "",
        refresh: bool = False,
    ) -> Response:
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        return self.request(
            "POST",
            url,
            source=source,
            tier=tier,
            body=raw,
            headers={"Content-Type": "application/json"},
            vintage=vintage,
            refresh=refresh,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        source: str,
        tier: int = 1,
        params: dict | None = None,
        body: bytes | None = None,
        headers: dict | None = None,
        vintage: str = "",
        refresh: bool = False,
    ) -> Response:
        if params:
            url = str(httpx.URL(url, params=params))
        self._guard(url, tier)
        key = self._cache_key(method, url, body, vintage)
        raw = paths.raw_dir(source)
        meta_path = raw / f"{key}.meta.json"
        if not refresh and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            data_path = raw / meta["file"]
            if 200 <= meta["status"] < 300 and data_path.exists():
                return Response(
                    url=url,
                    final_url=meta.get("final_url", url),
                    status=meta["status"],
                    content=data_path.read_bytes(),
                    content_type=meta.get("content_type", ""),
                    path=data_path,
                    fetched_at=meta["fetched_at"],
                    from_cache=True,
                )
        return self._fetch_and_store(method, url, body, headers, source, raw, key, meta_path)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internals ----------------------------------------------------------------------

    def _guard(self, url: str, tier: int) -> None:
        host = _host(url)
        if _host_blocked(host):
            raise Tier3Error(f"{host} is a Tier 3 source; no requests without explicit approval")
        if tier >= 2 and not os.environ.get(CONTACT_ENV, "").strip():
            raise ContactRequiredError(
                f"Tier {tier} request to {host} refused: {CONTACT_ENV} unset"
            )

    @staticmethod
    def _cache_key(method: str, url: str, body: bytes | None, vintage: str) -> str:
        h = hashlib.sha256()
        for part in (method.upper().encode(), url.encode(), body or b"", vintage.encode()):
            h.update(part)
            h.update(b"\x00")
        return h.hexdigest()[:24]

    def _throttle(self, host: str) -> None:
        delay = FAST_HOSTS.get(host, self._default_delay)
        last = self._last_request.get(host)
        if last is not None:
            wait = delay - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _fetch_and_store(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: dict | None,
        source: str,
        raw: Path,
        key: str,
        meta_path: Path,
    ) -> Response:
        host = _host(url)
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle(host)
            fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
            try:
                resp = self._http.request(method, url, content=body, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._log_manifest(url, method, source, fetched_at, None, None, None, str(exc))
                log.warning("attempt %d/%d failed for %s: %s", attempt, MAX_ATTEMPTS, url, exc)
                self._sleep(min(30.0, 5.0 * attempt))
                continue
            content = resp.content
            sha = hashlib.sha256(content).hexdigest()
            ctype = resp.headers.get("content-type", "")
            fname = f"{key}.{_ext_for(ctype, url)}"
            data_path = raw / fname
            data_path.write_bytes(content)
            meta = {
                "url": url,
                "final_url": str(resp.url),
                "method": method,
                "status": resp.status_code,
                "content_type": ctype,
                "fetched_at": fetched_at,
                "sha256": sha,
                "bytes": len(content),
                "file": fname,
                "response_headers": {
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower() in {"last-modified", "etag", "content-type", "retry-after"}
                },
            }
            meta_path.write_text(json.dumps(meta, indent=1))
            self._log_manifest(
                url, method, source, fetched_at, resp.status_code, sha, str(data_path), ""
            )
            if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                ra = resp.headers.get("retry-after")
                wait = float(ra) if ra and ra.isdigit() else 10.0 * attempt
                log.warning("%s from %s; retrying in %.0fs", resp.status_code, host, wait)
                self._sleep(min(wait, 120.0))
                continue
            if not 200 <= resp.status_code < 300:
                raise FetchError(url, resp.status_code)
            return Response(
                url=url,
                final_url=str(resp.url),
                status=resp.status_code,
                content=content,
                content_type=ctype,
                path=data_path,
                fetched_at=fetched_at,
                from_cache=False,
            )
        raise FetchError(url, None, f"after {MAX_ATTEMPTS} attempts: {last_exc}")

    def _log_manifest(
        self,
        url: str,
        method: str,
        source: str,
        fetched_at: str,
        status: int | None,
        sha256: str | None,
        path: str | None,
        error: str,
    ) -> None:
        row = {
            "url": url,
            "method": method,
            "source": source,
            "fetched_at": fetched_at,
            "status": status,
            "sha256": sha256,
            "path": path,
            "error": error or None,
        }
        mp = self._manifest or paths.manifest_path()
        with mp.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def robots_txt(client: Client, url: str, *, source: str = "robots") -> str | None:
    """Fetch and cache a host's robots.txt (None if 4xx). Goes through the tier guard."""
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        return client.get(robots_url, source=source).text
    except FetchError as exc:
        if exc.status and 400 <= exc.status < 500:
            return None
        raise


def robots_allows(robots: str | None, url: str, agent: str = "bench-time") -> bool:
    """Check a URL against robots.txt text using the stdlib parser (our UA, then *)."""
    if robots is None:
        return True
    from urllib import robotparser

    rp = robotparser.RobotFileParser()
    rp.parse(robots.splitlines())
    return rp.can_fetch(agent, url)
