import json

import pytest

import lc.config as config


@pytest.fixture
def cfg_path(tmp_path):
    return tmp_path / "config.toml"


def test_load_returns_defaults_when_missing(cfg_path):
    data = config.load(cfg_path)
    assert data["schema_version"] == config.SCHEMA_VERSION
    assert data["cookie"] == ""
    assert data["default_language"] == "cpp"
    assert data["theme"] == "system"
    assert data["request_interval"] == 2.0


def test_save_load_roundtrip(cfg_path):
    payload = dict(config.DEFAULTS)
    payload.update(
        {
            "cookie": "LEETCODE_SESSION=abc; csrftoken=tok",
            "llm_api_key": "sk-test",
            "request_interval": 3.5,
            "ui_language": "en",
        }
    )
    config.save(payload, cfg_path)
    loaded = config.load(cfg_path)
    for key in ("cookie", "llm_api_key", "request_interval", "ui_language"):
        assert loaded[key] == payload[key]
    assert loaded["schema_version"] == config.SCHEMA_VERSION
    text = cfg_path.read_text(encoding="utf-8")
    assert "schema_version" in text


def test_save_is_atomic_and_leaves_no_tmp_files(cfg_path):
    payload = dict(config.DEFAULTS)
    payload["llm_model"] = "gpt-x"
    config.save(payload, cfg_path)
    leftovers = [p.name for p in cfg_path.parent.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_fallback_parser_matches_tomllib(cfg_path):
    payload = dict(config.DEFAULTS)
    payload.update({"cookie": 'a="b"; c=d\n', "request_interval": 0.5})
    text = config.dump_toml(payload)
    if config._toml_reader is not None:
        via_tomllib = config._toml_reader.loads(text)
        via_fallback = config.parse_simple_toml(text)
        assert via_tomllib == via_fallback


def test_effective_config_priority_cli_over_env_over_file(cfg_path, monkeypatch):
    file_data = dict(config.DEFAULTS)
    file_data["request_interval"] = 4.0
    file_data["llm_api_key"] = "from-file"
    config.save(file_data, cfg_path)

    monkeypatch.setenv("ALGOCOACH_REQUEST_INTERVAL", "5.5")
    monkeypatch.setenv("ALGOCOACH_LLM_BASE_URL", "https://env.example")

    merged = config.effective_config(path=cfg_path)
    assert merged["request_interval"] == 5.5
    assert merged["llm_api_key"] == "from-file"
    assert merged["llm_base_url"] == "https://env.example"

    merged = config.effective_config(
        cli_overrides={"request_interval": "9", "llm_api_key": None},
        path=cfg_path,
    )
    assert merged["request_interval"] == 9.0
    assert merged["llm_api_key"] == "from-file"


def test_newer_schema_version_rejected(cfg_path):
    raw = dict(config.DEFAULTS)
    raw["schema_version"] = 999
    cfg_path.write_text(config.dump_toml(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        config.load(cfg_path)


def test_workspace_root_resolution(tmp_path):
    custom = {"workspace_root": str(tmp_path / "custom")}
    assert config.workspace_root_path(custom) == tmp_path / "custom"
    default = {"workspace_root": ""}
    resolved = config.workspace_root_path(default)
    assert resolved == config.app_dir() / "workspace"


def test_dump_toml_escapes_specials():
    text = config.dump_toml({"schema_version": 1, "cookie": 'a"b\\c\nd'})
    if config._toml_reader is not None:
        parsed = config._toml_reader.loads(text)
        assert parsed["cookie"] == 'a"b\\c\nd'
