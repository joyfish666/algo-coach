"""LeetCode.cn session management and cookie invalidation detection.

Responsibilities:
- requests.Session construction from a pasted browser cookie string, with
  browser UA / Referer injection and csrfToken extraction
- cookie invalidation detection across three observed shapes: 403 status,
  redirect to the login page, and 200 + errors payload (cn-site GraphQL
  sessions often expire this way; checking status codes alone misses it)
- shared session/client lifecycle: process-wide singletons guarded by a lock;
  after a cookie update the session must be rebuilt immediately via
  rebuild(), otherwise stale cookies cause an "expired right after update"
  loop until restart
"""

from __future__ import annotations

import threading

import requests

from lc.exceptions import AuthError
from lc.httpclient import HttpClient
from lc.i18n import t

LEETCODE_CN_BASE = "https://leetcode.cn"
GRAPHQL_ENDPOINT = LEETCODE_CN_BASE + "/graphql/"
LOGIN_MARKER = "/accounts/login"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": LEETCODE_CN_BASE,
    "Accept": "application/json",
}

AUTH_ERROR_MARKERS = (
    "not logged in",
    "not login",
    "unauthenticated",
    "authentication",
    "login required",
    "anonymous user",
    "user is anonymous",
    "not authenticated",
    "未登录",
    "登录",
    "认证",
)


def parse_cookie_string(cookie_string: str) -> dict:
    jar = {}
    for pair in (cookie_string or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        name, sep, value = pair.partition("=")
        if sep and name.strip():
            jar[name.strip()] = value.strip()
    return jar


def extract_csrf_token(cookie_string: str) -> str:
    return parse_cookie_string(cookie_string).get("csrftoken", "")


def build_session(cookie_string: str = "") -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    token = extract_csrf_token(cookie_string)
    if token:
        session.headers["X-CSRFToken"] = token
    for name, value in parse_cookie_string(cookie_string).items():
        session.cookies.set(name, value)
    return session


def is_login_redirect(response) -> bool:
    for item in getattr(response, "history", None) or []:
        location = str(getattr(item, "headers", {}).get("Location", ""))
        if item.status_code in (301, 302, 303, 307, 308) and LOGIN_MARKER in location.lower():
            return True
    final_url = str(getattr(response, "url", "") or "")
    return LOGIN_MARKER in final_url.lower()


def body_reports_auth_error(response) -> bool:
    """Detect the 200 + errors payload shape of session expiration."""
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        return False
    errors = payload.get("errors") if isinstance(payload, dict) else None
    return is_auth_error_payload(errors)


def is_auth_error_payload(errors) -> bool:
    if not isinstance(errors, list) or not errors:
        return False
    for error in errors:
        message = ""
        if isinstance(error, dict):
            message = str(error.get("message", "") or error.get("code", ""))
        else:
            message = str(error)
        lowered = message.lower()
        for marker in AUTH_ERROR_MARKERS:
            if marker in lowered or marker in message:
                return True
    return False


def check_response(response, *, context: str = "") -> None:
    """Raise AuthError when the response matches any cookie-expired shape."""
    if getattr(response, "status_code", None) == 403:
        raise AuthError(t("cookie_invalid"), detail={"context": context, "shape": "403"})
    if is_login_redirect(response):
        raise AuthError(
            t("cookie_invalid"),
            detail={"context": context, "shape": "login_redirect"},
        )
    if body_reports_auth_error(response):
        raise AuthError(
            t("cookie_invalid"),
            detail={"context": context, "shape": "200_with_errors"},
        )


_state_lock = threading.Lock()
_persist_lock = threading.Lock()
_session = None
_http_client = None
_last_persisted_cookie: str | None = None


def configure(cookie_string: str = "", request_interval: float = None, timeout: float = None):
    """Build and register fresh session + client singletons."""
    global _session, _http_client, _last_persisted_cookie
    from lc.config import DEFAULTS, load

    interval = request_interval
    if interval is None:
        try:
            interval = float(load().get("request_interval", DEFAULTS["request_interval"]))
        except Exception:
            interval = DEFAULTS["request_interval"]
    new_session = build_session(cookie_string)
    client_kwargs = {"default_headers": dict(DEFAULT_HEADERS), "request_interval": interval}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    new_client = HttpClient(new_session, **client_kwargs)
    new_client.on_response = lambda response: _persist_rotated_cookies(new_client)
    with _state_lock:
        _session = new_session
        _http_client = new_client
    with _persist_lock:
        _last_persisted_cookie = None
    return _http_client


def _persist_rotated_cookies(client) -> None:
    """Persist session rotation: cn re-issues LEETCODE_SESSION on logins and
    may rotate it over time; browsers auto-save, so must we — otherwise the
    on-disk cookie goes stale while the in-memory one works, and vice versa
    when other processes probe with the old value.

    Serialized behind _persist_lock so a sync-worker thread and an API thread
    cannot interleave load/save and lose an update; the in-memory cache skips
    the disk round-trip entirely while the cookie is unchanged (the steady
    state for every response).
    """
    global _last_persisted_cookie
    from lc.config import load as load_config, save as save_config

    jar = client.session.cookies
    session_value = jar.get("LEETCODE_SESSION")
    if not session_value:
        return
    csrf_value = jar.get("csrftoken")
    new_cookie = f"csrftoken={csrf_value or ''}; LEETCODE_SESSION={session_value}"
    with _persist_lock:
        if new_cookie == _last_persisted_cookie:
            return
        current = load_config()
        if current.get("cookie") == new_cookie:
            _last_persisted_cookie = new_cookie
            return
        current["cookie"] = new_cookie
        if csrf_value:
            current["csrf_token"] = csrf_value
        save_config(current)
        _last_persisted_cookie = new_cookie


def rebuild(cookie_string: str = "", **kwargs):
    """Discard cached session/client immediately after a credential update."""
    return configure(cookie_string, **kwargs)


def get_session():
    with _state_lock:
        return _session


def get_http_client():
    with _state_lock:
        return _http_client


def reset_state() -> None:
    global _session, _http_client, _last_persisted_cookie
    with _state_lock:
        _session = None
        _http_client = None
    with _persist_lock:
        _last_persisted_cookie = None
