"""FastAPI thin REST layer.

Stage 2 surface: status, setup cookie validation, settings read/update,
problem list cache, background sync with progress polling, daily problem,
problem workspace open/refresh, on-demand templates and custom testcases.

Layer rules:
- domain exceptions are translated to structured error JSON
- blocking network endpoints are plain def so they run in the thread pool
- Origin / Host guard middleware: state-changing methods require a whitelisted
  local origin (including the Vite dev origin http://localhost:5173); GET may
  omit Origin but the Host header must be local (DNS-rebinding protection);
  forced refresh lives on POST /api/problem/{qid}/refresh so GET never force-
  refetches; note GET still lazily materializes a not-yet-open problem (fetch
  once, then serve from disk) - that is documented behavior, not an accident
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from urllib.parse import urlparse

import lc
from lc import auth, favorites, judge, problems
from lc.archive import Archive, build_record, compute_stats, recommend_problems, tag_mastery
from lc.config import (
    LLM_TIMEOUT_MAX,
    LLM_TIMEOUT_MIN,
    REQUEST_INTERVAL_MAX,
    REQUEST_INTERVAL_MIN,
    effective_config,
    save as save_config,
    update_lock,
    workspace_root_path,
)
from lc.exceptions import (
    AlgoCoachError,
    AuthError,
    JudgeError,
    NetworkError,
    PremiumProblemError,
    ProblemNotFoundError,
    RateLimitError,
)
from lc.httpclient import HttpClient
from lc.i18n import t
from lc.langs import DEFAULT_LANGUAGE, is_supported
from lc.llm import LLMClient
from lc.logutil import logger
from lc.sites.cn import LeetCodeCnAdapter, classify_status_text

LOCAL_HOSTNAMES = ("127.0.0.1", "localhost", "::1")
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

_SAFE_QID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _require_safe_slug(qid: str) -> str:
    """Reject path-traversal payloads before they reach filesystem paths."""
    if not _SAFE_QID_RE.fullmatch(qid or ""):
        raise HTTPException(status_code=400, detail=f"invalid problem id: {qid!r}")
    return qid

app = FastAPI(title="AlgoCoach", version=lc.__version__)

_sync_engine = problems.SyncEngine()
_archive_lock = threading.Lock()
_archive: Archive | None = None
# Serializes the destructive data wipe against sync startup: without it a
# POST /api/problems/sync could slip in between clear's running-check and
# the directory deletion, leaving a half-rebuilt cache in a "cleared" dir.
_lifecycle_lock = threading.Lock()


def find_dist_dir() -> Path | None:
    """Locate the built frontend (web/dist).

    Resolution chain: ALGOCOACH_DIST env override -> repository layout
    (editable installs / source checkout, searched upward from this file) ->
    packaged copy inside the installed server package. None means API-only
    mode; the dev flow serves the UI through Vite instead.
    """
    env = os.environ.get("ALGOCOACH_DIST")
    if env and (Path(env) / "index.html").is_file():
        return Path(env)

    here = Path(__file__).resolve().parent
    for base in [here.parent, *here.parents[:4]]:
        candidate = base / "web" / "dist" / "index.html"
        if candidate.is_file():
            return candidate.parent

    packaged = here / "webdist"
    if (packaged / "index.html").is_file():
        return packaged
    return None


DIST_DIR = find_dist_dir()


def get_archive() -> Archive:
    global _archive
    with _archive_lock:
        if _archive is None:
            from lc.config import archive_path

            _archive = Archive(archive_path())
        return _archive


def reset_app_state() -> None:
    """Drop lazily-built process singletons.

    Exists so embedders/tests can re-isolate the module after the data
    directory changes; clear_local_data uses the same dance inline. The sync
    engine is reset here too: it is a module-level singleton whose run state
    (running flag, accumulated rows) would otherwise leak an in-flight or
    failed run across a data-directory swap.
    """
    global _archive
    with _archive_lock:
        _archive = None
    _sync_engine.reset()


def create_adapter() -> LeetCodeCnAdapter:
    client = auth.get_http_client()
    if client is None:
        config = effective_config()
        cookie = str(config.get("cookie", "") or "")
        if not cookie:
            raise http_domain_error(400, "cookie_missing")
        client = auth.configure(cookie, request_interval=config["request_interval"])
    return LeetCodeCnAdapter(client=client)


def validate_cookie_standalone(cookie: str) -> dict:
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


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    host_header = request.headers.get("host") or ""
    # urlparse("//[::1]:8000").hostname -> "::1"; handles bracketed IPv6
    host = (urlparse(f"//{host_header}").hostname or "").lower()
    if host not in LOCAL_HOSTNAMES:
        return JSONResponse(
            status_code=403,
            content={"error": {"kind": "ForbiddenHost", "message_key": "network_error",
                               "message": "host not allowed"}},
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if not origin:
            return JSONResponse(
                status_code=403,
                content={"error": {"kind": "MissingOrigin", "message_key": "network_error",
                                   "message": "origin required for state-changing requests"}},
            )
        parsed = urlparse(origin)
        allowed = (
            origin in DEV_ORIGINS
            or (parsed.hostname or "").lower() in LOCAL_HOSTNAMES
        )
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"error": {"kind": "ForbiddenOrigin", "message_key": "network_error",
                                   "message": "origin not allowed"}},
            )
    return await call_next(request)


_STATUS_BY_EXCEPTION = {
    RateLimitError: 429,
    AuthError: 401,
    PremiumProblemError: 403,
    ProblemNotFoundError: 404,
    NetworkError: 502,
    JudgeError: 502,
}


def _status_for(exc: AlgoCoachError) -> int:
    for cls in type(exc).__mro__:
        if cls in _STATUS_BY_EXCEPTION:
            return _STATUS_BY_EXCEPTION[cls]
    return 400


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


@app.exception_handler(AlgoCoachError)
async def domain_error_handler(request: Request, exc: AlgoCoachError):
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(int(retry_after))} if retry_after else None
    return JSONResponse(
        status_code=_status_for(exc),
        content={
            "error": {
                "kind": type(exc).__name__,
                "message_key": exc.message_key,
                "message": str(exc),
                "detail": exc.detail,
            }
        },
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled error on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "kind": type(exc).__name__,
                "message_key": "network_error",
                "message": f"{type(exc).__name__}: {exc}",
            }
        },
    )


# ---------------------------------------------------------------------------
# status / setup / settings


@app.get("/api/status")
def get_status():
    config = effective_config()
    from lc.config import app_dir

    return {
        "app": "algocoach",
        "version": lc.__version__,
        "site": "leetcode.cn",
        "configured": bool(config.get("cookie")),
        # lets the AI coach sidebar gate on LLM availability the same way the
        # analytics page does, instead of only failing after a send
        "llm_configured": bool(config.get("llm_api_key"))
        and bool(config.get("llm_base_url")),
        "data_dir": str(app_dir()),
        "sync": _sync_engine.progress(),
    }


class CookiePayload(BaseModel):
    cookie: str


@app.post("/api/setup/validate-cookie")
def validate_cookie(payload: CookiePayload):
    profile = validate_cookie_standalone(payload.cookie)
    return {"ok": True, "profile": profile}


def mask_secret(value: str) -> str:
    """Reveal only the tail: even a short prefix of a session token aids
    correlation attacks, so nothing but the last 4 chars is ever returned.
    Secrets shorter than 16 chars stay fully masked - on those the tail
    alone would expose too large a fraction of the entropy."""
    value = value or ""
    if not value:
        return ""
    if len(value) < 16:
        return "***"
    return f"…{value[-4:]}"


def masked_settings(config: dict) -> dict:
    return {
        "configured": bool(config.get("cookie")),
        "cookie_masked": mask_secret(config.get("cookie", "")),
        "csrf_token_masked": mask_secret(config.get("csrf_token", "")),
        "llm_api_key_masked": mask_secret(config.get("llm_api_key", "")),
        "llm_base_url": config.get("llm_base_url", ""),
        "llm_model": config.get("llm_model", ""),
        "llm_thinking": config.get("llm_thinking", "default"),
        "llm_timeout": config.get("llm_timeout", 120.0),
        "default_language": config.get("default_language", DEFAULT_LANGUAGE),
        "request_interval": config.get("request_interval", 2.0),
        "workspace_root": config.get("workspace_root", ""),
    }


@app.get("/api/settings")
def read_settings():
    return masked_settings(effective_config())


class SettingsUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    cookie: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_thinking: str | None = None
    llm_timeout: float | None = None
    default_language: str | None = None
    request_interval: float | None = None
    workspace_root: str | None = None


# Range policy lives in lc.config (RANGE_LIMITS) so every write door -
# settings API, env overrides, config file tooling - enforces the same
# bounds. The API still rejects (not clamps) so typos fail loudly.


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate):
    # the whole read→validate→mutate→save sequence holds the config update
    # lock: a cookie rotation persisting concurrently used to write its stale
    # whole-file snapshot afterwards and silently revert this save (including
    # resurrecting the pre-save cookie). rebuild() deliberately happens after
    # the lock is released - it acquires auth's persist lock, and no path may
    # take that lock while holding the config lock.
    with update_lock():
        config = effective_config()
        provided = payload.model_fields_set
        rebuild_needed = False

        updates = payload.model_dump(exclude_unset=True)
        # one uniform rule for every field: an explicit null is a client bug
        # (omitting the field already means "keep current value"). Letting nulls
        # through used to mean a TypeError 500 for numeric fields and - worse -
        # the string "None" silently written into config.toml for text fields.
        null_fields = sorted(key for key, value in updates.items() if value is None)
        if null_fields:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"field(s) {', '.join(null_fields)} cannot be null; "
                    "omit them to keep the current value"
                ),
            )
        if "request_interval" in updates:
            interval = float(updates["request_interval"])
            if not REQUEST_INTERVAL_MIN <= interval <= REQUEST_INTERVAL_MAX:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"request_interval out of range "
                        f"[{REQUEST_INTERVAL_MIN}, {REQUEST_INTERVAL_MAX}]: {interval}"
                    ),
                )
        if "llm_timeout" in updates:
            timeout = float(updates["llm_timeout"])
            if not LLM_TIMEOUT_MIN <= timeout <= LLM_TIMEOUT_MAX:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"llm_timeout out of range "
                        f"[{LLM_TIMEOUT_MIN}, {LLM_TIMEOUT_MAX}]: {timeout}"
                    ),
                )
        if "llm_thinking" in updates:
            from lc.llm import THINKING_LEVELS

            if updates["llm_thinking"] not in ("default", *THINKING_LEVELS):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "llm_thinking must be one of: default, "
                        + ", ".join(THINKING_LEVELS)
                        + f"; got {updates['llm_thinking']!r}"
                    ),
                )
        if "cookie" in provided:
            from lc.auth import extract_csrf_token

            config["cookie"] = updates["cookie"]
            config["csrf_token"] = extract_csrf_token(updates["cookie"])
            rebuild_needed = True
        config.update({key: value for key, value in updates.items() if key != "cookie"})

        if "default_language" in updates and not is_supported(updates["default_language"]):
            raise HTTPException(
                status_code=422,
                detail=f"unsupported language: {updates['default_language']}",
            )

        save_config(config)
    if rebuild_needed:
        auth.rebuild(config["cookie"], request_interval=config["request_interval"])
    logger.info("settings updated (fields=%s)", sorted(provided))
    return masked_settings(effective_config())


class LlmTestPayload(BaseModel):
    model_config = {"extra": "forbid"}

    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_thinking: str | None = None


# A probe must feel snappy even when the saved llm_timeout is generous; 30s
# still clears slow cold-start endpoints but never hangs the settings page.
LLM_TEST_TIMEOUT_CAP = 30.0


@app.post("/api/llm/test")
def test_llm_endpoint(payload: LlmTestPayload):
    """One-shot LLM connectivity probe.

    Fields provided in the payload override the saved config, so the settings
    form can verify what the user just typed before saving; omitted fields
    fall back to the saved values. Uses a tiny max_tokens cap to keep the
    probe cheap.
    """
    config = effective_config()
    updates = payload.model_dump(exclude_unset=True)
    api_key = str(updates.get("llm_api_key", "") or config.get("llm_api_key", "") or "")
    base_url = str(updates.get("llm_base_url", "") or config.get("llm_base_url", "") or "")
    model = str(
        updates.get("llm_model", "") or config.get("llm_model", "") or "deepseek-v4-flash"
    )
    thinking = str(
        updates.get("llm_thinking", "") or config.get("llm_thinking", "") or "default"
    )
    if not api_key or not base_url:
        raise http_domain_error(400, "ask_not_configured")
    timeout = min(float(config.get("llm_timeout", 120.0)), LLM_TEST_TIMEOUT_CAP)
    llm = LLMClient(
        base_url=base_url, api_key=api_key, model=model, timeout=timeout, thinking=thinking
    )
    reply = llm.chat([{"role": "user", "content": "ping"}], max_tokens=8)
    return {"ok": True, "model": llm.model, "reply": reply[:80]}


# ---------------------------------------------------------------------------
# problem list + sync


@app.get("/api/problems")
def get_problems():
    payload = problems.load_problems()
    latest = get_archive().latest_by_slug()
    favorite_slugs = favorites.load_favorites()
    rows = []
    for row in payload.get("problems", []):
        verdict = latest.get(row.get("slug"))
        if verdict:
            row = {
                **row,
                "practice_status": verdict.get("status"),
                "last_practice_at": verdict.get("timestamp"),
            }
        if row.get("slug") in favorite_slugs:
            row = {**row, "favorite": True}
        rows.append(row)
    return {
        "total": payload.get("total", 0),
        "synced_at": payload.get("synced_at"),
        "problems": rows,
    }


@app.post("/api/problems/sync")
def start_sync():
    adapter = create_adapter()
    with _lifecycle_lock:
        started = _sync_engine.begin(adapter, cache_path=None)
    if not started:
        raise http_domain_error(409, "sync_in_progress")
    return {"started": True, "progress": _sync_engine.progress()}


@app.get("/api/problems/sync/progress")
def sync_progress():
    return _sync_engine.progress()


# ---------------------------------------------------------------------------
# daily / problem workspace


@app.get("/api/daily")
def get_daily():
    return create_adapter().fetch_daily_question()


def _workspace_root() -> object:
    return workspace_root_path(effective_config())


def _open_or_refresh(slug: str, refresh: bool) -> dict:
    adapter = create_adapter()
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, slug)
    need_fetch = refresh or directory is None

    detail = None
    if need_fetch:
        detail = adapter.fetch_question_detail(slug)
        summary = problems.summary_from_detail(detail)
        if refresh and directory is not None:
            result = problems.refresh_problem(directory, detail, default_language=_default_lang())
            logger.info("refreshed %s backups=%s", slug, result["backups"])
        else:
            directory = problems.open_problem(detail, workspace, default_language=_default_lang())
        problems.upsert_summary_into_cache(summary)

    if directory is None:
        raise http_domain_error(404, "problem_not_found")

    if not need_fetch and not problems.statement_up_to_date(directory):
        # statement.md is regenerable converter output; a stored workspace
        # written by an older converter renders literal "**" garbage, so it
        # is refreshed once from the site. Offline or site-side failure
        # degrades to the stored file - offline review keeps working.
        try:
            detail = adapter.fetch_question_detail(slug)
            problems.regenerate_statement(directory, detail)
            logger.info(
                "regenerated statement.md for %s (converter v%d)",
                slug,
                problems.STATEMENT_VERSION,
            )
        except (AlgoCoachError, OSError) as exc:
            logger.warning("statement regeneration skipped for %s: %s", slug, exc)

    state = problems.read_problem_state(directory, default_language=_default_lang())
    cache = problems.load_problems()
    row = next((p for p in cache["problems"] if p["slug"] == slug), {})
    state.update(row)
    state.setdefault("slug", slug)
    state["dir"] = directory.name
    state["path"] = str(directory)
    state["favorite"] = favorites.is_favorite(slug)
    return state


def _default_lang() -> str:
    return effective_config().get("default_language", DEFAULT_LANGUAGE)


@app.get("/api/problem/{qid}")
def get_problem(qid: str):
    _require_safe_slug(qid)
    return _open_or_refresh(qid, False)


@app.post("/api/problem/{qid}/refresh")
def refresh_problem(qid: str):
    """Force a remote refetch; POST so the side effect cannot ride on GET."""
    _require_safe_slug(qid)
    return _open_or_refresh(qid, True)


@app.get("/api/problem/{qid}/template")
def get_template(qid: str, lang: str | None = None):
    # default comes from config like everywhere else, not a hardcoded cpp:
    # a python3-default user hitting this route without ?lang= must not get
    # C++ semantics
    lang = lang or _default_lang()
    _require_safe_slug(qid)
    if not is_supported(lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {lang}")
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    result = problems.ensure_template(
        directory,
        lang,
        detail_provider=lambda: create_adapter().fetch_question_detail(qid),
    )
    try:
        code = result["path"].read_text(encoding="utf-8")
    except OSError:
        # same transient-read degrade policy as the workspace state reads; a
        # Windows sharing violation on a file we just wrote must not 500
        code = ""
    return {
        "slug": qid,
        "lang": lang,
        "status": result["status"],
        "code": code,
    }


class TestcasesPayload(BaseModel):
    content: str


@app.put("/api/problem/{qid}/testcases")
def put_testcases(qid: str, payload: TestcasesPayload):
    _require_safe_slug(qid)
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    problems.save_testcases(directory, payload.content)
    return {"slug": qid, "saved": True}


class SolutionPayload(BaseModel):
    lang: str
    code: str


@app.put("/api/problem/{qid}/solution")
def put_solution(qid: str, payload: SolutionPayload):
    _require_safe_slug(qid)
    if not is_supported(payload.lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {payload.lang}")
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    path = problems.save_solution(directory, payload.lang, payload.code)
    return {"slug": qid, "lang": payload.lang, "saved": True, "mtime": path.stat().st_mtime}


class NotesPayload(BaseModel):
    content: str


@app.put("/api/problem/{qid}/notes")
def put_notes(qid: str, payload: NotesPayload):
    _require_safe_slug(qid)
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    problems.save_notes(directory, payload.content)
    return {"slug": qid, "saved": True}


class FavoritePayload(BaseModel):
    favorite: bool


@app.put("/api/problem/{qid}/favorite")
def put_favorite(qid: str, payload: FavoritePayload):
    """Toggle the list-level favorite flag for one problem."""
    _require_safe_slug(qid)
    state = favorites.set_favorite(qid, bool(payload.favorite))
    logger.info("favorite %s -> %s", qid, state)
    return {"slug": qid, "favorite": state}


def _problem_row_for(slug: str, adapter=None, cache_rows=None) -> dict:
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


def _archive_verdict(
    slug: str, lang: str, verdict: dict, adapter=None, cache_rows=None
) -> dict:
    row = _problem_row_for(slug, adapter=adapter, cache_rows=cache_rows)
    record = build_record(
        slug=slug,
        frontend_id=row.get("frontend_id", ""),
        submission_id=verdict.get("submission_id", ""),
        lang=lang,
        verdict=verdict,
        problem_row=row,
    )
    get_archive().append(record)
    return record


def _resolve_judge_context(slug: str) -> tuple:
    """Resolve (directory, question_id, frontend_row, cache_rows) in one pass.

    The problem cache is read exactly once here; the submit path reuses
    cache_rows for archiving instead of hitting the disk again.
    """
    _require_safe_slug(slug)
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, slug)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    meta = problems.load_meta(directory)
    question_id = str(meta.get("internal_question_id", "") or "")
    cache_rows = problems.load_problems()["problems"]
    frontend_row = next((p for p in cache_rows if p.get("slug") == slug), {})
    if not question_id:
        detail = create_adapter().fetch_question_detail(slug)
        question_id = str(detail.get("internal_question_id", "") or "")
    # last-resort fallback is the numeric frontend id; falling back to the
    # slug used to ship a guaranteed-to-fail submit that surfaced as an
    # opaque site-side error wrapped in a 502 - fail loudly instead
    question_id = question_id or str(frontend_row.get("frontend_id", "") or "")
    if not question_id:
        raise http_domain_error(422, "judge_missing_question_id")
    return (
        directory,
        question_id,
        frontend_row,
        cache_rows,
    )


class JudgeRunPayload(BaseModel):
    qid: str
    lang: str
    code: str
    use_local: bool = False


@app.post("/api/judge/run")
def judge_run_endpoint(payload: JudgeRunPayload):
    if not is_supported(payload.lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {payload.lang}")
    directory, question_id, _frontend_row, _cache_rows = _resolve_judge_context(payload.qid)

    if payload.use_local:
        testcases_path = directory / "testcases.txt"
        try:
            input_text = (
                testcases_path.read_text(encoding="utf-8")
                if testcases_path.exists()
                else ""
            )
        except OSError:
            # same policy as the cases.json branch: the file may vanish
            # between exists() and read; degrade to empty instead of 500
            input_text = ""
    else:
        # every stored official case participates in a remote run; the site
        # expects all case inputs newline-concatenated under data_input
        cases_path = directory / "cases.json"
        inputs = []
        if cases_path.exists():
            try:
                cases = json.loads(cases_path.read_text(encoding="utf-8")).get("cases", [])
                for case in cases:
                    inputs.extend(case.get("inputs") or [])
            except (json.JSONDecodeError, OSError):
                inputs = []
        input_text = "\n".join(inputs)

    problems.save_solution(directory, payload.lang, payload.code)
    verdict = judge.judge_run(
        create_adapter(),
        slug=payload.qid,
        question_id=question_id,
        code=payload.code,
        lang=payload.lang,
        input_text=input_text,
    )
    verdict["mode"] = "run"
    verdict["input"] = input_text
    return verdict


class JudgeSubmitPayload(BaseModel):
    qid: str
    lang: str
    code: str


@app.post("/api/judge/submit")
def judge_submit_endpoint(payload: JudgeSubmitPayload):
    if not is_supported(payload.lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {payload.lang}")
    directory, question_id, _frontend_row, cache_rows = _resolve_judge_context(payload.qid)
    problems.save_solution(directory, payload.lang, payload.code)
    adapter = create_adapter()
    verdict = judge.judge_submit(
        adapter,
        slug=payload.qid,
        question_id=question_id,
        code=payload.code,
        lang=payload.lang,
    )
    verdict["mode"] = "submit"
    try:
        _archive_verdict(
            payload.qid, payload.lang, verdict, adapter=adapter, cache_rows=cache_rows
        )
        verdict["archived"] = True
    except OSError as exc:
        # the submit itself succeeded and cannot be replayed - a local disk
        # failure (full, locked by backup software) used to surface as a 500
        # and invited a duplicate resubmission just to see the verdict again.
        # Degrade like every other persist failure and tell the client.
        logger.exception("archiving submit verdict failed: %s", exc)
        verdict["archived"] = False
    return verdict


def _build_llm() -> LLMClient:
    config = effective_config()
    api_key = str(config.get("llm_api_key", "") or "")
    base_url = str(config.get("llm_base_url", "") or "")
    if not api_key or not base_url:
        raise http_domain_error(400, "ask_not_configured")
    return LLMClient(
        base_url=base_url,
        api_key=api_key,
        model=str(config.get("llm_model", "") or "deepseek-v4-flash"),
        timeout=float(config.get("llm_timeout", 120.0)),
        thinking=str(config.get("llm_thinking", "") or "default"),
    )


# The coach replies in the UI language: the app ships a bilingual interface,
# but the prompt was a hardcoded Chinese constant, so an en-locale user asking
# in English always got a Chinese answer. The frontend i18n store sends its
# language as ui_lang; unknown values fall back to zh (the historical
# behavior, also the language every stored statement is written in).
COACH_SYSTEM_PROMPTS = {
    "zh": (
        "你是 AlgoCoach，一位耐心的算法学习教练。用简体中文回答：先给思路要点，"
        "再给复杂度分析；用户要求代码时给关键实现即可。若提供了题目与判定上下文，"
        "结合它们作答；没有则按通用算法问题处理。"
    ),
    "en": (
        "You are AlgoCoach, a patient algorithm learning coach. Answer in English: "
        "give the key ideas first, then the complexity analysis; when the user asks "
        "for code, provide only the essential implementation. Use the problem and "
        "verdict context when provided; otherwise treat the question as a general "
        "algorithm question. Quoted problem statements may be in Chinese - keep "
        "those quotes as they are."
    ),
}


def normalize_ui_lang(ui_lang) -> str:
    return ui_lang if ui_lang in COACH_SYSTEM_PROMPTS else "zh"


def coach_system_prompt(ui_lang: str) -> str:
    return COACH_SYSTEM_PROMPTS[ui_lang]


class AskPayload(BaseModel):
    question: str
    history: list = []
    qid: str | None = None
    code: str | None = None
    lang: str | None = None
    ui_lang: str | None = None


def _ask_context_parts(payload: AskPayload, ui_lang: str) -> list:
    """Coach context lines phrased in the reply language.

    Mixing a Chinese prompt with English context (or vice versa) taught the
    model to answer in the wrong language; one locale per system prompt keeps
    the reply stable. Tag/title preference follows the language too.
    """
    parts = []
    row = {}
    if payload.qid:
        row = _problem_row_for(payload.qid)
    if row:
        if ui_lang == "en":
            tags = ", ".join(
                (tag.get("name_en") or tag.get("name_zh") or "")
                for tag in (row.get("tags") or [])[:6]
            )
            parts.append(
                f"Current problem: {row.get('frontend_id', '')} "
                f"{row.get('title_en', '') or row.get('title_cn', '')}"
                f" (difficulty {row.get('difficulty', '?')}, tags {tags or 'none'})"
            )
        else:
            tags = "、".join(
                (tag.get("name_zh") or tag.get("name_en") or "") for tag in (row.get("tags") or [])[:6]
            )
            parts.append(
                f"当前题目: {row.get('frontend_id', '')} {row.get('title_cn', '') or row.get('title_en', '')}"
                f"（难度 {row.get('difficulty', '?')}，标签 {tags or '无'}）"
            )
        verdict = get_archive().latest_by_slug().get(payload.qid)
        if verdict:
            passed = f"{verdict.get('total_correct', '?')}/{verdict.get('total_testcases', '?')}"
            runtime = verdict.get("runtime_display") or "—"
            memory = verdict.get("memory_display") or "—"
            if ui_lang == "en":
                parts.append(
                    f"Last verdict: {verdict.get('status', 'unknown')}, cases passed {passed}, "
                    f"runtime {runtime}, memory {memory}"
                )
            else:
                parts.append(
                    f"上次判定: {verdict.get('status', 'unknown')}，通过用例 {passed}，"
                    f"用时 {runtime}，内存 {memory}"
                )

    # editor code is opt-in: the user attaches it explicitly per question so a
    # long solution is not shipped to the LLM on every casual ask
    if payload.code and payload.code.strip():
        lang_label = payload.lang or "text"
        snippet = payload.code[:6000]
        label = f"Current code ({lang_label}):" if ui_lang == "en" else f"当前代码（{lang_label}）:"
        parts.append(f"{label}\n```\n{snippet}\n```")
    return parts


@app.post("/api/ask")
def ask_endpoint(payload: AskPayload):
    llm = _build_llm()
    ui_lang = normalize_ui_lang(payload.ui_lang)
    context_parts = _ask_context_parts(payload, ui_lang)

    system_prompt = coach_system_prompt(ui_lang)
    if context_parts:
        header = "Context:" if ui_lang == "en" else "参考上下文:"
        system_prompt += f"\n\n{header}\n" + "\n".join(context_parts)

    messages = [{"role": "system", "content": system_prompt}]
    for item in (payload.history or [])[-12:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])[:4000]})
    messages.append({"role": "user", "content": payload.question})

    answer = llm.chat(messages)
    return {"answer": answer, "model": llm.model}


class AnalyzePayload(BaseModel):
    use_llm: bool = True
    limit: int = 100
    ui_lang: str | None = None


def _analyze_digest(stats: dict, weak_tags: list, recommendations: list, ui_lang: str) -> tuple:
    """Data digest + instruction + user turn for the AI report, in one language.

    The report prompt was Chinese-only while the app ships an en locale; an
    English report needs the digest, the instruction and the user turn all in
    English or the model answers in Chinese anyway.
    """
    by_difficulty = stats["by_difficulty"]
    if ui_lang == "en":
        digest_lines = [
            f"- Solved {stats['solved_total']} problems "
            f"(Easy {by_difficulty['easy']} / Medium {by_difficulty['medium']} / "
            f"Hard {by_difficulty['hard']}), {stats['attempts_total']} attempts in total"
        ]
        if weak_tags:
            weak_text = ", ".join(
                f"{item['name_en']} ({int(item['mastered'] * 100)}% mastery)"
                for item in weak_tags[:5]
            )
            digest_lines.append(f"- Weak tags: {weak_text}")
        if recommendations:
            rec_text = ", ".join(
                f"{row.get('frontend_id', '')} {row.get('title_en', '') or row.get('title_cn', '')}"
                for row in recommendations
            )
            digest_lines.append(f"- Recommended practice candidates: {rec_text}")
        instruction = (
            "\n\nBased on the local practice data below, write a short weakness "
            "analysis and a practice plan for next week (under 150 words). Data:\n"
        )
        user_turn = "Please generate my learning report."
        return "\n".join(digest_lines), instruction, user_turn

    digest_lines = [
        f"- 解出 {stats['solved_total']} 题"
        f"（Easy {by_difficulty['easy']} / Medium {by_difficulty['medium']}"
        f" / Hard {by_difficulty['hard']}），累计尝试 {stats['attempts_total']} 次"
    ]
    if weak_tags:
        weak_text = ", ".join(
            f"{item['name_zh']}(掌握 {int(item['mastered'] * 100)}%)" for item in weak_tags[:5]
        )
        digest_lines.append(f"- 薄弱标签: {weak_text}")
    if recommendations:
        rec_text = ", ".join(
            f"{row.get('frontend_id','')} {row.get('title_cn','')}" for row in recommendations
        )
        digest_lines.append(f"- 推荐练习候选: {rec_text}")
    instruction = (
        "\n\n现在请基于以下本地练习数据，写一份简短的薄弱点分析与下周练习建议（150字内）。"
        "数据:\n"
    )
    user_turn = "请生成我的学习报告。"
    return "\n".join(digest_lines), instruction, user_turn


@app.post("/api/analyze")
def analyze_endpoint(payload: AnalyzePayload):
    archive = get_archive()
    latest_index = archive.latest_by_slug()
    stats = compute_stats(latest_index)
    stats["attempts_total"] = archive.attempts_total()
    tags = tag_mastery(latest_index)
    weak_tags = [item for item in tags if item["attempted"] > 0][:10]
    recommendations = recommend_problems(problems.load_problems()["problems"], latest_index, weak_tags)

    ai_report = None
    # availability must be computed from config up front: the initial page
    # load passes use_llm=false, and gating ai_configured on that flag used
    # to report "LLM not configured" even with a perfectly saved key
    config = effective_config()
    ai_configured = bool(config.get("llm_api_key")) and bool(config.get("llm_base_url"))
    if payload.use_llm:
        try:
            llm = _build_llm()
            ai_configured = True
            ui_lang = normalize_ui_lang(payload.ui_lang)
            digest, instruction, user_turn = _analyze_digest(
                stats, weak_tags, recommendations, ui_lang
            )
            report_messages = [
                {
                    "role": "system",
                    "content": coach_system_prompt(ui_lang) + instruction + digest,
                },
                {"role": "user", "content": user_turn},
            ]
            ai_report = llm.chat(report_messages)
        except HTTPException:
            ai_configured = False
        except AlgoCoachError as exc:
            logger.warning("analyze AI report failed: %s", exc)
            ai_report = None

    return {
        "stats": stats,
        "tags": tags,
        "recommendations": recommendations,
        "ai_report": ai_report,
        "ai_configured": ai_configured,
    }


@app.get("/api/archive/recent")
def archive_recent(limit: int = 50, qid: str | None = None):
    capped = max(1, min(int(limit), 200))
    slug = qid or None
    if slug:
        _require_safe_slug(slug)
    return {"records": get_archive().query(slug=slug, limit=capped)}


class ImportSitePayload(BaseModel):
    limit: int = 20


@app.post("/api/archive/import-site")
def import_site(payload: ImportSitePayload):
    adapter = create_adapter()
    items = adapter.fetch_recent_submissions(min(max(1, int(payload.limit)), 20))
    cache_rows = problems.load_problems()["problems"]
    by_slug = {row.get("slug"): row for row in cache_rows}

    imported = 0
    skipped = 0
    records = []
    for item in items:
        if not item.get("submission_id") or get_archive().has_submission(item["submission_id"]):
            skipped += 1
            continue
        row = by_slug.get(item["slug"], {})
        if not row and item.get("frontend_id"):
            row = {"frontend_id": item["frontend_id"], "title_cn": item.get("title_cn", "")}
        record = build_record(
            slug=item["slug"],
            frontend_id=row.get("frontend_id", item.get("frontend_id", "")),
            submission_id=item["submission_id"],
            lang=item.get("lang", ""),
            # same classifier as judge results; unmatched text lands on
            # "other" so it stays visible but never inflates solved stats
            verdict={"status_key": classify_status_text(item.get("status")) or "other"},
            problem_row=row,
        )
        if item.get("timestamp", "").isdigit():
            record["timestamp"] = datetime.fromtimestamp(
                int(item["timestamp"]), tz=timezone.utc
            ).isoformat(timespec="seconds")
        records.append(record)

    # the site feed is newest-first, but Archive.query derives its
    # newest-first listing from file append order: append oldest-first so the
    # batch lands in true chronological position (ISO UTC strings sort
    # lexically - both write paths stamp the same format)
    records.sort(key=lambda record: str(record.get("timestamp", "")))
    for record in records:
        get_archive().append(record)
        imported += 1

    result = {"imported": imported, "skipped": skipped}
    logger.info("site import: %s", result)
    return result


@app.delete("/api/local-data")
def clear_local_data():
    """Erase everything under the data directory except the live lock file.

    Removes problem cache, submission archive, workspace files and config
    (cookie included); auth singletons are reset so the app returns to the
    unconfigured state immediately.
    """
    if _sync_engine.progress()["running"]:
        raise http_domain_error(409, "sync_in_progress")

    from lc.config import INSTANCE_LOCK_NAME, app_dir

    # hold the same lock start_sync uses: either begin() wins and the
    # running-check above sees it (409), or this wipe completes first and
    # the later sync starts fresh on an empty directory - no interleaving
    with _lifecycle_lock:
        # auth reset comes FIRST, inside the wipe: an in-flight rotation
        # persist must fail its still-current check instead of winning the
        # config lock race and resurrecting the erased cookie into a fresh
        # config.toml after the directory was declared clean
        auth.reset_state()
        root = app_dir()
        cleared = []
        # the config update lock keeps a concurrent settings save or rotation
        # persist from interleaving with the deletion of config.toml
        with update_lock():
            if root.exists():
                keep = {INSTANCE_LOCK_NAME}
                for entry in sorted(root.iterdir()):
                    if entry.name in keep:
                        continue
                    try:
                        if entry.is_dir():
                            import shutil

                            shutil.rmtree(entry)
                        else:
                            entry.unlink()
                        cleared.append(entry.name)
                    except OSError as exc:
                        logger.warning("could not remove %s: %s", entry, exc)

        reset_app_state()
    logger.info("local data cleared: %s", cleared)
    return {"cleared": cleared, "data_dir": str(root)}


# ---------------------------------------------------------------------------
# built-frontend hosting + SPA fallback (registered last on purpose)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        # generic not-found: this fallback only sees paths no route matched,
        # which is a client typo, not a missing problem
        raise HTTPException(status_code=404, detail="not found")

    if DIST_DIR is not None:
        dist_root = DIST_DIR.resolve()
        served = None
        if full_path:
            candidate = (dist_root / full_path.lstrip("/")).resolve()
            try:
                candidate.relative_to(dist_root)
                inside = True
            except ValueError:
                inside = False
            if inside and candidate.is_file():
                served = candidate
        if served is not None:
            immutable = "/assets/" in full_path
            return FileResponse(
                served,
                headers={
                    "Cache-Control": (
                        "public, max-age=31536000, immutable"
                        if immutable
                        else "no-cache"
                    )
                },
            )
        last_segment = full_path.rstrip("/").rsplit("/", 1)[-1]
        if "." in last_segment:
            # asset-shaped misses (a hashed chunk from before a redeploy)
            # must 404: rewriting them to index.html answered a JS request
            # with HTML, and the browser reported an opaque MIME error while
            # every navigation from the stale tab silently died
            raise HTTPException(status_code=404, detail="not found")
        index = dist_root / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    if not full_path:
        return JSONResponse(
            {
                "app": f"AlgoCoach v{lc.__version__}",
                "hint": "frontend not built; run `cd web && npm run build` or use Vite dev mode",
                "endpoints": [
                    "/api/status",
                    "/api/settings",
                    "/api/problems",
                    "/api/problems/sync/progress",
                    "/api/daily",
                ],
            }
        )
    raise HTTPException(status_code=404, detail="not found")
