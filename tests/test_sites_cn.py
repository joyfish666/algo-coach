import pytest

from lc.exceptions import AuthError, NetworkError, ProblemNotFoundError
from lc.sites.cn import (
    LeetCodeCnAdapter,
    normalize_problem_row,
    normalize_question_detail,
)


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.headers = {}
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def post(self, url, *, idempotent=False, json=None, headers=None, **kwargs):
        self.calls.append({"url": url, "json": json, "idempotent": idempotent})
        return FakeResponse(self.payloads.pop(0))


def adapter_with(payloads):
    client = FakeClient(payloads)
    return LeetCodeCnAdapter(client=client), client


def test_validate_cookie_ok():
    adapter, _ = adapter_with([{"data": {"userStatus": {"isSignedIn": True, "isPremium": False}}}])
    result = adapter.validate_cookie()
    assert result == {"signed_in": True, "premium": False}
    call = _.calls[0]
    assert call["idempotent"] is True


def test_validate_cookie_signed_out_raises_auth():
    adapter, _ = adapter_with([{"data": {"userStatus": {"isSignedIn": False, "isPremium": False}}}])
    with pytest.raises(AuthError):
        adapter.validate_cookie()


def test_validate_cookie_auth_error_payload_raises_auth():
    adapter, _ = adapter_with([{"errors": [{"message": "User not logged in"}]}])
    with pytest.raises(AuthError):
        adapter.validate_cookie()


def test_graphql_domain_error_raises_network_error():
    adapter, _ = adapter_with([{"errors": [{"message": "internal error"}]}])
    with pytest.raises(NetworkError):
        adapter.validate_cookie()


def test_fetch_problem_list_page_normalizes_rows():
    payload = {
        "data": {
            "problemsetQuestionList": {
                "total": 2,
                "questions": [
                    {
                        "frontendQuestionId": "1",
                        "titleSlug": "two-sum",
                        "title": "Two Sum",
                        "titleCn": "两数之和",
                        "difficulty": "Easy",
                        "paidOnly": False,
                        "topicTags": [
                            {"slug": "array", "name": "Array", "nameTranslated": "数组"},
                            {"slug": "hash-table", "name": "Hash Table", "nameTranslated": "哈希表"},
                        ],
                    },
                    {
                        "frontendQuestionId": "剑指 Offer 03",
                        "titleSlug": "shu-zu-zhong-zhong-fu-de-shu-zi-lcof",
                        "title": "Shu Zu Zhong Zhong Fu De Shu Zi LCOF",
                        "translatedTitle": "数组中重复的数字",
                        "difficulty": "Medium",
                        "paidOnly": True,
                    },
                ],
            }
        }
    }
    adapter, fake_client = adapter_with([payload])
    page = adapter.fetch_problem_list_page(skip=0, limit=50)
    assert page["total"] == 2
    first = page["problems"][0]
    assert first["slug"] == "two-sum"
    assert first["frontend_id"] == "1"
    assert first["title_cn"] == "两数之和"
    assert first["difficulty"] == "easy"
    assert [tag["slug"] for tag in first["tags"]] == ["array", "hash-table"]
    second = page["problems"][1]
    assert second["frontend_id"] == "剑指 Offer 03"
    assert second["paid_only"] is True
    assert second["tags"] == []
    variables = fake_client.calls[0]["json"]["variables"]
    assert variables == {"categorySlug": "", "limit": 50, "skip": 0, "filters": {}}


def test_fetch_problem_list_missing_payload_raises():
    adapter, _ = adapter_with([{"data": {}}])
    with pytest.raises(NetworkError):
        adapter.fetch_problem_list_page(0, 10)


def test_normalize_problem_row_requires_slug():
    with pytest.raises(NetworkError):
        normalize_problem_row({"frontendQuestionId": "9"})


def test_fetch_question_detail_full():
    payload = {
        "data": {
            "question": {
                "questionFrontendId": "1",
                "titleSlug": "two-sum",
                "title": "Two Sum",
                "translatedTitle": "两数之和",
                "translatedContent": "<p>给你一个整数数组</p>",
                "difficulty": "EASY",
                "isPaidOnly": False,
                "hints": ["哈希表", "一次遍历"],
                "sampleTestCase": "[2,7,11,15]\n9",
                "codeSnippets": [
                    {"lang": "C++", "langSlug": "cpp", "code": "class Solution {};\n"},
                    {"lang": "Python3", "langSlug": "python3", "code": "class Solution:\n    pass\n"},
                ],
                "topicTags": [{"slug": "array", "name": "Array", "nameTranslated": "数组"}],
            }
        }
    }
    adapter, _ = adapter_with([payload])
    detail = adapter.fetch_question_detail("two-sum")
    assert detail["statement_html"] == "<p>给你一个整数数组</p>"
    assert detail["hints"] == ["哈希表", "一次遍历"]
    assert detail["sample_test_case"] == "[2,7,11,15]\n9"
    assert [snippet["lang_slug"] for snippet in detail["code_snippets"]] == ["cpp", "python3"]
    assert detail["code_snippets"][0]["code"].endswith(";\n")


def test_fetch_question_detail_falls_back_to_english_content():
    payload = {
        "data": {
            "question": {
                "questionFrontendId": "1",
                "titleSlug": "two-sum",
                "content": "<p>English statement</p>",
                "difficulty": "easy",
            }
        }
    }
    adapter, _ = adapter_with([payload])
    detail = adapter.fetch_question_detail("two-sum")
    assert detail["statement_html"] == "<p>English statement</p>"


def test_fetch_question_detail_without_statement_raises():
    payload = {"data": {"question": {"titleSlug": "x", "difficulty": "easy"}}}
    adapter, _ = adapter_with([payload])
    with pytest.raises(NetworkError):
        adapter.fetch_question_detail("x")


def test_fetch_question_detail_unknown_slug_raises_not_found():
    adapter, _ = adapter_with([{"data": {"question": None}}])
    with pytest.raises(ProblemNotFoundError):
        adapter.fetch_question_detail("nope")


def test_fetch_daily_question():
    payload = {
        "data": {
            "todayRecord": [
                {
                    "date": "2026-08-23",
                    "question": {
                        "questionFrontendId": "3",
                        "titleSlug": "longest-substring-without-repeating-characters",
                        "title": "Longest Substring Without Repeating Characters",
                        "translatedTitle": "无重复字符的最长子串",
                        "difficulty": "MEDIUM",
                        "isPaidOnly": False,
                    },
                }
            ]
        }
    }
    adapter, _ = adapter_with([payload])
    daily = adapter.fetch_daily_question()
    assert daily["slug"] == "longest-substring-without-repeating-characters"
    assert daily["frontend_id"] == "3"
    assert daily["date"] == "2026-08-23"
    assert daily["difficulty"] == "medium"


def test_fetch_daily_empty_record_raises():
    adapter, _ = adapter_with([{"data": {"todayRecord": []}}])
    with pytest.raises(NetworkError):
        adapter.fetch_daily_question()


def test_normalize_question_detail_direct():
    raw = {
        "titleSlug": "a",
        "questionFrontendId": "LCP 07",
        "difficulty": "HARD",
        "translatedContent": "<p>题面</p>",
    }
    detail = normalize_question_detail(raw)
    assert detail["frontend_id"] == "LCP 07"
    assert detail["paid_only"] is False


def test_normalize_site_submission_extracts_slug_from_url():
    from lc.sites.cn import normalize_site_submission

    row = normalize_site_submission({
        "id": "777",
        "statusDisplay": "Accepted",
        "lang": "cpp",
        "runtime": "52 ms",
        "timestamp": "1755900000",
        "url": "/problems/two-sum/submissions/",
        "title": "Two Sum",
    })
    assert row["slug"] == "two-sum"
    assert row["submission_id"] == "777"
    assert row["status"] == "Accepted"

    assert normalize_site_submission({"id": "1"}) is None
    assert normalize_site_submission({"id": "1", "url": "/contests/weekly/"}) is None
    assert normalize_site_submission({"url": "/problems/x/"}) is None
