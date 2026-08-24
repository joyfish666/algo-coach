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
from lc import auth, judge, problems
from lc.archive import Archive, build_record, compute_stats, recommend_problems, tag_mastery
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
    directory changes; clear_local_data uses the same dance inline.
    """
    global _archive
    with _archive_lock:
        _archive = None


def create_adapter() -> LeetCodeCnAdapter:
    client = auth.get_http_client()
    if client is None:
        config = effective_config()
        cookie = str(config.get("cookie", "") or "")
        if not cookie:
            raise HTTPException(status_code=400, detail=t("cookie_missing"))
        client = auth.configure(cookie, request_interval=config["request_interval"])
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
    correlation attacks, so nothing but the last 4 chars is ever returned."""
    value = value or ""
    if not value:
        return ""
    if len(value) <= 8:
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
    default_language: str | None = None
    request_interval: float | None = None
    workspace_root: str | None = None


# Politeness bounds for the leetcode.cn rate limiter: below 0.5s the pacing
# gate is effectively off (risking site-side throttling/bans), above 60s a
# full sync would take hours. Values outside are rejected, not clamped, so
# typos fail loudly instead of silently reconfiguring the limiter.
REQUEST_INTERVAL_MIN = 0.5
REQUEST_INTERVAL_MAX = 60.0


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate):
    provided = payload.model_fields_set
    config = effective_config()
    rebuild_needed = False

    updates = payload.model_dump(exclude_unset=True)
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
    latest = get_archive().latest_by_slug()
    rows = []
    for row in payload.get("problems", []):
        verdict = latest.get(row.get("slug"))
        if verdict:
            row = {
                **row,
                "practice_status": verdict.get("status"),
                "last_practice_at": verdict.get("timestamp"),
            }
        rows.append(row)
    return {
        "total": payload.get("total", 0),
        "synced_at": payload.get("synced_at"),
        "problems": rows,
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
def get_problem(qid: str):
    _require_safe_slug(qid)
    return _open_or_refresh(qid, False)


@app.post("/api/problem/{qid}/refresh")
def refresh_problem(qid: str):
    """Force a remote refetch; POST so the side effect cannot ride on GET."""
    _require_safe_slug(qid)
    return _open_or_refresh(qid, True)


@app.get("/api/problem/{qid}/template")
def get_template(qid: str, lang: str = "cpp"):
    _require_safe_slug(qid)
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
    _require_safe_slug(qid)
    workspace = _workspace_root()
    directory = problems.find_problem_dir(workspace, qid)
    if directory is None:
        raise HTTPException(status_code=404, detail=t("problem_not_found"))
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
        raise HTTPException(status_code=404, detail=t("problem_not_found"))
    path = problems.save_solution(directory, payload.lang, payload.code)
    return {"slug": qid, "lang": payload.lang, "saved": True, "mtime": path.stat().st_mtime}


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
        raise HTTPException(status_code=404, detail=t("problem_not_found"))
    meta = problems.load_meta(directory)
    question_id = str(meta.get("internal_question_id", "") or "")
    cache_rows = problems.load_problems()["problems"]
    frontend_row = next((p for p in cache_rows if p.get("slug") == slug), {})
    if not question_id:
        detail = create_adapter().fetch_question_detail(slug)
        question_id = str(detail.get("internal_question_id", "") or "")
    return (
        directory,
        question_id or str(frontend_row.get("frontend_id", "") or "") or slug,
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
        input_text = (
            testcases_path.read_text(encoding="utf-8") if testcases_path.exists() else ""
        )
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
    _archive_verdict(
        payload.qid, payload.lang, verdict, adapter=adapter, cache_rows=cache_rows
    )
    verdict["archived"] = True
    return verdict


def _build_llm() -> LLMClient:
    config = effective_config()
    api_key = str(config.get("llm_api_key", "") or "")
    base_url = str(config.get("llm_base_url", "") or "")
    if not api_key or not base_url:
        raise HTTPException(status_code=400, detail=t("ask_not_configured"))
    return LLMClient(
        base_url=base_url,
        api_key=api_key,
        model=str(config.get("llm_model", "") or "deepseek-v4-flash"),
        timeout=float(config.get("llm_timeout", 120.0)),
    )


COACH_SYSTEM_PROMPT = (
    "你是 AlgoCoach，一位耐心的算法学习教练。用简体中文回答：先给思路要点，"
    "再给复杂度分析；用户要求代码时给关键实现即可。若提供了题目与判定上下文，"
    "结合它们作答；没有则按通用算法问题处理。"
)


class AskPayload(BaseModel):
    question: str
    history: list = []
    qid: str | None = None


@app.post("/api/ask")
def ask_endpoint(payload: AskPayload):
    llm = _build_llm()
    context_parts = []

    row = {}
    if payload.qid:
        row = _problem_row_for(payload.qid)
    if row:
        tags = "、".join(
            (tag.get("name_zh") or tag.get("name_en") or "") for tag in (row.get("tags") or [])[:6]
        )
        context_parts.append(
            f"当前题目: {row.get('frontend_id', '')} {row.get('title_cn', '') or row.get('title_en', '')}"
            f"（难度 {row.get('difficulty', '?')}，标签 {tags or '无'}）"
        )
        verdict = get_archive().latest_by_slug().get(payload.qid)
        if verdict:
            passed = f"{verdict.get('total_correct', '?')}/{verdict.get('total_testcases', '?')}"
            context_parts.append(
                f"上次判定: {verdict.get('status', 'unknown')}，通过用例 {passed}，"
                f"用时 {verdict.get('runtime_display') or '—'}，内存 {verdict.get('memory_display') or '—'}"
            )

    system_prompt = COACH_SYSTEM_PROMPT
    if context_parts:
        system_prompt += "\n\n参考上下文:\n" + "\n".join(context_parts)

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
    ai_configured = False
    if payload.use_llm:
        try:
            llm = _build_llm()
            ai_configured = True
            digest_lines = [
                f"- 解出 {stats['solved_total']} 题"
                f"（Easy {stats['by_difficulty']['easy']} / Medium {stats['by_difficulty']['medium']}"
                f" / Hard {stats['by_difficulty']['hard']}），累计尝试 {stats['attempts_total']} 次"
            ]
            if weak_tags:
                weak_text = ", ".join(
                    f"{t['name_zh']}(掌握 {int(t['mastered'] * 100)}%)" for t in weak_tags[:5]
                )
                digest_lines.append(f"- 薄弱标签: {weak_text}")
            if recommendations:
                rec_text = ", ".join(
                    f"{r.get('frontend_id','')} {r.get('title_cn','')}" for r in recommendations
                )
                digest_lines.append(f"- 推荐练习候选: {rec_text}")
            report_messages = [
                {
                    "role": "system",
                    "content": COACH_SYSTEM_PROMPT
                    + "\n\n现在请基于以下本地练习数据，写一份简短的薄弱点分析与下周练习建议（150字内）。"
                    "数据:\n" + "\n".join(digest_lines),
                },
                {"role": "user", "content": "请生成我的学习报告。"},
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
def archive_recent(limit: int = 50):
    capped = max(1, min(int(limit), 200))
    return {"records": get_archive().recent(capped)}


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
        raise HTTPException(status_code=409, detail=t("sync_in_progress"))

    from lc.config import INSTANCE_LOCK_NAME, app_dir

    root = app_dir()
    cleared = []
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

    auth.reset_state()
    global _archive
    with _archive_lock:
        _archive = None
    logger.info("local data cleared: %s", cleared)
    return {"cleared": cleared, "data_dir": str(root)}


# ---------------------------------------------------------------------------
# built-frontend hosting + SPA fallback (registered last on purpose)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail=t("problem_not_found"))

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
