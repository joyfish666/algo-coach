"""Logging utilities.

Responsibilities:
- debug switch plus optional log file output
- request/response header redaction: Cookie and API keys are never printed
"""

from __future__ import annotations

import logging

logger = logging.getLogger("algocoach")

SENSITIVE_HEADERS = {"cookie", "authorization", "x-csrftoken"}
REDACTED_PLACEHOLDER = "<redacted>"

_configured = False


def redact_headers(headers) -> dict:
    return {
        key: (REDACTED_PLACEHOLDER if key.lower() in SENSITIVE_HEADERS else value)
        for key, value in dict(headers or {}).items()
    }


def redact_mapping(payload: dict, fields=None) -> dict:
    markers = fields or (
        "cookie",
        "csrftoken",
        "csrf_token",
        "api_key",
        "apikey",
        "token",
        "secret",
        "session",
    )
    result = {}
    for key, value in dict(payload or {}).items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in markers):
            result[key] = REDACTED_PLACEHOLDER
        else:
            result[key] = value
    return result


def setup_logging(debug: bool = False, log_file=None) -> None:
    global _configured
    level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    if log_file:
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    _configured = True


def is_configured() -> bool:
    return _configured
