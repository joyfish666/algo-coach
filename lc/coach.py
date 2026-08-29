"""AI coach prompt engineering (pure logic, no data access).

The coach replies in the UI language: the app ships a bilingual interface,
but the prompt was originally a hardcoded Chinese constant, so an en-locale
user asking in English always got a Chinese answer. The frontend i18n store
sends its language as ui_lang on /api/ask and /api/analyze; unknown values
fall back to zh (the historical behavior, also the language every stored
statement is written in).

Every context line is phrased in the reply language: mixing a Chinese prompt
with English context (or vice versa) taught the model to answer in the wrong
language. One locale per system prompt keeps the reply stable. Functions here
take already-fetched data (problem row, verdict, code) - the API layer owns
data access, this module owns wording.
"""

from __future__ import annotations

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


def problem_context_line(row: dict, ui_lang: str) -> str | None:
    """Describe the problem being asked about; None when row is empty."""
    if not row:
        return None
    if ui_lang == "en":
        tags = ", ".join(
            (tag.get("name_en") or tag.get("name_zh") or "")
            for tag in (row.get("tags") or [])[:6]
        )
        return (
            f"Current problem: {row.get('frontend_id', '')} "
            f"{row.get('title_en', '') or row.get('title_cn', '')}"
            f" (difficulty {row.get('difficulty', '?')}, tags {tags or 'none'})"
        )
    tags = "、".join(
        (tag.get("name_zh") or tag.get("name_en") or "") for tag in (row.get("tags") or [])[:6]
    )
    return (
        f"当前题目: {row.get('frontend_id', '')} {row.get('title_cn', '') or row.get('title_en', '')}"
        f"（难度 {row.get('difficulty', '?')}，标签 {tags or '无'}）"
    )


def verdict_context_line(verdict: dict, ui_lang: str) -> str | None:
    """Describe the latest archived verdict; None when there is none."""
    if not verdict:
        return None
    passed = f"{verdict.get('total_correct', '?')}/{verdict.get('total_testcases', '?')}"
    runtime = verdict.get("runtime_display") or "—"
    memory = verdict.get("memory_display") or "—"
    if ui_lang == "en":
        return (
            f"Last verdict: {verdict.get('status', 'unknown')}, cases passed {passed}, "
            f"runtime {runtime}, memory {memory}"
        )
    return (
        f"上次判定: {verdict.get('status', 'unknown')}，通过用例 {passed}，"
        f"用时 {runtime}，内存 {memory}"
    )


def code_context_line(code: str, lang: str | None, ui_lang: str) -> str | None:
    """Attach the editor code the user explicitly shared.

    Editor code is opt-in: the user attaches it explicitly per question so a
    long solution is not shipped to the LLM on every casual ask.
    """
    if not code or not code.strip():
        return None
    lang_label = lang or "text"
    snippet = code[:6000]
    label = f"Current code ({lang_label}):" if ui_lang == "en" else f"当前代码（{lang_label}）:"
    return f"{label}\n```\n{snippet}\n```"


def analyze_digest(stats: dict, weak_tags: list, recommendations: list, ui_lang: str) -> tuple:
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
