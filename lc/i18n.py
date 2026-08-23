"""UI message catalog (zh/en), selected by system locale, overridable in settings.

Simple dict approach (no gettext). UI language affects interface strings only;
problem statements are always Chinese because the data source is leetcode.cn.
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
        "run_timeout": "运行判定超时，请稍后重试；若持续失败请把调试日志发给开发者",
        "sync_in_progress": "题库同步正在进行中",
        "not_configured": "尚未完成配置",
        "ask_not_configured": "LLM 未配置，请先在设置中填写 API Key 与接口地址",
        "action_retry": "重试",
        "action_relogin": "重新粘贴 Cookie",
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
        "run_timeout": "Run judging timed out - please retry; if it keeps failing share the debug log",
        "sync_in_progress": "Problem list sync already in progress",
        "not_configured": "Setup not completed yet",
        "ask_not_configured": "LLM is not configured yet - set your API key and base URL in settings first",
        "action_retry": "Retry",
        "action_relogin": "Paste cookie again",
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
