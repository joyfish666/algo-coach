"""Shared UTC timestamp helper.

problems.json (sync stamps) and submissions.jsonl (record timestamps) both
stamp ISO-8601 UTC at second precision; the exact format is load-bearing
because the archive's newest-first ordering sorts these strings lexically.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
