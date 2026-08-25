"""OpenAI-compatible LLM client (stateless).

Reuses the HTTP layer's forced timeouts and structured error translation but
disables rate limiting and site-specific header injection (UA/csrf/Referer do
not apply to user-configured endpoints). Request timeout is separate and
configurable (llm_timeout, default 120s) because long answers take tens of
seconds. v0.1 is non-streaming.
"""

from __future__ import annotations

import requests

from lc.exceptions import NetworkError
from lc.logutil import logger


def normalize_base_url(base_url: str) -> str:
    url = (base_url or "").strip().rstrip("/")
    if not url:
        raise NetworkError("LLM base URL is empty")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


class LLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "deepseek-v4-flash",
        timeout: float = 120.0,
    ):
        self.endpoint = normalize_base_url(base_url)
        self.api_key = api_key
        self.model = model or "deepseek-v4-flash"
        self.timeout = float(timeout)

    def chat(self, messages: list, *, max_tokens: int | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
        }
        # connectivity probes pass a tiny cap so a ping stays cheap
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        logger.debug("llm chat model=%s endpoint=%s msgs=%d", self.model, self.endpoint, len(messages))
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.warning("llm request failed: %s", exc)
            raise NetworkError(f"LLM request failed: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning("llm non-JSON response (HTTP %s)", response.status_code)
            raise NetworkError(f"LLM: non-JSON response (HTTP {response.status_code})") from exc

        if response.status_code >= 400:
            message = "unknown error"
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message", message))
                elif isinstance(error, str):
                    message = error
            logger.warning("llm HTTP %s: %s", response.status_code, message)
            raise NetworkError(f"LLM HTTP {response.status_code}: {message}")

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("llm unexpected completion shape keys=%s", sorted(body) if isinstance(body, dict) else type(body))
            raise NetworkError("LLM: unexpected completion shape") from exc
        return str(content).strip()
