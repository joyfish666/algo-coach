import json

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from server import api as api_module


class FakeJudgeAdapter:
    def __init__(self, *, detail=None, run_verdict=None, submission_id="9001", poll_sequence=None):
        self.detail = detail or DETAIL_FIXTURE.copy()
        self.run_verdict = run_verdict or dict(FINISHED_AC)
        self.poll_sequence = list(poll_sequence or [])
        self.submission_id_value = submission_id
        self.submissions = []
        self.runs = []

    def fetch_question_detail(self, slug):
        return json.loads(json.dumps(self.detail))

    def run_code(self, slug, question_id, code, lang, input_text):
        self.runs.append(
            {"slug": slug, "question_id": question_id, "code": code, "lang": lang, "input": input_text}
        )
        return dict(self.run_verdict)

    def submit_code(self, slug, question_id, code, lang):
        self.submissions.append({"slug": slug, "question_id": question_id, "code": code, "lang": lang})
        return self.submission_id_value

    def poll_submission(self, submission_id):
        if self.poll_sequence:
            return self.poll_sequence.pop(0)
        return dict(FINISHED_AC)


DETAIL_FIXTURE = {
    "slug": "two-sum",
    "internal_question_id": "1001",
    "frontend_id": "1",
    "title_en": "Two Sum",
    "title_cn": "两数之和",
    "difficulty": "easy",
    "paid_only": False,
    "category": "Algorithms",
    "tags": [],
    "statement_html": "<p>题面</p>",
    "hints": [],
    "sample_test_case": "[2,7,11,15]\n9",
    "code_snippets": [
        {"lang_slug": "cpp", "code": "class Solution {};\n"},
        {"lang_slug": "python3", "code": "# py\n"},
    ],
}

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
    "expected_outputs": ["[3,2,4]"],
    "stdout_tail": "",
    "compile_error": "",
    "runtime_error": "",
    "submission_id": "9001",
}

ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ALGOCOACH_HOME", str(home))
    auth.reset_state()
    yield
    auth.reset_state()


@pytest.fixture
def client():
    return TestClient(api_module.app, base_url="http://127.0.0.1:8000")


def open_problem(client, monkeypatch, adapter=None):
    adapter = adapter or FakeJudgeAdapter()
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    response = client.get("/api/problem/two-sum")
    assert response.status_code == 200
    return adapter


def test_run_with_default_sample_cases(client, monkeypatch):
    adapter = open_problem(client, monkeypatch)
    response = client.post(
        "/api/judge/run",
        json={"qid": "two-sum", "lang": "cpp", "code": "class Solution {};\n", "use_local": False},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    verdict = response.json()
    assert verdict["status_key"] == "accepted"
    assert verdict["mode"] == "run"
    assert verdict["input"] == "[2,7,11,15]\n9"
    assert adapter.runs[0]["input"] == "[2,7,11,15]\n9"
    assert adapter.runs[0]["question_id"] == "1001"


def test_save_before_judge_persists_editor_code(client, monkeypatch):
    adapter = open_problem(client, monkeypatch)
    editor_code = "// my latest local edit\n"
    client.post(
        "/api/judge/run",
        json={"qid": "two-sum", "lang": "cpp", "code": editor_code, "use_local": False},
        headers=ORIGIN,
    )
    saved = (api_module.problems.find_problem_dir(api_module._workspace_root(), "two-sum") / "solution.cpp").read_text(encoding="utf-8")
    assert saved == editor_code
    assert adapter.runs[0]["code"] == editor_code


def test_run_with_local_custom_testcases(client, monkeypatch):
    adapter = open_problem(client, monkeypatch)
    client.put(
        "/api/problem/two-sum/testcases",
        json={"content": "[5,5]\n10"},
        headers=ORIGIN,
    )
    response = client.post(
        "/api/judge/run",
        json={"qid": "two-sum", "lang": "cpp", "code": "x", "use_local": True},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    assert adapter.runs[0]["input"] == "[5,5]\n10"


def test_run_merges_all_official_example_cases(client, monkeypatch):
    """Regression: only cases[0] used to be sent; every official example must
    participate in a remote run (inputs newline-concatenated, site parity)."""
    detail = DETAIL_FIXTURE.copy()
    detail["example_test_cases"] = ["[2,7,11,15]\n9", "[3,2,4]\n6"]
    adapter = open_problem(client, monkeypatch, FakeJudgeAdapter(detail=detail))
    response = client.post(
        "/api/judge/run",
        json={"qid": "two-sum", "lang": "cpp", "code": "x", "use_local": False},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    assert adapter.runs[0]["input"] == "[2,7,11,15]\n9\n[3,2,4]\n6"


def test_submit_long_poll_returns_final(client, monkeypatch):
    open_problem(client, monkeypatch)
    response = client.post(
        "/api/judge/submit",
        json={"qid": "two-sum", "lang": "cpp", "code": "class S {};"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    verdict = response.json()
    assert verdict["mode"] == "submit"
    assert verdict["status_key"] == "accepted"
    assert verdict["submission_id"] == "9001"


def test_put_solution_endpoint_writes_file(client, monkeypatch):
    open_problem(client, monkeypatch)
    response = client.put(
        "/api/problem/two-sum/solution",
        json={"lang": "python3", "code": "# hello\n"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    directory = api_module.problems.find_problem_dir(api_module._workspace_root(), "two-sum")
    assert (directory / "solution.py").read_text(encoding="utf-8") == "# hello\n"
    unsupported = client.put(
        "/api/problem/two-sum/solution",
        json={"lang": "ruby", "code": "x"},
        headers=ORIGIN,
    )
    assert unsupported.status_code == 422


def test_create_adapter_lazy_initializes_from_config(client, monkeypatch):
    import lc.config as config

    data = dict(config.DEFAULTS)
    data["cookie"] = "csrftoken=tok9; LEETCODE_SESSION=sess9"
    data["request_interval"] = 3.0
    config.save(data)
    auth.reset_state()
    api_module._archive = None

    adapter = api_module.create_adapter()
    session = auth.get_session()
    assert session.cookies.get("csrftoken") == "tok9"
    assert adapter.client.limiter.interval == 3.0


def test_judge_requires_existing_problem(client, monkeypatch):
    monkeypatch.setattr(api_module, "create_adapter", lambda: FakeJudgeAdapter())
    response = client.post(
        "/api/judge/run",
        json={"qid": "ghost-problem", "lang": "cpp", "code": "x"},
        headers=ORIGIN,
    )
    assert response.status_code == 404


def test_check_payload_classification_variants():
    from lc.sites.cn import normalize_check_payload

    ac = normalize_check_payload({"state": "FINISHED", "status_msg": "", "run_success": True})
    assert ac["status_key"] == "accepted"
    wa = normalize_check_payload(
        {
            "state": "FINISHED",
            "status_msg": "Wrong Answer",
            "total_correct": 30,
            "total_testcases": 57,
            "code_answer": ["[0,1]"],
            "expected_output": ["[3,2,4]"],
            "memory": 42000,
        }
    )
    assert wa["status_key"] == "wrong_answer"
    assert wa["expected_outputs"] == ["[3,2,4]"]
    ce = normalize_check_payload({"state": "FINISHED", "status_msg": "Compile Error", "compile_error": "err line"})
    assert ce["status_key"] == "compile_error"
    running = normalize_check_payload({"state": "STARTED"})
    assert running["finished"] is False


def test_check_payload_interpret_style_without_state_counts_as_finished():
    from lc.sites.cn import normalize_check_payload

    interpret_done = normalize_check_payload({
        "run_success": True,
        "code_answer": ["[0,1]"],
        "code_output": [],
        "std_output_list": [],
    })
    assert interpret_done["finished"] is True
    assert interpret_done["status_key"] == "accepted"

    interpret_err = normalize_check_payload({"compile_error": "oops"})
    assert interpret_err["finished"] is True
    assert interpret_err["status_key"] == "compile_error"

    empty_pending = normalize_check_payload({"foo": 1})
    assert empty_pending["finished"] is False
