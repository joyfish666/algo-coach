"""FastAPI thin REST layer.

Stage 2 surface: status, setup cookie validation, settings read/update,
problem list cache, background sync with progress polling, daily problem,
problem workspace open/refresh, on-demand templates and custom testcases.

Layer rules:
- domain exceptions are translated to structured error JSON
- blocking network endpoints are plain def so they run in the thread pool
- Origin / Host guard middleware: state-changing methods require a whitelisted
  local origin (including the Vite dev origin http://localhost:5173); GET may
  omit Origin but the Host header must be local (DNS-rebinding protection)
"""

from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from urllib.parse import urlparse

import lc
from lc import auth, problems
from lc.config import effective_config, save as save_config, workspace_root_path
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
from lc.logutil import logger
from lc.sites.cn import LeetCodeCnAdapter

LOCAL_HOSTNAMES = ("127.0.0.1", "localhost", "::1")
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

app = FastAPI(title="AlgoCoach", version=lc.__version__)

_sync_engine = problems.SyncEngine()


def create_adapter() -> LeetCodeCnAdapter:
    client = auth.get_http_client()
    if client is None:
        raise HTTPException(status_code=400, detail=t("cookie_missing"))
    return LeetCodeCnAdapter(client=client)


def validate_cookie_standalone(cookie: str) -> dict:
    config = effective_config()
    session = auth.build_session(cookie)
    client = HttpClient(
        session,
        default_headers=dict(auth.DEFAULT_HEADERS),
        request_interval=min(float(config.get("request_interval", 2.0)), 1.0),
    )
    adapter = LeetCodeCnAdapter(client=client)
    return adapter.validate_cookie()


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
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


# ---------------------------------------------------------------------------
# status / setup / settings


@app.get("/api/status")
def get_status():
    config = effective_config()
    return {
        "app": "algocoach",
        "version": lc.__version__,
        "site": "leetcode.cn",
        "configured": bool(config.get("cookie")),
        "sync": _sync_engine.progress(),
    }


class CookiePayload(BaseModel):
    cookie: str


@app.post("/api/setup/validate-cookie")
def validate_cookie(payload: CookiePayload):
    profile = validate_cookie_standalone(payload.cookie)
    return {"ok": True, "profile": profile}


def mask_secret(value: str) -> str:
    value = value or ""
    if not value:
        return ""
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def masked_settings(config: dict) -> dict:
    return {
        "configured": bool(config.get("cookie")),
        "cookie_masked": mask_secret(config.get("cookie", "")),
        "csrf_token_masked": mask_secret(config.get("csrf_token", "")),
        "llm_api_key_masked": mask_secret(config.get("llm_api_key", "")),
        "llm_base_url": config.get("llm_base_url", ""),
        "llm_model": config.get("llm_model", ""),
        "default_language": config.get("default_language", DEFAULT_LANGUAGE),
        "ui_language": config.get("ui_language", ""),
        "theme": config.get("theme", "system"),
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
    default_language: str | None = None
    ui_language: str | None = None
    theme: str | None = None
    request_interval: float | None = None
    workspace_root: str | None = None


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate):
    provided = payload.model_fields_set
    config = effective_config()
    rebuild_needed = False

    updates = payload.model_dump(exclude_unset=True)
    if "cookie" in provided and updates.get("cookie") is not None:
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


# ---------------------------------------------------------------------------
# problem list + sync


@app.get("/api/problems")
def get_problems():
    payload = problems.load_problems()
    return {
        "total": payload.get("total", 0),
        "synced_at": payload.get("synced_at"),
        "problems": payload.get("problems", []),
    }


@app.post("/api/problems/sync")
def start_sync():
    adapter = create_adapter()
    started = _sync_engine.begin(adapter, cache_path=None)
    if not started:
        raise HTTPException(status_code=409, detail=t("sync_in_progress"))
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
        raise HTTPException(status_code=404, detail=t("problem_not_found"))

    state = problems.read_problem_state(directory, default_language=_default_lang())
    cache = problems.load_problems()
    row = next((p for p in cache["problems"] if p["slug"] == slug), {})
    state.update(row)
    state.setdefault("slug", slug)
    state["dir"] = directory.name
    state["path"] = str(directory)
    return state


def _default_lang() -> str:
    return effective_config().get("default_language", DEFAULT_LANGUAGE)


@app.get("/api/problem/{qid}")
def get_problem(qid: str, refresh: int = 0):
    return _open_or_refresh(qid, bool(refresh))


@app.get("/api/problem/{qid}/template")
def get_template(qid: str, lang: str = "cpp"):
    if not is_supported(lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {lang}")
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise HTTPException(status_code=404, detail=t("problem_not_found"))
    result = problems.ensure_template(
        directory,
        lang,
        detail_provider=lambda: create_adapter().fetch_question_detail(qid),
    )
    return {
        "slug": qid,
        "lang": lang,
        "status": result["status"],
        "code": result["path"].read_text(encoding="utf-8"),
    }


class TestcasesPayload(BaseModel):
    content: str


@app.put("/api/problem/{qid}/testcases")
def put_testcases(qid: str, payload: TestcasesPayload):
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise HTTPException(status_code=404, detail=t("problem_not_found"))
    problems.save_testcases(directory, payload.content)
    return {"slug": qid, "saved": True}
