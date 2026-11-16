import json

import httpx
import pytest

from courtdelay.common import http


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTDELAY_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(http.CONTACT_ENV, raising=False)
    return tmp_path


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.slept: list[float] = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make_client(handler, clock):
    with pytest.warns(UserWarning):  # contact unset in tests
        return http.Client(
            transport=httpx.MockTransport(handler), clock=clock.now, sleep=clock.sleep
        )


def test_user_agent_uses_env(monkeypatch):
    monkeypatch.setenv(http.CONTACT_ENV, "someone@example.org")
    assert http.user_agent() == "bench-time/0.1.0 (court-delay research; someone@example.org)"
    monkeypatch.delenv(http.CONTACT_ENV)
    with pytest.warns(UserWarning):
        assert "contact not configured" in http.user_agent()


def test_cache_and_manifest(env):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"ok": 1}, headers={"content-type": "application/json"})

    c = make_client(handler, FakeClock())
    r1 = c.get("https://example.gc.ca/a", source="s_test")
    r2 = c.get("https://example.gc.ca/a", source="s_test")
    assert r1.json() == {"ok": 1} and not r1.from_cache
    assert r2.from_cache and r2.content == r1.content
    assert len(calls) == 1, "second call must come from disk cache"
    assert r1.path.suffix == ".json" and r1.path.parent.name == "s_test"
    rows = [json.loads(line) for line in (env / "manifest.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["status"] == 200 and len(rows[0]["sha256"]) == 64
    # a new vintage stores a new file rather than overwriting
    r3 = c.get("https://example.gc.ca/a", source="s_test", vintage="2026-12")
    assert not r3.from_cache and r3.path != r1.path and len(calls) == 2


def test_post_cache_key_includes_body(env):
    def handler(request):
        return httpx.Response(200, json={"echo": json.loads(request.content)})

    c = make_client(handler, FakeClock())
    a = c.post_json("https://example.gc.ca/api", [{"productId": 1}], source="s_test")
    b = c.post_json("https://example.gc.ca/api", [{"productId": 2}], source="s_test")
    assert a.json() != b.json() and not b.from_cache


def test_errors_not_served_from_cache(env):
    status = [503, 503, 503, 200]

    def handler(request):
        return httpx.Response(status.pop(0), text="x")

    c = make_client(handler, FakeClock())
    with pytest.raises(http.FetchError):
        c.get("https://example.gc.ca/b", source="s_test")  # 3 attempts, all 503
    r = c.get("https://example.gc.ca/b", source="s_test")  # retried, not served from cache
    assert r.status == 200 and not r.from_cache
    rows = (env / "manifest.jsonl").read_text().splitlines()
    assert len(rows) == 4, "every network attempt is logged"


def test_rate_limit_per_host(env):
    def handler(request):
        return httpx.Response(200, text="ok")

    clock = FakeClock()
    c = make_client(handler, clock)
    c.get("https://court.example.ca/1", source="s_test")
    c.get("https://court.example.ca/2", source="s_test")
    assert clock.slept == [pytest.approx(4.0)], "default 4 s between requests to a court host"
    c.get("https://www150.statcan.gc.ca/x", source="s_test")  # other host: no wait
    c.get("https://www150.statcan.gc.ca/y", source="s_test")
    assert clock.slept[-1] == pytest.approx(1.0), "StatCan allowlisted at 1 s"


def test_tier_guards(env, monkeypatch):
    c = make_client(lambda r: httpx.Response(200), FakeClock())
    with pytest.raises(http.Tier3Error):
        c.get("https://www.canlii.org/robots.txt", source="s_test")
    with pytest.raises(http.Tier3Error):
        c.get("https://calendly.com/toronto-region", source="s_test")
    with pytest.raises(http.ContactRequiredError):
        c.get("https://www.fct-cf.gc.ca/en/court-files", source="s10", tier=2)
    monkeypatch.setenv(http.CONTACT_ENV, "x@example.org")
    c.get("https://www.fct-cf.gc.ca/en/court-files", source="s10", tier=2)  # now allowed


def test_robots_allows():
    txt = "User-agent: *\nDisallow: /private/\n"
    assert http.robots_allows(txt, "https://x.ca/public/a")
    assert not http.robots_allows(txt, "https://x.ca/private/a")
    assert http.robots_allows(None, "https://x.ca/anything")


def test_download_streams_to_cache(env):
    payload = b"x" * (3 << 20)

    def handler(request):
        return httpx.Response(
            200, content=payload, headers={"content-type": "application/x-parquet"}
        )

    c = make_client(handler, FakeClock())
    r = c.download(
        "https://huggingface.co/datasets/x/y/resolve/main/SCC/train.parquet", source="s3"
    )
    assert (
        r.content == b"" and r.path.suffix == ".parquet" and r.path.stat().st_size == len(payload)
    )
    r2 = c.download(
        "https://huggingface.co/datasets/x/y/resolve/main/SCC/train.parquet", source="s3"
    )
    assert r2.from_cache and r2.path == r.path
    rows = [json.loads(line) for line in (env / "manifest.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["sha256"] == __import__("hashlib").sha256(payload).hexdigest()
