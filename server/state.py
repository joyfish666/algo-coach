"""Process-wide singletons and config-derived factories shared by routers.

Everything here is the patchable seam for tests: routers call these through
the module namespace (`state.create_adapter()`), so monkeypatching an
attribute on this module reroutes every router at once.

Locking discipline (see also lc.auth / lc.config):
- `_archive_lock` guards only the lazy Archive construction
- `lifecycle_lock` serializes sync startup against the destructive data
  wipe: without it a POST /api/problems/sync could slip in between clear's
  running-check and the directory deletion, leaving a half-rebuilt cache in
  a "cleared" dir
- reset_app_state drops lazily-built singletons so embedders/tests can
  re-isolate the process after the data directory changes
"""

from __future__ import annotations

import threading

from lc import auth, problems
from lc.archive import Archive
from lc.config import effective_config, workspace_root_path
from lc.exceptions import AlgoCoachError
from lc.httpclient import HttpClient
from lc.langs import DEFAULT_LANGUAGE
from lc.llm import DEFAULT_MODEL, LLMClient
from lc.logutil import logger
from lc.sites.cn import LeetCodeCnAdapter
from server.errors import http_domain_error

sync_engine = problems.SyncEngine()

lifecycle_lock = threading.Lock()

_archive_lock = threading.Lock()
_archive: Archive | None = None


def get_archive() -> Archive:
    global _archive
    with _archive_lock:
        if _archive is None:
            from lc.config import archive_path

            _archive = Archive(archive_path())
        return _archive


def reset_app_state() -> None:
    """Drop lazily-built process singletons.

    The sync engine is reset here too: it is a module-level singleton whose
    run state (running flag, accumulated rows) would otherwise leak an
    in-flight or failed run across a data-directory swap.
    """
    global _archive
    with _archive_lock:
        _archive = None
    sync_engine.reset()


def create_adapter() -> LeetCodeCnAdapter:
    """Build the site adapter, lazily configuring the session from config."""
    client = auth.get_http_client()
    if client is None:
        config = effective_config()
        cookie = str(config.get("cookie", "") or "")
        if not cookie:
            raise http_domain_error(400, "cookie_missing")
        client = auth.configure(cookie, request_interval=config["request_interval"])
    return LeetCodeCnAdapter(client=client)


def validate_cookie_standalone(cookie: str) -> dict:
    """Validate a pasted cookie without touching the global session."""
    config = effective_config()
    session = auth.build_session(cookie)
    # deliberately isolated from the global singletons: a failed validation
    # must never clobber a working session; closed afterwards so the pooled
    # connections do not linger until GC
    try:
        client = HttpClient(
            session,
            default_headers=dict(auth.DEFAULT_HEADERS),
            request_interval=min(float(config.get("request_interval", 2.0)), 1.0),
        )
        adapter = LeetCodeCnAdapter(client=client)
        return adapter.validate_cookie()
    finally:
        session.close()


def build_llm() -> LLMClient:
    """LLM client from the saved config; 400 when not configured."""
    config = effective_config()
    api_key = str(config.get("llm_api_key", "") or "")
    base_url = str(config.get("llm_base_url", "") or "")
    if not api_key or not base_url:
        raise http_domain_error(400, "ask_not_configured")
    return LLMClient(
        base_url=base_url,
        api_key=api_key,
        model=str(config.get("llm_model", "") or DEFAULT_MODEL),
        timeout=float(config.get("llm_timeout", 120.0)),
        thinking=str(config.get("llm_thinking", "") or "default"),
    )


def workspace_root():
    return workspace_root_path(effective_config())


def default_language() -> str:
    return effective_config().get("default_language", DEFAULT_LANGUAGE)


def problem_row_for(slug: str, adapter=None, cache_rows=None) -> dict:
    """Cache row for one problem, self-healing from the site when missing."""
    rows = cache_rows
    if rows is None:
        rows = problems.load_problems()["problems"]
    row = next((p for p in rows if p.get("slug") == slug), None)
    if row is not None:
        return row
    if adapter is None:
        return {}
    try:
        detail = adapter.fetch_question_detail(slug)
        summary = problems.summary_from_detail(detail)
        problems.upsert_summary_into_cache(summary)
        logger.info("self-healed problem cache entry for %s", slug)
        return problems.decorate_problem_row(summary)
    except AlgoCoachError as exc:
        logger.warning("could not self-heal problem %s: %s", slug, exc)
        return {}


__all__ = [
    "sync_engine",
    "lifecycle_lock",
    "get_archive",
    "reset_app_state",
    "create_adapter",
    "validate_cookie_standalone",
    "build_llm",
    "workspace_root",
    "default_language",
    "problem_row_for",
]
