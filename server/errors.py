"""Error envelope and HTTP translation for the API layer.

Every error response uses one shape:

    {"error": {"kind": ..., "message": ..., "message_key": ..., "detail": ...}}

- domain exceptions (AlgoCoachError subclasses) carry message_key so the
  frontend re-translates the wording into the UI language
- http_domain_error is the message_key-carrying variant for conditions the
  domain layer does not model (a second sync while one runs, LLM unset)
- plain HTTPException (string detail) covers developer-facing validation
  messages; the handler in server.app reshapes it into the same envelope
- message is rendered in the backend process locale on purpose: it is the
  fallback for API consumers and logs, not the primary user-facing wording
  (the message_key protocol is, see lc.i18n)
"""

from __future__ import annotations

from fastapi import HTTPException

from lc.exceptions import (
    AlgoCoachError,
    AuthError,
    GroupNotFoundError,
    JudgeError,
    NetworkError,
    PremiumProblemError,
    ProblemNotFoundError,
    RateLimitError,
)
from lc.i18n import t
from lc.validate import is_safe_slug

STATUS_BY_EXCEPTION = {
    RateLimitError: 429,
    AuthError: 401,
    PremiumProblemError: 403,
    ProblemNotFoundError: 404,
    GroupNotFoundError: 404,
    NetworkError: 502,
    JudgeError: 502,
}


def status_for(exc: AlgoCoachError) -> int:
    """HTTP status for a domain error, honoring subclassing through the MRO."""
    for cls in type(exc).__mro__:
        if cls in STATUS_BY_EXCEPTION:
            return STATUS_BY_EXCEPTION[cls]
    return 400


def error_payload(kind: str, message: str, message_key: str | None = None, detail=None) -> dict:
    """Build the unified error envelope body."""
    body = {"kind": kind, "message": message}
    if message_key:
        body["message_key"] = message_key
    if detail is not None:
        body["detail"] = detail
    return body


def http_domain_error(status_code: int, message_key: str) -> HTTPException:
    """HTTPException variant that still carries a message_key.

    Plain `HTTPException(detail=t(key))` pre-rendered the message in the
    backend process locale, so the frontend could not translate it into the
    UI language the way it does for every domain error - sync conflicts and
    LLM-not-configured replies were stuck in whatever locale the coach
    process happened to run under.
    """
    return HTTPException(
        status_code=status_code,
        detail={
            "kind": "HTTPException",
            "message_key": message_key,
            "message": t(message_key),
        },
    )


def require_safe_qid(qid: str) -> str:
    """Reject path-traversal payloads before they reach filesystem paths.

    Same slug policy the site adapter enforces on remote data (lc.validate);
    bad client input answers 400 instead of the adapter's NetworkError.
    """
    if not is_safe_slug(qid):
        raise HTTPException(status_code=400, detail=f"invalid problem id: {qid!r}")
    return qid
