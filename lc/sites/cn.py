"""leetcode.cn adapter.

Single point of response parsing for the whole app: GraphQL query documents
are organized here and every payload is normalized into plain snake_case
dicts. Missing required fields degrade to clear domain errors instead of
crashes. Field-level names still need live-network verification during the
problems-sync milestone; findings must be recorded back into PITFALLS.md.
"""

from __future__ import annotations

from lc.auth import GRAPHQL_ENDPOINT, check_response, get_http_client
from lc.exceptions import (
    AuthError,
    NetworkError,
    PremiumProblemError,
    ProblemNotFoundError,
)
from lc.i18n import t
from lc.sites.base import SiteAdapter

USER_STATUS_QUERY = """
query userStatusInfo {
  userStatus {
    isSignedIn
    isPremium
  }
}
"""

PROBLEM_LIST_QUERY = """
query problemsetQuestionList($categorySlug: String!, $limit: Int!, $skip: Int!, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      frontendQuestionId: questionFrontendId
      titleSlug
      title
      titleCn
      translatedTitle
      difficulty
      isPaidOnly
      categoryTitle
      topicTags {
        slug
        name
        nameTranslated
      }
    }
  }
}
"""

QUESTION_DETAIL_QUERY = """
query questionDetailBySlug($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionFrontendId
    titleSlug
    title
    titleCn
    translatedTitle
    content
    translatedContent
    difficulty
    isPaidOnly
    hints
    sampleTestCase
    codeSnippets {
      lang
      langSlug
      code
    }
    topicTags {
      slug
      name
      nameTranslated
    }
  }
}
"""

DAILY_QUESTION_QUERY = """
query todayQuestionRecord {
  todayRecord {
    date
    question {
      questionFrontendId
      titleSlug
      title
      titleCn
      translatedTitle
      difficulty
      isPaidOnly
      topicTags {
        slug
        name
        nameTranslated
      }
    }
  }
}
"""


class LeetCodeCnAdapter(SiteAdapter):
    name = "leetcode.cn"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = get_http_client()
        if self._client is None:
            raise NetworkError(t("cookie_missing"))
        return self._client

    def _graphql(self, operation_name: str, query: str, variables: dict = None) -> dict:
        payload = {
            "operationName": operation_name,
            "query": " ".join(query.split()),
            "variables": variables or {},
        }
        response = self.client.post(
            GRAPHQL_ENDPOINT,
            idempotent=True,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        check_response(response, context=operation_name)
        try:
            body = response.json()
        except ValueError as exc:
            raise NetworkError(f"{operation_name}: response is not valid JSON") from exc

        errors = body.get("errors") if isinstance(body, dict) else None
        if errors:
            from lc.auth import is_auth_error_payload

            if is_auth_error_payload(errors):
                raise AuthError(t("cookie_invalid"), detail={"context": operation_name})
            first = errors[0] if isinstance(errors[0], dict) else {}
            message = str(first.get("message", errors[0]))
            raise NetworkError(f"{operation_name}: {message}", detail={"errors": errors})

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise NetworkError(f"{operation_name}: missing data payload")
        return data

    def validate_cookie(self) -> dict:
        data = self._graphql("userStatusInfo", USER_STATUS_QUERY)
        status = data.get("userStatus")
        if not isinstance(status, dict) or "isSignedIn" not in status:
            raise NetworkError("userStatusInfo: missing userStatus.isSignedIn")
        signed_in = bool(status.get("isSignedIn"))
        if not signed_in:
            raise AuthError(t("cookie_invalid"), detail={"context": "userStatusInfo"})
        return {"signed_in": True, "premium": bool(status.get("isPremium"))}

    def fetch_problem_list_page(self, skip: int, limit: int) -> dict:
        variables = {"categorySlug": "", "limit": int(limit), "skip": int(skip), "filters": {}}
        data = self._graphql("problemsetQuestionList", PROBLEM_LIST_QUERY, variables)
        listing = data.get("problemsetQuestionList")
        if not isinstance(listing, dict):
            raise NetworkError("problemsetQuestionList: missing problemsetQuestionList payload")
        raw_rows = listing.get("questions") or []
        problems = [normalize_problem_row(row) for row in raw_rows]
        total = listing.get("total")
        return {
            "total": int(total) if total is not None else len(problems),
            "problems": problems,
        }

    def fetch_question_detail(self, slug: str) -> dict:
        data = self._graphql(
            "questionDetailBySlug", QUESTION_DETAIL_QUERY, {"titleSlug": slug}
        )
        raw = data.get("question")
        if raw is None:
            raise ProblemNotFoundError(t("problem_not_found"), detail={"slug": slug})
        return normalize_question_detail(raw)

    def fetch_daily_question(self) -> dict:
        data = self._graphql("todayQuestionRecord", DAILY_QUESTION_QUERY)
        records = data.get("todayRecord") or []
        if not records:
            raise NetworkError("todayQuestionRecord: no daily record returned")
        record = records[0] if isinstance(records, list) else records
        question = (record or {}).get("question") if isinstance(record, dict) else None
        if not isinstance(question, dict):
            raise NetworkError("todayQuestionRecord: missing question in todayRecord")
        summary = normalize_problem_row(question)
        date = record.get("date") if isinstance(record, dict) else None
        if date:
            summary["date"] = str(date)
        return summary


def normalize_tag(raw) -> dict:
    if not isinstance(raw, dict):
        return {"slug": "", "name_en": "", "name_zh": ""}
    name_en = str(raw.get("name", "") or "")
    return {
        "slug": str(raw.get("slug", "") or ""),
        "name_en": name_en,
        "name_zh": str(raw.get("nameTranslated", "") or raw.get("translatedName", "") or name_en),
    }


def normalize_problem_row(raw) -> dict:
    if not isinstance(raw, dict):
        raise NetworkError("problem row is not an object")
    slug = raw.get("titleSlug")
    if not slug:
        raise NetworkError("problem row missing titleSlug", detail={"raw_keys": sorted(raw)})
    frontend_id = (
        raw.get("frontendQuestionId")
        or raw.get("questionFrontendId")
        or ""
    )
    title_cn = raw.get("titleCn") or raw.get("translatedTitle") or raw.get("title") or ""
    difficulty = str(raw.get("difficulty", "") or "").lower()
    tags = [normalize_tag(tag) for tag in (raw.get("topicTags") or [])]
    return {
        "slug": str(slug),
        "frontend_id": str(frontend_id),
        "title_en": str(raw.get("title", "") or ""),
        "title_cn": str(title_cn),
        "difficulty": difficulty,
        "paid_only": bool(raw.get("isPaidOnly", False)),
        "category": str(raw.get("categoryTitle", "") or raw.get("category", "") or ""),
        "tags": tags,
    }


def normalize_question_detail(raw) -> dict:
    detail = normalize_problem_row(raw)
    statement = raw.get("translatedContent") or raw.get("content")
    if not statement:
        if detail.get("paid_only"):
            raise PremiumProblemError(
                t("premium_problem"), detail={"slug": detail["slug"]}
            )
        raise NetworkError(
            f"question '{detail['slug']}' returned no statement content",
            detail={"slug": detail["slug"]},
        )
    snippets = []
    for snippet in raw.get("codeSnippets") or []:
        if not isinstance(snippet, dict):
            continue
        lang_slug = str(snippet.get("langSlug", "") or "")
        if not lang_slug:
            continue
        snippets.append(
            {
                "lang_slug": lang_slug,
                "lang_name": str(snippet.get("lang", "") or ""),
                "code": str(snippet.get("code", "") or ""),
            }
        )
    detail.update(
        {
            "statement_html": str(statement),
            "hints": [str(hint) for hint in (raw.get("hints") or [])],
            "sample_test_case": str(raw.get("sampleTestCase", "") or ""),
            "code_snippets": snippets,
        }
    )
    return detail
