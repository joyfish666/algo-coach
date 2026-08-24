

from lc.judge import judge_run, judge_submit, unknown_verdict


class FakeJudgeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.headers = {}
        self._payload = payload

    def json(self):
        return self._payload


class FakeJudgeAdapter:
    def __init__(self, *, run_results=None, submission_id="9001", poll_sequence=None, default_poll=None):
        self.run_results = list(run_results or [])
        self.poll_sequence = list(poll_sequence or [])
        self.default_poll = default_poll
        self.submitted = []
        self.polled = []

    def submit_code(self, slug, question_id, code, lang):
        self.submitted.append({"slug": slug, "question_id": question_id, "code": code, "lang": lang})
        return "9001"

    def poll_submission(self, submission_id):
        self.polled.append(submission_id)
        if self.poll_sequence:
            return self.poll_sequence.pop(0)
        if self.default_poll is not None:
            return dict(self.default_poll)
        return {"finished": True, "status_key": "accepted", "submission_id": submission_id}

    def run_code(self, slug, question_id, code, lang, input_text):
        self.run_input = input_text
        return self.run_results.pop(0)


STARTED = {"finished": False, "status_key": None, "submission_id": "9001"}
FINISHED_AC = {
    "finished": True,
    "status_key": "accepted",
    "status_msg": "Accepted",
    "runtime_display": "52 ms",
    "runtime_percentile": 88.5,
    "memory_display": "41.2 MB",
    "memory_percentile": 70.1,
    "total_correct": 57,
    "total_testcases": 57,
    "outputs": ["[3,2,4]"],
    "expected_outputs": [],
    "stdout_tail": "",
    "compile_error": "",
    "runtime_error": "",
    "submission_id": "9001",
}


def test_judge_submit_returns_finished_verdict():
    adapter = FakeJudgeAdapter(poll_sequence=[STARTED.copy(), dict(FINISHED_AC)])
    verdict = judge_submit(
        adapter,
        slug="two-sum",
        question_id="1001",
        code="class Solution {};\n",
        lang="cpp",
        max_wait=5,
        poll_interval=0.01,
        sleeper=lambda s: None,
    )
    assert verdict["status_key"] == "accepted"
    assert verdict["total_correct"] == 57
    assert adapter.submitted[0]["question_id"] == "1001"
    assert len(adapter.polled) == 2


def test_judge_submit_timeout_returns_unknown_with_submission_id():
    adapter = FakeJudgeAdapter(default_poll=STARTED)
    verdict = judge_submit(
        adapter,
        slug="two-sum",
        question_id="1",
        code="x",
        lang="cpp",
        max_wait=0.05,
        poll_interval=0.01,
        sleeper=lambda s: None,
    )
    assert verdict["status_key"] == "unknown"
    assert verdict["submission_id"] == "9001"
    assert verdict["finished"] is False


def test_judge_submit_final_poll_recovers_result():
    adapter = FakeJudgeAdapter(poll_sequence=[dict(STARTED), dict(FINISHED_AC)])
    verdict = judge_submit(
        adapter,
        slug="two-sum",
        question_id="1",
        code="x",
        lang="cpp",
        max_wait=0,
        poll_interval=0,
        sleeper=lambda s: None,
    )
    assert verdict["status_key"] == "accepted"


def test_judge_run_waits_for_finish():
    first = dict(STARTED)
    adapter = FakeJudgeAdapter(run_results=[first])
    original_poll = adapter.poll_submission

    def poll_once_then_accept(sid):
        result = original_poll(sid)
        if not result.get("finished"):
            return dict(FINISHED_AC)
        return result

    adapter.poll_submission = poll_once_then_accept
    verdict = judge_run(
        adapter,
        slug="two-sum",
        question_id="1",
        code="x",
        lang="cpp",
        input_text="[2,7,11,15]\n9",
        max_wait=2,
        poll_interval=0.01,
    )
    assert verdict["status_key"] == "accepted"
    assert adapter.run_input == "[2,7,11,15]\n9"


def test_unknown_verdict_shape():
    verdict = unknown_verdict("42")
    assert verdict["status_key"] == "unknown"
    assert verdict["submission_id"] == "42"
    assert "judge_timeout_unknown" in repr(verdict["status_msg"]) or verdict["status_msg"]
