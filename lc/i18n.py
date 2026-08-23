"""UI message catalog (zh/en), selected by system locale, overridable in settings.

UI language affects interface strings only; problem statements are always
Chinese because the data source is leetcode.cn.
"""

MESSAGES = {
    "zh": {},
    "en": {},
}


def detect_locale():
    import locale

    try:
        name = locale.getdefaultlocale()[0] or ""
    except (ValueError, AttributeError):
        name = ""
    return "zh" if name.lower().startswith("zh") else "en"


def translate(key, lang=None):
    lang = lang or detect_locale()
    return MESSAGES.get(lang, {}).get(key) or MESSAGES["en"].get(key) or key
