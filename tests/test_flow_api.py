"""Whole-app happy path over the real FastAPI stack, network fully mocked.

setup -> sync -> list -> open workbench -> run -> submit (archived) ->
analyze. Guards the seams between layers that individual unit tests cannot
see: cache rows feeding archive enrichment, workspace materialization
feeding judge context, archive feeding analytics.
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from server import api as api_module

ORIGIN = {"Origin": "http://localhost:5173"}

DETAIL = {
    "slug": "two-sum",
    "internal_question_id": "1001",
    "frontend_id": "1",
    "title_en": "Two Sum",
    "title_cn": "两数之和",
    "difficulty": "easy",
    "paid_only": False,
    "category": "Algorithms",
    "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}],
    "statement_html": "<p>题面</p>",
    "hints": [],
    "sample_test_case": "[2,7,11,15]\n9",
    "example_test_cases": ["[2,7,11,15]\n9", "[3,2,4]\n6"],
    "code_snippets": [{"lang_slug": "cpp", "code": "class Solution {};\n"}],
}

FINISHED_AC = {
    "finished": True,
    "status_key": "accepted",
    "status_msg": "Accepted",
    "runtime_display": "52 ms",
    "runtime_percentile": 88.0,
    "memory_display": "41.2 MB",
    "memory_percentile": 70.0,
    "total_correct": 57,
    "total_testcases": 57,
    "outputs": [],
    "expected_outputs": [],
    "stdout_tail": "",
    "compile_error": "",
    "runtime_error": "",
}


class FlowAdapter:
    def __init__(self):
        self.pages = [
            [
                {"slug": "two-sum", "frontend_id": "1", "title_cn": "两数之和",
                 "difficulty": "easy", "paid_only": False, "category": "Algorithms",
                 "tags": DETAIL["tags"]},
                {"slug": "add-two-num", "frontend_id": "2", "title_cn": "两数相加",
                 "difficulty": "medium", "paid_only": False, "category": "Algorithms",
                 "tags": []},
            ]
        ]
        self.runs = []

    def fetch_problem_list_page(self, skip, limit):
        return {"total": 2, "problems": self.pages[skip // limit] if skip < limit else []}

    def fetch_question_detail(self, slug):
        assert slug == "two-sum"
        return json.loads(json.dumps(DETAIL))

    def run_code(self, slug, question_id, code, lang, input_text):
        self.runs.append({"input": input_text, "question_id": question_id})
        return dict(FINISHED_AC)

    def submit_code(self, slug, question_id, code, lang):
        return "9001"

    def poll_submission(self, submission_id):
        verdict = dict(FINISHED_AC)
        verdict["submission_id"] = submission_id
        return verdict


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


def wait_sync_done(client):
    deadline = time.time() + 5
    while time.time() < deadline:
        progress = client.get("/api/problems/sync/progress").json()
        if not progress["running"]:
            return progress
        time.sleep(0.02)
    raise AssertionError("sync did not finish in time")


def test_full_practice_flow_end_to_end(client, monkeypatch):
    adapter = FlowAdapter()
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)

    # -- setup ---------------------------------------------------------------
    status = client.get("/api/status").json()
    assert status["configured"] is False
    saved = client.put(
        "/api/settings",
        json={
            "cookie": "csrftoken=tok; LEETCODE_SESSION=sess-flow-000123456789",
            "llm_api_key": "sk-flow-key-000123456789",
            "default_language": "cpp",
        },
        headers=ORIGIN,
    )
    assert saved.status_code == 200
    assert client.get("/api/status").json()["configured"] is True

    # -- sync ----------------------------------------------------------------
    assert client.post("/api/problems/sync", headers=ORIGIN).json()["started"] is True
    assert wait_sync_done(client)["error"] is None
    listing = client.get("/api/problems").json()
    assert listing["total"] == 2
    assert [row["slug"] for row in listing["problems"]] == ["two-sum", "add-two-num"]

    # -- open workbench (lazily materializes) ---------------------------------
    opened = client.get("/api/problem/two-sum").json()
    assert opened["dir"] == "0001-two-sum"
    assert opened["code"].startswith("class Solution")
    # both official examples are stored as separate cases
    assert len(opened["cases"]) == 2

    # -- run merges every stored example --------------------------------------
    run_verdict = client.post(
        "/api/judge/run",
        json={"qid": "two-sum", "lang": "cpp", "code": "class Solution {};", "use_local": False},
        headers=ORIGIN,
    ).json()
    assert run_verdict["status_key"] == "accepted"
    assert adapter.runs[0]["input"] == "[2,7,11,15]\n9\n[3,2,4]\n6"

    # -- submit archives with problem metadata --------------------------------
    submitted = client.post(
        "/api/judge/submit",
        json={"qid": "two-sum", "lang": "cpp", "code": "class Solution {};"},
        headers=ORIGIN,
    ).json()
    assert submitted["archived"] is True
    recent = client.get("/api/archive/recent").json()["records"]
    assert recent[0]["slug"] == "two-sum"
    assert recent[0]["difficulty"] == "easy"  # enriched from the synced cache
    assert recent[0]["tags"][0]["slug"] == "array"

    # -- list reflects practice status -----------------------------------------
    row = next(r for r in client.get("/api/problems").json()["problems"]
               if r["slug"] == "two-sum")
    assert row["practice_status"] == "accepted"

    # -- analyze derives stats from the archive --------------------------------
    analysis = client.post("/api/analyze", json={"use_llm": False}, headers=ORIGIN).json()
    assert analysis["stats"]["solved_total"] == 1
    assert analysis["stats"]["by_difficulty"]["easy"] == 1
    array_tag = next(t for t in analysis["tags"] if t["slug"] == "array")
    assert array_tag["solved"] == 1


def test_second_sync_picks_up_site_additions(client, monkeypatch):
    """The API-level face of the resume bug: clicking sync twice must not be a
    silent no-op after the first completed sync."""
    adapter = FlowAdapter()
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)

    client.post("/api/problems/sync", headers=ORIGIN)
    assert wait_sync_done(client)["error"] is None

    adapter.pages[0].append({
        "slug": "brand-new", "frontend_id": "3", "title_cn": "新题",
        "difficulty": "hard", "paid_only": False, "category": "Algorithms", "tags": [],
    })
    client.post("/api/problems/sync", headers=ORIGIN)
    progress = wait_sync_done(client)
    assert progress["error"] is None
    body = client.get("/api/problems").json()
    slugs = [row["slug"] for row in body["problems"]]
    assert "brand-new" in slugs