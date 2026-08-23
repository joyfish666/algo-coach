"""Run/Submit judging pipeline.

Discipline implemented here:
- save-before-judge: the editor code is written to solution.<ext> before any
  remote call so disk content always matches what was judged
- run mode uses the remote interpret flow and never enters submission history
- submit mode polls at most MAX_WAIT_SECONDS (120s) handling PENDING/STARTED
  intermediate states; on timeout one final detail lookup by submission_id is
  performed, and if still unfinished an explicit status:"unknown" verdict with
  the traceable submission_id is returned (never faked success)
- non-idempotent remote calls are never auto-retried by the HTTP layer; this
  module simply surfaces structured errors to the user
"""

from __future__ import annotations

import time

from lc.exceptions import JudgeError
from lc.i18n import t

POLL_INTERVAL_SECONDS = 2.0
MAX_WAIT_SECONDS = 120.0


def unknown_verdict(submission_id: str) -> dict:
    return {
        "finished": False,
        "status_key": "unknown",
        "status_msg": t("judge_timeout_unknown"),
        "submission_id": str(submission_id),
    }


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def judge_run(
    adapter,
    *,
    slug: str,
    question_id: str,
    code: str,
    lang: str,
    input_text: str,
    max_wait: float = 45.0,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> dict:
    """Run mode: interpret remotely against the given input."""
    started = time.monotonic()
    verdict = adapter.run_code(slug, question_id, code, lang, input_text)
    while not verdict.get("finished"):
        if time.monotonic() - started >= max_wait:
            raise JudgeError(
                "interpret result did not finish in time",
                detail={"slug": slug},
            )
        _sleep(poll_interval)
        verdict = adapter.poll_submission(verdict.get("submission_id", ""))
    return verdict


def judge_submit(
    adapter,
    *,
    slug: str,
    question_id: str,
    code: str,
    lang: str,
    max_wait: float = MAX_WAIT_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    sleeper=_sleep,
) -> dict:
    """Submit mode: formal submission + bounded polling.

    Returns the final verdict or an explicit "unknown" record carrying the
    submission_id for later reconciliation.
    """
    submission_id = adapter.submit_code(slug, question_id, code, lang)
    started = time.monotonic()
    while True:
        verdict = adapter.poll_submission(submission_id)
        if verdict.get("finished"):
            return verdict
        if time.monotonic() - started >= max_wait:
            break
        sleeper(poll_interval)
    final_attempt = adapter.poll_submission(submission_id)
    if final_attempt.get("finished"):
        return final_attempt
    return unknown_verdict(submission_id)
