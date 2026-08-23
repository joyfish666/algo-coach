"""Logging utilities.

Responsibilities (implemented in later milestones):
- debug switch plus optional log file output
- request/response header redaction: Cookie and API keys are never printed
"""

import logging

logger = logging.getLogger("algocoach")

SENSITIVE_HEADERS = {"cookie", "authorization", "x-csrftoken"}


def redact_headers(headers):
    return {
        key: ("<redacted>" if key.lower() in SENSITIVE_HEADERS else value)
        for key, value in headers.items()
    }
