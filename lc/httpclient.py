"""Unified HTTP layer.

Discipline enforced here for every outbound call:
- forced timeout (no unbounded waits)
- thread-safe rate limiting: minimum interval between requests plus random
  jitter, accounted under a lock so concurrent thread-pool workers cannot
  punch through the gate
- retries restricted to idempotent reads only; run/submit/interpret style
  non-idempotent requests fail fast with a structured error so the user
  decides whether to retry
- UTF-8 response decoding, browser UA/Referer injection
- 429 handling: Retry-After first (integer seconds or HTTP-date), otherwise
  exponential backoff 1s -> 2s -> 4s capped at 30s; the Retry-After *wait*
  is capped at the same 30s so a hostile or broken header cannot park the
  calling thread (e.g. a sync worker) for hours - the uncapped value is kept
  on the raised RateLimitError for the API's Retry-After response header
"""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime

import requests

from lc.exceptions import NetworkError, RateLimitError
from lc.logutil import logger, redact_headers

DEFAULT_REQUEST_INTERVAL = 2.0
DEFAULT_JITTER_MAX = 1.0
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RETRIES = 3
BACKOFF_CAP_SECONDS = 30.0

TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})


def parse_retry_after(value, now=None):
    """Parse a Retry-After header value: integer seconds or HTTP-date."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    reference = now or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - reference).total_seconds()
    return max(0.0, delta)


def http_date_in(seconds: int) -> str:
    target = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return format_datetime(target, usegmt=True)


class RateLimiter:
    """Thread-safe minimum-interval request pacing."""

    def __init__(self, interval: float, jitter_max: float = DEFAULT_JITTER_MAX):
        self.interval = max(0.0, float(interval))
        self.jitter_max = max(0.0, float(jitter_max))
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def reserve(self) -> float:
        """Reserve the next slot and return how long to wait before sending."""
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_allowed)
            jitter = random.uniform(0.0, self.jitter_max) if self.jitter_max else 0.0
            self._next_allowed = start + self.interval + jitter
        return start - time.monotonic()

    def wait(self) -> None:
        delay = self.reserve()
        if delay > 0:
            time.sleep(delay)

    def reset(self) -> None:
        with self._lock:
            self._next_allowed = 0.0


class HttpClient:
    def __init__(
        self,
        session,
        *,
        default_headers=None,
        timeout: float = DEFAULT_TIMEOUT,
        request_interval: float = DEFAULT_REQUEST_INTERVAL,
        jitter_max: float = DEFAULT_JITTER_MAX,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.session = session
        self.default_headers = dict(default_headers or {})
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self.limiter = RateLimiter(request_interval, jitter_max)
        self.on_response = None

    def set_session(self, session) -> None:
        self.session = session

    def get(self, url, **kwargs):
        kwargs.setdefault("idempotent", True)
        return self.request("GET", url, **kwargs)

    def post(self, url, *, idempotent=False, **kwargs):
        kwargs["idempotent"] = idempotent
        return self.request("POST", url, **kwargs)

    def _backoff_delay(self, attempt: int) -> float:
        delay = float(2 ** max(0, attempt - 1))
        return min(BACKOFF_CAP_SECONDS, delay)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict = None,
        **kwargs,
    ):
        idempotent = kwargs.pop("idempotent", None)
        if idempotent is None:
            idempotent = method.upper() == "GET"
        merged_headers = {**self.default_headers, **(headers or {})}
        kwargs.setdefault("timeout", self.timeout)
        kwargs["headers"] = merged_headers
        max_attempts = 1 + self.max_retries if idempotent else 1

        attempt = 0
        while True:
            attempt += 1
            self.limiter.wait()
            logger.debug(
                "http %s %s headers=%s",
                method,
                url,
                redact_headers(merged_headers),
            )
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.RequestException as exc:
                if idempotent and attempt <= self.max_retries:
                    wait = self._backoff_delay(attempt)
                    logger.warning(
                        "network error on %s %s (attempt %s/%s), retrying in %.1fs: %s",
                        method,
                        url,
                        attempt,
                        max_attempts,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                    continue
                raise NetworkError(f"{method} {url} failed: {exc}") from exc

            response.encoding = "utf-8"

            if self.on_response is not None:
                try:
                    self.on_response(response)
                except Exception as exc:
                    logger.warning("on_response hook failed: %s", exc)

            if response.status_code == 429:
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                if idempotent and attempt <= self.max_retries:
                    if retry_after is not None:
                        wait = min(retry_after, BACKOFF_CAP_SECONDS)
                    else:
                        wait = self._backoff_delay(attempt)
                    logger.warning(
                        "429 on %s %s (attempt %s/%s), backing off %.1fs",
                        method,
                        url,
                        attempt,
                        max_attempts,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                raise RateLimitError(
                    f"429 rate limited on {method} {url}",
                    retry_after=retry_after,
                )

            transient = response.status_code in TRANSIENT_STATUS_CODES
            if transient and idempotent and attempt <= self.max_retries:
                wait = self._retry_wait_for_transient(response, attempt)
                logger.warning(
                    "%s on %s %s (attempt %s/%s), retrying in %.1fs",
                    response.status_code,
                    method,
                    url,
                    attempt,
                    max_attempts,
                    wait,
                )
                time.sleep(wait)
                continue
            return response

    def _retry_wait_for_transient(self, response, attempt: int) -> float:
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        if retry_after is not None:
            return min(retry_after, BACKOFF_CAP_SECONDS)
        return self._backoff_delay(attempt)
