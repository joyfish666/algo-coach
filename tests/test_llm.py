import pytest

from lc.exceptions import NetworkError
from lc.llm import LLMClient, normalize_base_url


class FakeLLMResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def capture_post(monkeypatch):
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        calls["headers"] = headers
        calls["timeout"] = timeout
        return calls.get("response", FakeLLMResponse(200, {
            "choices": [{"message": {"content": " 思路：哈希表 "}}]
        }))

    monkeypatch.setattr("lc.llm.requests.post", fake_post)
    return calls


def test_normalize_base_url_variants():
    assert normalize_base_url("https://api.x.com/v1") == "https://api.x.com/v1/chat/completions"
    assert normalize_base_url("https://api.x.com/v1/") == "https://api.x.com/v1/chat/completions"
    assert (
        normalize_base_url("https://api.x.com/v1/chat/completions")
        == "https://api.x.com/v1/chat/completions"
    )
    with pytest.raises(NetworkError):
        normalize_base_url("  ")


def test_normalize_thinking_rejects_unknown():
    from lc.llm import normalize_thinking

    assert normalize_thinking(" HIGH ") == "high"
    assert normalize_thinking("off") == "off"
    assert normalize_thinking("bogus") == "default"
    assert normalize_thinking("") == "default"


def test_chat_thinking_fields_mapping(capture_post):
    # default sends nothing: always safe against strict providers
    LLMClient(base_url="https://api.x.com/v1", api_key="k").chat([])
    assert "enable_thinking" not in capture_post["json"]
    assert "reasoning_effort" not in capture_post["json"]

    LLMClient(base_url="https://api.x.com/v1", api_key="k", thinking="off").chat([])
    assert capture_post["json"]["enable_thinking"] is False
    assert "reasoning_effort" not in capture_post["json"]

    LLMClient(base_url="https://api.x.com/v1", api_key="k", thinking="high").chat([])
    assert capture_post["json"]["enable_thinking"] is True
    assert capture_post["json"]["reasoning_effort"] == "high"


def test_chat_success_and_request_shape(capture_post):
    client = LLMClient(base_url="https://api.x.com/v1", api_key="sk-1", model="m1", timeout=7)
    answer = client.chat([{"role": "user", "content": "hi"}])
    assert answer == "思路：哈希表"
    assert capture_post["url"] == "https://api.x.com/v1/chat/completions"
    assert capture_post["headers"]["Authorization"] == "Bearer sk-1"
    assert capture_post["timeout"] == 7
    body = capture_post["json"]
    assert body["model"] == "m1"
    assert body["stream"] is False


def test_chat_no_site_headers_leak(capture_post):
    import lc.auth as auth

    client = LLMClient(base_url="https://api.x.com/v1", api_key="sk-1", timeout=5)
    client.chat([])
    sent_headers = capture_post["headers"]
    assert "Referer" not in sent_headers
    assert "X-CSRFToken" not in sent_headers
    assert sent_headers.get("User-Agent", "") != auth.BROWSER_UA


def test_chat_http_error_surfaces_message(capture_post):
    capture_post["response"] = FakeLLMResponse(401, {"error": {"message": "bad key"}})
    client = LLMClient(base_url="https://api.x.com/v1", api_key="bad", timeout=5)
    with pytest.raises(NetworkError) as exc_info:
        client.chat([])
    assert "401" in str(exc_info.value)
    assert "bad key" in str(exc_info.value)


def test_chat_unexpected_shape(capture_post):
    capture_post["response"] = FakeLLMResponse(200, {"unexpected": True})
    client = LLMClient(base_url="https://api.x.com/v1", api_key="k", timeout=5)
    with pytest.raises(NetworkError):
        client.chat([])


def test_chat_network_failure_translated(monkeypatch):
    import requests

    def boom(url, **kwargs):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr("lc.llm.requests.post", boom)
    client = LLMClient(base_url="https://api.x.com/v1", api_key="k", timeout=5)
    with pytest.raises(NetworkError):
        client.chat([])


def test_chat_null_content_is_error_not_literal_none(capture_post):
    """Reasoning-style endpoints answer with content:null; str(None) used to
    surface the literal string "None" as the coach's reply with a 200."""
    capture_post["response"] = FakeLLMResponse(200, {"choices": [{"message": {"content": None}}]})
    client = LLMClient(base_url="https://api.x.com/v1", api_key="k", timeout=5)
    with pytest.raises(NetworkError) as exc_info:
        client.chat([])
    assert "None" not in str(exc_info.value)


def test_chat_null_content_falls_back_to_reasoning_content(capture_post):
    """max_tokens-limited probes against thinking models can spend all tokens
    in reasoning_content; the connection test used to fail on those."""
    capture_post["response"] = FakeLLMResponse(
        200,
        {"choices": [{"message": {"content": None, "reasoning_content": " 推理过程 "}}]},
    )
    client = LLMClient(base_url="https://api.x.com/v1", api_key="k", timeout=5)
    assert client.chat([]) == "推理过程"
