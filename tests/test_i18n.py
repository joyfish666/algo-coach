import lc.i18n as i18n


def setup_function(function):
    i18n.set_language(None)


def teardown_function(function):
    i18n.set_language(None)


def test_set_language_and_get():
    i18n.set_language("zh")
    assert i18n.get_language() == "zh"
    i18n.set_language("en")
    assert i18n.get_language() == "en"


def test_unknown_language_rejected():
    import pytest

    with pytest.raises(ValueError):
        i18n.set_language("xx")


def test_messages_exist_in_both_languages():
    for lang, table in i18n.MESSAGES.items():
        assert isinstance(table, dict)
        assert "cookie_invalid" in table
        assert "template_missing_hint" in table


def test_t_returns_message_and_falls_back_to_key():
    i18n.set_language("zh")
    assert i18n.t("cookie_invalid") == i18n.MESSAGES["zh"]["cookie_invalid"]
    assert i18n.t("no_such_key") == "no_such_key"


def test_t_formatting():
    i18n.set_language("en")
    message = i18n.t("no_such_key")
    assert isinstance(message, str)


def test_detect_locale_env(monkeypatch):
    monkeypatch.setenv("LC_ALL", "zh_CN.UTF-8")
    assert i18n.detect_locale() == "zh"
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    assert i18n.detect_locale() == "en"


def _frontend_catalog_keys(locale):
    """Extract keys from one locale block of the JS catalog.

    The server sends message_key on every domain error precisely so wording
    follows the UI language instead of the backend process locale; that
    design only works while every backend key exists in BOTH frontend locale
    blocks. The frontend's own check script cannot see these usages - they
    flow through dynamic i18n.t(key) calls - so this parity guard lives on
    the Python side where the backend catalog is importable.
    """
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "web" / "src" / "stores" / "i18n.js").read_text(encoding="utf-8")
    match = re.search(rf"{locale}: \{{([\s\S]*?)\n  \}},", source)
    assert match, f"cannot locate {locale} catalog block in web i18n.js"
    return set(re.findall(r"^    ([a-zA-Z0-9_]+):", match.group(1), re.M))


def test_backend_message_keys_exist_in_frontend_catalog():
    for locale in ("zh", "en"):
        frontend_keys = _frontend_catalog_keys(locale)
        missing = set(i18n.MESSAGES[locale]) - frontend_keys
        assert not missing, (
            f"frontend JS catalog is missing backend message keys ({locale}): "
            f"{sorted(missing)} - server-sent message_key would fall back to "
            "backend-locale text"
        )


def test_frontend_catalog_blocks_were_actually_extracted():
    """The extraction regex depends on the catalog's exact closing shape; a
    refactor of the file could silently extract zero keys and make the parity
    test above vacuously pass. Anchor the guard with a known key."""
    for locale in ("zh", "en"):
        assert "cookie_invalid" in _frontend_catalog_keys(locale)
