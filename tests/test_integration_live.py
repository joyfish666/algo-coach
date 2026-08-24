"""Live-network regression suite (pytest -m integration).

These tests exercise the real leetcode.cn adapter so GraphQL field drift is
caught by an executable check instead of only manual ROADMAP notes. They are
excluded from the default run via pyproject addopts and from CI entirely;
run them manually with a valid cookie:

    ALGOCOACH_TEST_COOKIE="csrftoken=...; LEETCODE_SESSION=..." pytest -m integration
"""

import os

import pytest

from lc.auth import build_session, extract_csrf_token
from lc.config import DEFAULTS
from lc.httpclient import HttpClient
from lc.sites.cn import LeetCodeCnAdapter, normalize_check_payload

pytestmark = pytest.mark.integration

COOKIE = os.environ.get("ALGOCOACH_TEST_COOKIE", "")


def live_adapter() -> LeetCodeCnAdapter:
    if not COOKIE:
        pytest.skip("ALGOCOACH_TEST_COOKIE not set; skipping live network tests")
    session = build_session(COOKIE)
    client = HttpClient(session, default_headers=dict(__import__("lc.auth").DEFAULT_HEADERS))
    return LeetCodeCnAdapter(client=client)


def test_live_validate_cookie():
    profile = live_adapter().validate_cookie()
    assert profile["signed_in"] is True


def test_live_problem_list_page():
    page = live_adapter().fetch_problem_list_page(0, 5)
    assert page["total"] is None or int(page["total"]) > 1000
    assert len(page["problems"]) == 5
    row = page["problems"][0]
    for key in ("slug", "frontend_id", "difficulty"):
        assert row[key]


def test_live_question_detail_and_examples():
    detail = live_adapter().fetch_question_detail("two-sum")
    assert detail["internal_question_id"]
    assert "example_test_cases" in detail
    assert detail["statement_html"]
    assert any(snippet["lang_slug"] == "cpp" for snippet in detail["code_snippets"])


def test_live_daily_question():
    daily = live_adapter().fetch_daily_question()
    assert daily["slug"]


def test_live_recent_submissions_shape():
    items = live_adapter().fetch_recent_submissions(5)
    # unauthenticated returns [] per PITFALLS; with a cookie it returns rows
    for item in items:
        assert item["submission_id"]
        assert item["slug"]


def test_live_check_payload_normalizer():
    verdict = normalize_check_payload(
        {"state": "STARTED"}, fallback_submission_id="x"
    )
    assert verdict["finished"] is False
    assert DEFAULTS["request_interval"] > 0
    assert extract_csrf_token("a=1; csrftoken=t") == "t"
