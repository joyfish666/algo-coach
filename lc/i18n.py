"""Server-side message catalog (zh/en), selected by the process locale.

Simple dict approach (no gettext). These strings back the message_key
protocol: the frontend catalogs carry the same keys and re-translate every
server-sent error into the UI language, so this text is the fallback for
API consumers and logs rather than the primary user-facing wording.
"""

from __future__ import annotations

import os
import sys

MESSAGES = {
    "zh": {
        "cookie_invalid": "Cookie 已失效，请重新粘贴",
        "cookie_missing": "尚未配置 Cookie，请先完成引导配置",
        "rate_limited": "请求过于频繁已触发限速，请稍后再试",
        "network_error": "网络错误，请检查网络后重试",
        "premium_problem": "该题为付费题，暂不支持",
        "problem_not_found": "未找到该题目",
        "template_missing_hint": "打开题目并选择该语言",
        "judge_timeout_unknown": "判定超时，结果未知，请在站内确认",
        "judge_missing_question_id": "该题缺少站点内部题号，无法判定；请重新打开题目后重试",
        "run_timeout": "运行判定超时，请稍后重试；若持续失败请把调试日志发给开发者",
        "sync_in_progress": "题库同步正在进行中",
        "ask_not_configured": "LLM 未配置，请先在设置中填写 API Key 与接口地址",
    },
    "en": {
        "cookie_invalid": "Cookie has expired, please paste a new one",
        "cookie_missing": "No cookie configured yet, please finish the setup wizard first",
        "rate_limited": "Rate limited, please try again later",
        "network_error": "Network error, please check your connection and retry",
        "premium_problem": "This is a premium problem and is not supported yet",
        "problem_not_found": "Problem not found",
        "template_missing_hint": "Open the problem and select this language to fetch its template",
        "judge_timeout_unknown": "Judging timed out with unknown result, please verify on the website",
        "judge_missing_question_id": "This problem is missing its internal question id; reopen it and retry",
        "run_timeout": "Run judging timed out - please retry; if it keeps failing share the debug log",
        "sync_in_progress": "Problem list sync already in progress",
        "ask_not_configured": "LLM is not configured yet - set your API key and base URL in settings first",
    },
}

_current_language = None


def detect_locale() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return "zh" if value.lower().startswith("zh") else "en"
    if sys.platform == "win32":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "zh" if (lang_id & 0xFF) == 0x04 else "en"
        except Exception:
            pass
    return "en"


def set_language(lang=None) -> None:
    global _current_language
    if lang in MESSAGES:
        _current_language = lang
    elif lang:
        raise ValueError(f"unsupported language: {lang!r}")
    else:
        _current_language = detect_locale()


def get_language() -> str:
    if _current_language is None:
        set_language(None)
    assert _current_language is not None
    return _current_language


def t(key: str, **kwargs) -> str:
    language = get_language()
    message = MESSAGES[language].get(key) or MESSAGES["en"].get(key)
    if message is None:
        return key
    if kwargs:
        try:
            return message.format(**kwargs)
        except (KeyError, IndexError):
            return message
    return message
