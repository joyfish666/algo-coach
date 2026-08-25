import json

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from server import api as api_module


ORIGIN = {"Origin": "http://localhost:5173"}


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.headers = {}
        self._payload = payload

    def json(self):
        return self._payload


class FakeImportAdapter:
    def __init__(self, items):
        self.items = items

    def fetch_recent_submissions(self, limit):
        return [dict(item) for item in self.items][: max(1, min(limit, 20))]


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ALGOCOACH_HOME", str(home))
    auth.reset_state()
    api_module._archive = None
    yield
    auth.reset_state()
    api_module._archive = None


@pytest.fixture
def client():
    return TestClient(api_module.app, base_url="http://127.0.0.1:8000")


def seed_cache(rows=None):
    import lc.config as config

    payload = {
        "schema_version": 1,
        "synced_at": None,
        "total": len(rows or []),
        "problems": rows if rows is not None else [
            {
                "slug": "two-sum", "frontend_id": "1", "title_cn": "两数之和",
                "difficulty": "easy", "category": "Algorithms",
                "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}],
            },
            {
                "slug": "lrn", "frontend_id": "146", "title_cn": "LRU 缓存",
                "difficulty": "medium", "category": "Algorithms",
                "tags": [{"slug": "design", "name_zh": "设计", "name_en": "Design"}],
            },
        ],
    }
    cache_path = config.problems_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


def test_analyze_stats_without_llm(client):
    seed_cache()
    archive = api_module.get_archive()
    archive.append({
        "schema": 1, "timestamp": "2026-08-23T00:00:01+00:00", "slug": "two-sum",
        "frontend_id": "1", "submission_id": "1", "lang": "cpp", "status": "wrong_answer",
        "runtime_display": "", "runtime_percentile": None, "memory_display": "",
        "memory_percentile": None, "total_correct": 30, "total_testcases": 57,
        "outputs": [], "expected_outputs": [], "compile_error": "", "runtime_error": "",
        "difficulty": "easy", "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}],
        "category": "Algorithms",
    })
    archive.append({
        "schema": 1, "timestamp": "2026-08-23T00:00:02+00:00", "slug": "two-sum",
        "frontend_id": "1", "submission_id": "2", "lang": "cpp", "status": "accepted",
        "runtime_display": "50 ms", "runtime_percentile": 80, "memory_display": "41 MB",
        "memory_percentile": 60, "total_correct": 57, "total_testcases": 57,
        "outputs": [], "expected_outputs": [], "compile_error": "", "runtime_error": "",
        "difficulty": "easy", "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}],
        "category": "Algorithms",
    })
    archive.append({
        "schema": 1, "timestamp": "2026-08-23T00:00:03+00:00", "slug": "lrn",
        "frontend_id": "146", "submission_id": "3", "lang": "cpp", "status": "wrong_answer",
        "runtime_display": "", "runtime_percentile": None, "memory_display": "",
        "memory_percentile": None, "total_correct": 40, "total_testcases": 22,
        "outputs": [], "expected_outputs": [], "compile_error": "", "runtime_error": "",
        "difficulty": "medium", "tags": [{"slug": "design", "name_zh": "设计", "name_en": "Design"}],
        "category": "Algorithms",
    })

    response = client.post("/api/analyze", json={"use_llm": False}, headers=ORIGIN)
    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["solved_total"] == 1
    assert body["stats"]["by_difficulty"]["easy"] == 1
    assert body["stats"]["attempts_total"] == 3
    assert body["ai_report"] is None
    assert body["ai_configured"] is False

    tag_slugs = [tag["slug"] for tag in body["tags"]]
    assert tag_slugs[0] == "design"
    assert tag_slugs[1] == "array"

    recs = [r["slug"] for r in body["recommendations"]]
    assert "two-sum" not in recs
    assert "lrn" in recs


def test_analyze_reports_ai_configured_without_generating(client):
    # regression: ai_configured used to be computed only inside the
    # use_llm branch, so the initial load (use_llm=false) always claimed
    # the LLM was unconfigured and the report button never appeared
    seed_cache()
    seed_config_llm(None)
    response = client.post("/api/analyze", json={"use_llm": False}, headers=ORIGIN)
    assert response.status_code == 200
    body = response.json()
    assert body["ai_report"] is None
    assert body["ai_configured"] is True


def test_ask_requires_llm_configured(client):
    response = client.post(
        "/api/ask",
        json={"question": "hi"},
        headers=ORIGIN,
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("LLM")


def test_ask_includes_problem_and_verdict_context(client, monkeypatch):
    seed_config_llm(monkeypatch)
    seed_cache()

    class FakeLLM:
        model = "test-model"

        def chat(self, messages):
            FakeLLM.captured = messages
            return "答案"

    monkeypatch.setattr(api_module, "_build_llm", lambda: FakeLLM())

    archive = api_module.get_archive()
    archive.append({
        "schema": 1, "timestamp": "2026-08-23T00:00:02+00:00", "slug": "two-sum",
        "frontend_id": "1", "submission_id": "2", "lang": "cpp", "status": "accepted",
        "runtime_display": "50 ms", "runtime_percentile": 80, "memory_display": "41 MB",
        "memory_percentile": 60, "total_correct": 57, "total_testcases": 57,
        "outputs": [], "expected_outputs": [], "compile_error": "", "runtime_error": "",
        "difficulty": "easy", "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}],
        "category": "Algorithms",
    })

    response = client.post(
        "/api/ask",
        json={
            "question": "为什么我上次超时？",
            "history": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好！"}],
            "qid": "two-sum",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "答案"
    system_message = FakeLLM.captured[0]["content"]
    assert "两数之和" in system_message
    assert "accepted" in system_message
    roles = [m["role"] for m in FakeLLM.captured]
    assert roles[-1] == "user"


def seed_config_llm(monkeypatch):
    import lc.config as config

    data = dict(config.DEFAULTS)
    data.update({"llm_api_key": "sk-test", "llm_base_url": "https://llm.test/v1"})
    config.save(data)


def test_ask_trims_history_to_twelve(client, monkeypatch):
    seed_config_llm(monkeypatch)

    class FakeLLM:
        model = "m"

        def chat(self, messages):
            FakeLLM.captured = messages
            return "ok"

    monkeypatch.setattr(api_module, "_build_llm", lambda: FakeLLM())
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
        for i in range(20)
    ]
    client.post("/api/ask", json={"question": "?", "history": history}, headers=ORIGIN)
    non_system = FakeLLM.captured[1:]
    assert len(non_system) == 13
    assert non_system[0]["content"] == "msg8"


def test_import_site_dedupes_by_submission_id(client, monkeypatch):
    seed_cache()
    items = [
        {"submission_id": "100", "slug": "two-sum", "frontend_id": "1",
         "title_cn": "", "title_en": "", "status": "Accepted", "lang": "cpp",
         "timestamp": "1755900000"},
        {"submission_id": "101", "slug": "lrn", "frontend_id": "146",
         "title_cn": "", "title_en": "", "status": "Wrong Answer", "lang": "cpp",
         "timestamp": "1755900100"},
    ]
    monkeypatch.setattr(api_module, "create_adapter", lambda: FakeImportAdapter(items))

    first = client.post("/api/archive/import-site", json={"limit": 20}, headers=ORIGIN)
    assert first.status_code == 200
    assert first.json() == {"imported": 2, "skipped": 0}

    second = client.post("/api/archive/import-site", json={"limit": 20}, headers=ORIGIN)
    assert second.json()["skipped"] == 2

    records = client.get("/api/archive/recent?limit=10", headers=ORIGIN).json()["records"]
    by_sid = {r["submission_id"]: r for r in records}
    assert by_sid["100"]["status"] == "accepted"
    assert by_sid["101"]["status"] == "wrong_answer"
    assert by_sid["100"]["difficulty"] == "easy"


def test_import_site_appends_in_chronological_order(client, monkeypatch):
    """Regression: the site feed is newest-first, but Archive.query derives
    its listing from file append order - appending in feed order put the
    batch's oldest record in the newest position once truncated."""
    seed_cache()
    items = [
        {"submission_id": "900", "slug": "two-sum", "frontend_id": "1",
         "title_cn": "", "title_en": "", "status": "Accepted", "lang": "cpp",
         "timestamp": "1755900200"},
        {"submission_id": "901", "slug": "lrn", "frontend_id": "146",
         "title_cn": "", "title_en": "", "status": "Accepted", "lang": "cpp",
         "timestamp": "1755900100"},
        {"submission_id": "902", "slug": "two-sum", "frontend_id": "1",
         "title_cn": "", "title_en": "", "status": "Wrong Answer", "lang": "cpp",
         "timestamp": "1755900000"},
    ]
    monkeypatch.setattr(api_module, "create_adapter", lambda: FakeImportAdapter(items))

    response = client.post("/api/archive/import-site", json={"limit": 20}, headers=ORIGIN)
    assert response.status_code == 200

    from lc.config import archive_path

    lines = archive_path().read_text(encoding="utf-8").strip().splitlines()
    timestamps = [json.loads(line)["timestamp"] for line in lines]
    assert timestamps == sorted(timestamps)
    # file order (oldest append first) matches the chronological expectation
    assert [json.loads(line)["submission_id"] for line in lines] == ["902", "901", "900"]

    records = client.get("/api/archive/recent?limit=2", headers=ORIGIN).json()["records"]
    # newest-first view starts with the genuinely newest submission
    assert [r["submission_id"] for r in records] == ["900", "901"]


def test_archive_recent_respects_limit(client):
    archive = api_module.get_archive()
    for i in range(6):
        archive.append({
            "schema": 1, "timestamp": f"2026-08-23T00:00:0{i}+00:00", "slug": f"p{i}",
            "frontend_id": str(i), "submission_id": str(i), "lang": "cpp",
            "status": "accepted", "runtime_display": "", "runtime_percentile": None,
            "memory_display": "", "memory_percentile": None, "total_correct": 1,
            "total_testcases": 1, "outputs": [], "expected_outputs": [],
            "compile_error": "", "runtime_error": "", "difficulty": "easy",
            "tags": [], "category": "Algorithms",
        })
    records = client.get("/api/archive/recent?limit=3", headers=ORIGIN).json()["records"]
    assert [r["submission_id"] for r in records] == ["5", "4", "3"]
