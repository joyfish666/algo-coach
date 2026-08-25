import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from lc.exceptions import NetworkError
from server import api as api_module

ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ALGOCOACH_HOME", str(home))
    auth.reset_state()
    api_module._archive = None
    yield
    auth.reset_state()
    api_module._archive = None


@pytest.fixture
def client():
    return TestClient(api_module.app, base_url="http://127.0.0.1:8000")


def seed_config_llm(monkeypatch=None, **extra):
    import lc.config as config

    data = dict(config.DEFAULTS)
    data.update({"llm_api_key": "sk-saved-key-123456", "llm_base_url": "https://saved.test/v1"})
    data.update(extra)
    config.save(data)


class FakeLLM:
    model = "fake-model"

    captured_kwargs = None
    captured_messages = None
    captured_max_tokens = None
    chat_result = "pong"

    def __init__(self, **kwargs):
        type(self).captured_kwargs = kwargs

    def chat(self, messages, *, max_tokens=None):
        type(self).captured_messages = messages
        type(self).captured_max_tokens = max_tokens
        return type(self).chat_result

    @classmethod
    def reset(cls):
        cls.captured_kwargs = None
        cls.captured_messages = None
        cls.captured_max_tokens = None
        cls.chat_result = "pong"


@pytest.fixture(autouse=True)
def reset_fake_llm():
    FakeLLM.reset()
    yield
    FakeLLM.reset()


def test_llm_test_requires_config(client):
    response = client.post("/api/llm/test", json={}, headers=ORIGIN)
    assert response.status_code == 400
    assert response.json()["detail"].startswith("LLM")


def test_llm_test_ok_with_saved_config(client, monkeypatch):
    seed_config_llm()
    monkeypatch.setattr(api_module, "LLMClient", lambda **kwargs: FakeLLM(**kwargs))

    response = client.post("/api/llm/test", json={}, headers=ORIGIN)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["model"] == "fake-model"
    # saved values were used and the probe stayed cheap
    assert FakeLLM.captured_kwargs["api_key"] == "sk-saved-key-123456"
    assert FakeLLM.captured_kwargs["base_url"] == "https://saved.test/v1"
    assert FakeLLM.captured_max_tokens is not None and FakeLLM.captured_max_tokens <= 16
    assert FakeLLM.captured_messages[-1]["content"] == "ping"


def test_llm_test_payload_overrides_saved(client, monkeypatch):
    seed_config_llm()
    monkeypatch.setattr(api_module, "LLMClient", lambda **kwargs: FakeLLM(**kwargs))

    response = client.post(
        "/api/llm/test",
        json={
            "llm_api_key": "sk-typed-key-987654",
            "llm_base_url": "https://typed.test/v1",
            "llm_model": "typed-model",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200
    assert FakeLLM.captured_kwargs["api_key"] == "sk-typed-key-987654"
    assert FakeLLM.captured_kwargs["base_url"] == "https://typed.test/v1"
    assert FakeLLM.captured_kwargs["model"] == "typed-model"


def test_llm_test_partial_override_falls_back_to_saved(client, monkeypatch):
    seed_config_llm(llm_model="saved-model")
    monkeypatch.setattr(api_module, "LLMClient", lambda **kwargs: FakeLLM(**kwargs))

    response = client.post(
        "/api/llm/test",
        json={"llm_base_url": "https://typed.test/v1"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    # only base_url was overridden; key and model come from the saved config
    assert FakeLLM.captured_kwargs["api_key"] == "sk-saved-key-123456"
    assert FakeLLM.captured_kwargs["base_url"] == "https://typed.test/v1"
    assert FakeLLM.captured_kwargs["model"] == "saved-model"


def test_llm_test_translates_network_error(client, monkeypatch):
    seed_config_llm()
    monkeypatch.setattr(api_module, "LLMClient", lambda **kwargs: FakeLLM(**kwargs))

    def boom(self, messages, *, max_tokens=None):
        raise NetworkError("LLM HTTP 401: bad key")

    FakeLLM.chat = boom
    response = client.post("/api/llm/test", json={}, headers=ORIGIN)
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["kind"] == "NetworkError"
    assert "401" in error["message"]


def test_llm_test_rejects_unknown_fields(client):
    response = client.post("/api/llm/test", json={"cookie": "x"}, headers=ORIGIN)
    assert response.status_code == 422
