"""leetcode.cn adapter.

Single point of response parsing for the whole app: GraphQL query documents
are organized here and every payload is normalized into plain snake_case
dicts. Missing required fields degrade to clear domain errors instead of
crashes. Field-level names still need live-network verification during the
problems-sync milestone; findings must be recorded back into PITFALLS.md.
"""

from __future__ import annotations

import re

from lc.auth import (
    GRAPHQL_ENDPOINT,
    LEETCODE_CN_BASE,
    check_response,
    get_http_client,
)
from lc.exceptions import (
    AuthError,
    JudgeError,
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
  problemsetQuestionList(categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) {
    hasMore
    total
    questions {
      acRate
      difficulty
      frontendQuestionId
      title
      titleCn
      titleSlug
      paidOnly
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
    questionId
    questionFrontendId
    titleSlug
    title
    translatedTitle
    content
    translatedContent
    difficulty
    isPaidOnly
    hints
    sampleTestCase
    exampleTestcases
    codeSnippets {
      lang
      langSlug
      code
    }
    topicTags {
      slug
      name
      translatedName
    }
  }
}
"""

RECENT_SUBMISSIONS_QUERY = """
query recentSubmissionFeed($limit: Int!, $offset: Int!) {
  submissionList(limit: $limit, offset: $offset) {
    hasNext
    lastKey
    submissions {
      id
      statusDisplay
      lang
      runtime
      timestamp
      url
      title
    }
  }
}
"""

DAILY_QUESTION_QUERY = """
query todayQuestionRecord {
  todayRecord {
    date
    question {
      questionId
      questionFrontendId
      titleSlug
      title
      translatedTitle
      difficulty
      isPaidOnly
    }
  }
}
"""


class LeetCodeCnAdapter(SiteAdapter):
    name = "leetcode.cn"

    SUBMIT_PATH = "/problems/{slug}/submit/"
    CHECK_PATH = "/submissions/detail/{sid}/check/"
    INTERPRET_PATH = "/problems/{slug}/interpret_solution/"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = get_http_client()
        if self._client is None:
            raise NetworkError(t("cookie_missing"))
        return self._client

    def _graphql(self, operation_name: str, query: str, variables: dict = None, *, idempotent: bool = True) -> dict:
        payload = {
            "operationName": operation_name,
            "query": " ".join(query.split()),
            "variables": variables or {},
        }
        response = self.client.post(
            GRAPHQL_ENDPOINT,
            idempotent=idempotent,
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

    def submit_code(self, slug: str, question_id: str, code: str, lang: str) -> str:
        """Formal submission; returns submission_id. Never auto-retried."""
        url = LEETCODE_CN_BASE + self.SUBMIT_PATH.format(slug=slug)
        response = self.client.post(
            url,
            idempotent=False,
            json={"lang": lang, "question_id": str(question_id), "typed_code": code},
            headers={
                "Content-Type": "application/json",
                "X-CSRFToken": self._csrf_token(),
                "Referer": f"{LEETCODE_CN_BASE}/problems/{slug}/",
            },
        )
        check_response(response, context="submit")
        try:
            payload = response.json()
        except ValueError as exc:
            raise NetworkError("submit: response is not valid JSON") from exc
        submission_id = payload.get("submission_id") if isinstance(payload, dict) else None
        if submission_id is None:
            raise NetworkError(
                "submit: missing submission_id",
                detail={"payload_keys": sorted(payload) if isinstance(payload, dict) else []},
            )
        return str(submission_id)

    def poll_submission(self, submission_id: str) -> dict:
        url = LEETCODE_CN_BASE + self.CHECK_PATH.format(sid=submission_id)
        response = self.client.get(url)
        check_response(response, context="check")
        try:
            payload = response.json()
        except ValueError as exc:
            raise NetworkError("check: response is not valid JSON") from exc
        return normalize_check_payload(payload, fallback_submission_id=str(submission_id))

    def run_code(self, slug: str, question_id: str, code: str, lang: str, input_text: str) -> dict:
        """Debug-run via the REST interpret endpoint (never enters history)."""
        url = LEETCODE_CN_BASE + self.INTERPRET_PATH.format(slug=slug)
        response = self.client.post(
            url,
            idempotent=False,
            json={
                "question_id": str(question_id),
                "lang": lang,
                "typed_code": code,
                "input": input_text,
            },
            headers={
                "Content-Type": "application/json",
                "Referer": f"{LEETCODE_CN_BASE}/problems/{slug}/",
            },
        )
        check_response(response, context="interpret_solution")
        try:
            payload = response.json()
        except ValueError as exc:
            raise NetworkError("interpret_solution: response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise NetworkError("interpret_solution: unexpected payload")
        interpret_id = (
            payload.get("interpretation_id")
            or payload.get("interpret_id")
            or payload.get("interpretationId")
            or payload.get("interpretId")
        )
        if not interpret_id:
            raise JudgeError(
                "interpret_solution: missing interpretation id",
                detail={"keys": sorted(payload)},
            )
        return self.poll_submission(str(interpret_id))

    def _csrf_token(self) -> str:
        try:
            return self.client.session.cookies.get("csrftoken") or ""
        except AttributeError:
            token = self.client.default_headers.get("X-CSRFToken", "")
            return token

    def fetch_recent_submissions(self, limit: int = 20) -> list:
        """Site-side recent submissions (capability boundary: about 20)."""
        capped = max(1, min(int(limit), 20))
        data = self._graphql(
            "recentSubmissionFeed",
            RECENT_SUBMISSIONS_QUERY,
            {"limit": capped, "offset": 0},
        )
        feed = data.get("submissionList") or {}
        rows = feed.get("submissions") or []
        normalized = []
        for raw in rows:
            item = normalize_site_submission(raw)
            if item is not None:
                normalized.append(item)
        return normalized


def normalize_tag(raw) -> dict:
    if not isinstance(raw, dict):
        return {"slug": "", "name_en": "", "name_zh": ""}
    name_en = str(raw.get("name", "") or "")
    return {
        "slug": str(raw.get("slug", "") or ""),
        "name_en": name_en,
        "name_zh": str(
            raw.get("nameTranslated", "")
            or raw.get("translatedName", "")
            or name_en
        ),
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
    paid_only = bool(raw.get("paidOnly", raw.get("isPaidOnly", False)))
    ac_rate = raw.get("acRate")
    row = {
        "slug": str(slug),
        "frontend_id": str(frontend_id),
        "title_en": str(raw.get("title", "") or ""),
        "title_cn": str(title_cn),
        "difficulty": difficulty,
        "paid_only": paid_only,
        "category": str(raw.get("categoryTitle", "") or raw.get("category", "") or ""),
        "tags": tags,
    }
    if isinstance(ac_rate, (int, float)):
        row["ac_rate"] = round(float(ac_rate), 2)
    return row


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
            "internal_question_id": str(raw.get("questionId", "") or ""),
            "statement_html": str(statement),
            "hints": [str(hint) for hint in (raw.get("hints") or [])],
            "sample_test_case": str(raw.get("sampleTestCase", "") or ""),
            "code_snippets": snippets,
        }
    )
    return detail


def normalize_site_submission(raw: dict) -> dict | None:
    """Normalize a submissionList row; slug is derived from the url path."""
    if not isinstance(raw, dict):
        return None
    submission_id = raw.get("id") or raw.get("submission_id")
    url = str(raw.get("url", "") or "")
    match = re.search(r"/problems/([a-z0-9-]+)/", url)
    slug = match.group(1) if match else raw.get("titleSlug")
    if not submission_id or not slug:
        return None
    return {
        "submission_id": str(submission_id),
        "slug": str(slug),
        "frontend_id": str(raw.get("frontendQuestionId", "") or ""),
        "title_cn": str(raw.get("translatedTitle", "") or raw.get("titleCn", "") or ""),
        "title_en": str(raw.get("title", "") or ""),
        "status": str(raw.get("statusDisplay", "") or ""),
        "lang": str(raw.get("lang", "") or ""),
        "timestamp": str(raw.get("timestamp", "") or ""),
    }


_STATUS_KEY_RULES = (
    ("accept", "accepted"),
    ("wrong answer", "wrong_answer"),
    ("compile", "compile_error"),
    ("runtime error", "runtime_error"),
    ("time limit", "tle"),
    ("memory limit", "mle"),
    ("output limit", "ole"),
)


def _classify_status(status_msg, run_success) -> str:
    text = str(status_msg or "").strip().lower()
    if not text and run_success:
        return "accepted"
    for marker, key in _STATUS_KEY_RULES:
        if marker in text:
            return key
    if text == "finished" and run_success:
        return "accepted"
    return "unknown"


def humanize_bytes(num) -> str:
    try:
        value = float(num)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def normalize_check_payload(payload: dict, *, fallback_submission_id: str = "") -> dict:
    """Single-point normalization of submission/interpret check payloads.

    Classification relies on the human-readable status_msg first so that
    status-code drift between sites degrades gracefully instead of crashing.
    """
    if not isinstance(payload, dict):
        raise NetworkError("check payload is not an object")
    state = str(payload.get("state", "") or "").upper()
    finished = state == "FINISHED" or "status_msg" in payload and state != "STARTED"
    status_code = payload.get("status_code")
    run_success = bool(payload.get("run_success"))
    runtime = payload.get("runtime")
    runtime_display = payload.get("runtime_display") or (
        f"{runtime} ms" if isinstance(runtime, (int, float)) else ""
    )
    memory = payload.get("memory")
    memory_display = payload.get("memory_display") or humanize_bytes(memory)
    verdict = {
        "finished": finished,
        "raw_state": state,
        "raw_status_code": status_code,
        "status_key": _classify_status(payload.get("status_msg"), run_success)
        if finished
        else None,
        "status_msg": str(payload.get("status_msg", "") or ""),
        "runtime_display": runtime_display,
        "runtime_percentile": _optional_number(payload.get("runtime_percentile")),
        "memory_display": memory_display,
        "memory_percentile": _optional_number(payload.get("memory_percentile")),
        "total_correct": payload.get("total_correct"),
        "total_testcases": payload.get("total_testcases"),
        "outputs": _string_list(payload.get("code_answer")),
        "expected_outputs": _string_list(payload.get("expected_output")),
        "stdout_tail": _join_stdout(payload.get("std_output_list")),
        "compile_error": str(payload.get("compile_error", "") or ""),
        "runtime_error": str(payload.get("runtime_error", "") or payload.get("full_runtime_error", "") or ""),
        "submission_id": str(payload.get("submission_id", "") or fallback_submission_id),
    }
    return verdict


def _optional_number(value):
    try:
        return round(float(value), 1) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _join_stdout(lines):
    if not lines:
        return ""
    if isinstance(lines, list):
        return "\n".join(str(line) for line in lines[-40:])
    return str(lines)
