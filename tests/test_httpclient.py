import threading

import pytest
import requests

import lc.httpclient as httpclient_module
from lc.httpclient import HttpClient, RateLimiter, http_date_in, parse_retry_after
from lc.exceptions import NetworkError, RateLimitError


class FakeResponse:
    def __init__(self, status_code=200, headers=None, payload=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self.text = text or json.dumps(payload) if payload is not None else ""
        self.encoding = "iso-8859-1"
        self.url = "https://example.test/"

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


class FakeTime:
    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def fake_time(monkeypatch):
    ft = FakeTime()
    monkeypatch.setattr(httpclient_module.time, "monotonic", ft.monotonic)
    monkeypatch.setattr(httpclient_module.time, "sleep", ft.sleep)
    yield ft


def make_client(session, **kwargs):
    kwargs.setdefault("request_interval", 0.0)
    kwargs.setdefault("jitter_max", 0.0)
    return HttpClient(session, default_headers={"User-Agent": "UA"}, **kwargs)


def test_rate_limiter_enforces_interval(fake_time):
    limiter = RateLimiter(interval=10.0, jitter_max=0.0)
    assert limiter.reserve() == 0.0
    second = limiter.reserve()
    assert 9.5 <= second <= 10.5


def test_rate_limiter_thread_safety(fake_time):
    limiter = RateLimiter(interval=5.0, jitter_max=0.0)
    reservations = []
    lock = threading.Lock()

    def worker():
        delay = limiter.reserve()
        with lock:
            reservations.append(delay)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(round(r, 6) for r in reservations) == [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]


def test_headers_merged_and_timeout_forced(fake_time):
    session = ScriptedSession([FakeResponse(200)])
    client = make_client(session, timeout=7.5)
    response = client.get("https://example.test/x", headers={"X-Extra": "1"})
    assert response.status_code == 200
    call = session.calls[0]
    assert call["headers"]["User-Agent"] == "UA"
    assert call["headers"]["X-Extra"] == "1"
    assert call["timeout"] == 7.5


def test_response_encoding_forced_utf8(fake_time):
    session = ScriptedSession([FakeResponse(200)])
    client = make_client(session)
    response = client.get("https://example.test/")
    assert response.encoding == "utf-8"


def test_get_retries_network_error_then_succeeds(fake_time):
    session = ScriptedSession(
        [requests.ConnectionError("boom"), requests.ConnectionError("boom"), FakeResponse(200)]
    )
    client = make_client(session)
    response = client.get("https://example.test/")
    assert response.status_code == 200
    assert len(session.calls) == 3
    assert [round(s) for s in fake_time.sleeps] == [1, 2]


def test_post_never_retries_on_network_error(fake_time):
    session = ScriptedSession([requests.ConnectionError("boom")])
    client = make_client(session)
    with pytest.raises(NetworkError):
        client.post("https://example.test/run", idempotent=False, json={})
    assert len(session.calls) == 1
    assert fake_time.sleeps == []


def test_get_429_honors_integer_retry_after(fake_time):
    session = ScriptedSession(
        [FakeResponse(429, headers={"Retry-After": "7"}), FakeResponse(200)]
    )
    client = make_client(session)
    response = client.get("https://example.test/")
    assert response.status_code == 200
    assert fake_time.sleeps == [7.0]


def test_get_429_http_date_retry_after(fake_time):
    date_value = http_date_in(12)
    session = ScriptedSession([FakeResponse(429, headers={"Retry-After": date_value}), FakeResponse(200)])
    client = make_client(session)
    response = client.get("https://example.test/")
    assert response.status_code == 200
    assert fake_time.sleeps and 11.0 <= fake_time.sleeps[0] <= 13.0


def test_get_429_exponential_backoff_then_rate_limit_error(fake_time):
    outcomes = [FakeResponse(429) for _ in range(5)]
    session = ScriptedSession(outcomes)
    client = make_client(session, max_retries=3)
    with pytest.raises(RateLimitError):
        client.get("https://example.test/")
    assert [round(s) for s in fake_time.sleeps] == [1, 2, 4]
    assert len(session.calls) == 4


def test_post_429_fails_fast_without_retry(fake_time):
    session = ScriptedSession([FakeResponse(429, headers={"Retry-After": "3"})])
    client = make_client(session)
    with pytest.raises(RateLimitError) as exc_info:
        client.post("https://example.test/submit", idempotent=False, json={})
    assert exc_info.value.retry_after == 3.0
    assert len(session.calls) == 1
    assert fake_time.sleeps == []


def test_parse_retry_after_variants():
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("5") == 5.0
    past = http_date_in(-30)
    assert parse_retry_after(past) == 0.0
    future = http_date_in(45)
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    delta = parse_retry_after(future, now=now)
    assert 43.0 <= delta <= 46.0
    assert parse_retry_after("garbage-date") is None


def test_backoff_capped_at_thirty_seconds():
    client = HttpClient(ScriptedSession([]))
    assert client._backoff_delay(1) == 1.0
    assert client._backoff_delay(2) == 2.0
    assert client._backoff_delay(3) == 4.0
    assert client._backoff_delay(10) == httpclient_module.BACKOFF_CAP_SECONDS
