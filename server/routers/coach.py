"""AI coach endpoints: chat ask and the weakness-analysis report.

Wording/prompt engineering lives in lc.coach; this module owns data access
(problem row, latest verdict, practice stats) and the LLM call.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lc import coach, problems
from lc.archive import compute_stats, recommend_problems, tag_mastery
from lc.config import effective_config
from lc.exceptions import AlgoCoachError
from lc.logutil import logger
from server import state

router = APIRouter()


class AskPayload(BaseModel):
    question: str
    history: list = []
    qid: str | None = None
    code: str | None = None
    lang: str | None = None
    ui_lang: str | None = None


@router.post("/api/ask")
def ask_endpoint(payload: AskPayload):
    llm = state.build_llm()
    ui_lang = coach.normalize_ui_lang(payload.ui_lang)

    context_parts = []
    if payload.qid:
        row = state.problem_row_for(payload.qid)
        line = coach.problem_context_line(row, ui_lang)
        if line:
            context_parts.append(line)
        verdict = state.get_archive().latest_by_slug().get(payload.qid)
        verdict_line = coach.verdict_context_line(verdict, ui_lang)
        if verdict_line:
            context_parts.append(verdict_line)
    code_line = coach.code_context_line(payload.code or "", payload.lang, ui_lang)
    if code_line:
        context_parts.append(code_line)

    system_prompt = coach.coach_system_prompt(ui_lang)
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


@router.post("/api/analyze")
def analyze_endpoint(payload: AnalyzePayload):
    archive = state.get_archive()
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
            llm = state.build_llm()
            ai_configured = True
            ui_lang = coach.normalize_ui_lang(payload.ui_lang)
            digest, instruction, user_turn = coach.analyze_digest(
                stats, weak_tags, recommendations, ui_lang
            )
            report_messages = [
                {
                    "role": "system",
                    "content": coach.coach_system_prompt(ui_lang) + instruction + digest,
                },
                {"role": "user", "content": user_turn},
            ]
            ai_report = llm.chat(report_messages)
        except HTTPException:
            # state.build_llm raises 400 ask_not_configured when unset; the
            # report simply omits the AI section instead of failing the page
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
