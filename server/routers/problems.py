"""Problem list, sync, daily question, per-problem workspace, judging."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lc import favorites, judge, problems, workspace
from lc.archive import build_record
from lc.exceptions import AlgoCoachError
from lc.langs import is_supported
from lc.logutil import logger
from server import state
from server.errors import http_domain_error, require_safe_qid

router = APIRouter()


@router.get("/api/problems")
def get_problems():
    payload = problems.load_problems()
    latest = state.get_archive().latest_by_slug()
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


@router.post("/api/problems/sync")
def start_sync():
    adapter = state.create_adapter()
    with state.lifecycle_lock:
        started = state.sync_engine.begin(adapter, cache_path=None)
    if not started:
        raise http_domain_error(409, "sync_in_progress")
    return {"started": True, "progress": state.sync_engine.progress()}


@router.get("/api/problems/sync/progress")
def sync_progress():
    return state.sync_engine.progress()


# ---------------------------------------------------------------------------
# daily / problem workspace


@router.get("/api/daily")
def get_daily():
    return state.create_adapter().fetch_daily_question()


def _open_or_refresh(slug: str, refresh: bool) -> dict:
    adapter = state.create_adapter()
    root = state.workspace_root()
    directory = workspace.find_problem_dir(root, slug)
    need_fetch = refresh or directory is None

    detail = None
    if need_fetch:
        detail = adapter.fetch_question_detail(slug)
        summary = problems.summary_from_detail(detail)
        if refresh and directory is not None:
            result = workspace.refresh_problem(
                directory, detail, default_language=state.default_language()
            )
            logger.info("refreshed %s backups=%s", slug, result["backups"])
        else:
            directory = workspace.open_problem(
                detail, root, default_language=state.default_language()
            )
        problems.upsert_summary_into_cache(summary)

    if directory is None:
        raise http_domain_error(404, "problem_not_found")

    if not need_fetch and not workspace.statement_up_to_date(directory):
        # statement.md is regenerable converter output; a stored workspace
        # written by an older converter renders literal "**" garbage, so it
        # is refreshed once from the site. Offline or site-side failure
        # degrades to the stored file - offline review keeps working.
        try:
            detail = adapter.fetch_question_detail(slug)
            workspace.regenerate_statement(directory, detail)
            logger.info(
                "regenerated statement.md for %s (converter v%d)",
                slug,
                workspace.STATEMENT_VERSION,
            )
        except (AlgoCoachError, OSError) as exc:
            logger.warning("statement regeneration skipped for %s: %s", slug, exc)

    problem_state = workspace.read_problem_state(directory, default_language=state.default_language())
    cache = problems.load_problems()
    row = next((p for p in cache["problems"] if p["slug"] == slug), {})
    problem_state.update(row)
    problem_state.setdefault("slug", slug)
    problem_state["dir"] = directory.name
    problem_state["path"] = str(directory)
    problem_state["favorite"] = favorites.is_favorite(slug)
    return problem_state


@router.get("/api/problem/{qid}")
def get_problem(qid: str):
    require_safe_qid(qid)
    return _open_or_refresh(qid, False)


@router.post("/api/problem/{qid}/refresh")
def refresh_problem(qid: str):
    """Force a remote refetch; POST so the side effect cannot ride on GET."""
    require_safe_qid(qid)
    return _open_or_refresh(qid, True)


@router.get("/api/problem/{qid}/template")
def get_template(qid: str, lang: str | None = None):
    # default comes from config like everywhere else, not a hardcoded cpp:
    # a python3-default user hitting this route without ?lang= must not get
    # C++ semantics
    lang = lang or state.default_language()
    require_safe_qid(qid)
    if not is_supported(lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {lang}")
    directory = workspace.find_problem_dir(state.workspace_root(), qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    result = workspace.ensure_template(
        directory,
        lang,
        detail_provider=lambda: state.create_adapter().fetch_question_detail(qid),
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


@router.put("/api/problem/{qid}/testcases")
def put_testcases(qid: str, payload: TestcasesPayload):
    require_safe_qid(qid)
    directory = workspace.find_problem_dir(state.workspace_root(), qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    workspace.save_testcases(directory, payload.content)
    return {"slug": qid, "saved": True}


class SolutionPayload(BaseModel):
    lang: str
    code: str


@router.put("/api/problem/{qid}/solution")
def put_solution(qid: str, payload: SolutionPayload):
    require_safe_qid(qid)
    if not is_supported(payload.lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {payload.lang}")
    directory = workspace.find_problem_dir(state.workspace_root(), qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    path = workspace.save_solution(directory, payload.lang, payload.code)
    return {"slug": qid, "lang": payload.lang, "saved": True, "mtime": path.stat().st_mtime}


class NotesPayload(BaseModel):
    content: str


@router.put("/api/problem/{qid}/notes")
def put_notes(qid: str, payload: NotesPayload):
    require_safe_qid(qid)
    directory = workspace.find_problem_dir(state.workspace_root(), qid)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    workspace.save_notes(directory, payload.content)
    return {"slug": qid, "saved": True}


class FavoritePayload(BaseModel):
    favorite: bool


@router.put("/api/problem/{qid}/favorite")
def put_favorite(qid: str, payload: FavoritePayload):
    """Toggle the list-level favorite flag for one problem."""
    require_safe_qid(qid)
    favorite_state = favorites.set_favorite(qid, bool(payload.favorite))
    logger.info("favorite %s -> %s", qid, favorite_state)
    return {"slug": qid, "favorite": favorite_state}


# ---------------------------------------------------------------------------
# judging


def _archive_verdict(
    slug: str, lang: str, verdict: dict, adapter=None, cache_rows=None
) -> dict:
    row = state.problem_row_for(slug, adapter=adapter, cache_rows=cache_rows)
    record = build_record(
        slug=slug,
        frontend_id=row.get("frontend_id", ""),
        submission_id=verdict.get("submission_id", ""),
        lang=lang,
        verdict=verdict,
        problem_row=row,
    )
    state.get_archive().append(record)
    return record


def _resolve_judge_context(slug: str) -> tuple:
    """Resolve (directory, question_id, frontend_row, cache_rows) in one pass.

    The problem cache is read exactly once here; the submit path reuses
    cache_rows for archiving instead of hitting the disk again.
    """
    require_safe_qid(slug)
    directory = workspace.find_problem_dir(state.workspace_root(), slug)
    if directory is None:
        raise http_domain_error(404, "problem_not_found")
    meta = workspace.load_meta(directory)
    question_id = str(meta.get("internal_question_id", "") or "")
    cache_rows = problems.load_problems()["problems"]
    frontend_row = next((p for p in cache_rows if p.get("slug") == slug), {})
    if not question_id:
        detail = state.create_adapter().fetch_question_detail(slug)
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


@router.post("/api/judge/run")
def judge_run_endpoint(payload: JudgeRunPayload):
    if not is_supported(payload.lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {payload.lang}")
    directory, question_id, _frontend_row, _cache_rows = _resolve_judge_context(payload.qid)

    if payload.use_local:
        input_text = workspace.stored_testcases(directory)
    else:
        # every stored official case participates in a remote run
        input_text = workspace.official_case_input(directory)

    workspace.save_solution(directory, payload.lang, payload.code)
    verdict = judge.judge_run(
        state.create_adapter(),
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


@router.post("/api/judge/submit")
def judge_submit_endpoint(payload: JudgeSubmitPayload):
    if not is_supported(payload.lang):
        raise HTTPException(status_code=422, detail=f"unsupported language: {payload.lang}")
    directory, question_id, _frontend_row, cache_rows = _resolve_judge_context(payload.qid)
    workspace.save_solution(directory, payload.lang, payload.code)
    adapter = state.create_adapter()
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
