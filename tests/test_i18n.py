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
