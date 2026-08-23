import json
import time

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from server import api as api_module


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.headers = {}
        self._payload = payload

    def json(self):
        return self._payload


class FakeAdapter:
    def __init__(self, pages=None, total=0, detail=None, daily=None, validate=None, gate=None):
        self.pages = pages or []
        self.total = total
        self.detail = detail
        self.daily = daily
        self.validate_result = validate
        self.gate = gate
        self.calls = []

    def fetch_problem_list_page(self, skip, limit):
        self.calls.append(("page", skip))
        if self.gate is not None:
            if skip >= limit:
                self.gate.ready.set()
                self.gate.release.wait(timeout=5)
        return {"total": self.total, "problems": self.pages[skip // limit] if skip < len(self.pages) * limit else []}

    def fetch_question_detail(self, slug):
        self.calls.append(("detail", slug))
        return self.detail

    def fetch_daily_question(self):
        self.calls.append(("daily",))
        return self.daily

    def validate_cookie(self):
        self.calls.append(("validate",))
        if isinstance(self.validate_result, Exception):
            raise self.validate_result
        return self.validate_result


class Gate:
    def __init__(self):
        self.ready = __import__("threading").Event()
        self.release = __import__("threading").Event()


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


def seed_config(**overrides):
    import lc.config as config

    data = dict(config.DEFAULTS)
    data.update(overrides)
    config.save(data)


def test_status_reports_unconfigured(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["version"] == "0.1.0"
    assert "sync" in body


def test_origin_guard_blocks_post_without_origin(client):
    response = client.post("/api/setup/validate-cookie", json={"cookie": "x"})
    assert response.status_code == 403


def test_origin_guard_allows_get_without_origin(client):
    response = client.get("/api/problems")
    assert response.status_code == 200


def test_host_guard_rejects_foreign_host(client):
    response = client.get("/api/status", headers={"Host": "evil.example:8000"})
    assert response.status_code == 403


def test_settings_roundtrip_masks_secrets_and_rebuilds_session(client):
    seed_config()
    response = client.put(
        "/api/settings",
        json={
            "cookie": "csrftoken=tok123; LEETCODE_SESSION=sessionvalue123456",
            "llm_api_key": "sk-abcdef123456",
            "theme": "dark",
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert "sessionvalue123456" not in body["cookie_masked"]
    assert "sk-abcdef123456" not in body["llm_api_key_masked"]
    assert body["theme"] == "dark"

    session = auth.get_session()
    assert session.cookies.get("csrftoken") == "tok123"

    fetched = client.get("/api/settings").json()
    assert fetched["configured"] is True


def test_validate_cookie_endpoint_success(client, monkeypatch):
    def fake_standalone(cookie):
        assert cookie == "good-cookie"
        return {"signed_in": True, "premium": False}

    monkeypatch.setattr(api_module, "validate_cookie_standalone", fake_standalone)
    response = client.post(
        "/api/setup/validate-cookie", json={"cookie": "good-cookie"}, headers=ORIGIN
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_problems_empty_then_seeded(client):
    assert client.get("/api/problems").json()["problems"] == []
    import lc.config as config

    seed_payload = {
        "schema_version": 1,
        "synced_at": "2026-08-23T00:00:00+00:00",
        "total": 1,
        "problems": [
            {
                "slug": "two-sum",
                "frontend_id": "1",
                "title_cn": "两数之和",
                "difficulty": "easy",
                "paid_only": False,
                "category": "Algorithms",
                "tags": [],
            }
        ],
    }
    cache_path = config.problems_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(seed_payload), encoding="utf-8")
    body = client.get("/api/problems").json()
    assert body["total"] == 1
    assert body["problems"][0]["slug"] == "two-sum"


def test_sync_flow_with_progress_and_conflict(client, monkeypatch, tmp_path):
    pages = [
        [{"slug": f"p{i}", "frontend_id": str(i), "title_cn": "", "difficulty": "easy",
          "paid_only": False, "category": "Algorithms", "tags": []} for i in range(100)],
        [{"slug": f"q{i}", "frontend_id": str(100 + i), "title_cn": "", "difficulty": "easy",
          "paid_only": False, "category": "Algorithms", "tags": []} for i in range(50)],
    ]
    gate = Gate()

    def factory():
        return FakeAdapter(pages=pages, total=150, gate=gate)

    monkeypatch.setattr(api_module, "create_adapter", factory)
    response = client.post("/api/problems/sync", headers=ORIGIN)
    assert response.status_code == 200
    assert response.json()["started"] is True

    assert gate.ready.wait(timeout=5)
    conflict = client.post("/api/problems/sync", headers=ORIGIN)
    assert conflict.status_code == 409

    gate.release.set()
    deadline = time.time() + 5
    while time.time() < deadline:
        progress = client.get("/api/problems/sync/progress").json()
        if not progress["running"]:
            break
        time.sleep(0.02)
    assert progress["running"] is False
    assert progress["fetched"] == 150

    body = client.get("/api/problems").json()
    assert body["total"] == 150


def test_daily_endpoint(client, monkeypatch):
    daily_row = {"slug": "two-sum", "frontend_id": "1", "date": "2026-08-23"}

    def factory():
        return FakeAdapter(daily=daily_row)

    monkeypatch.setattr(api_module, "create_adapter", factory)
    response = client.get("/api/daily")
    assert response.status_code == 200
    assert response.json()["slug"] == "two-sum"


DETAIL_FIXTURE = {
    "slug": "two-sum",
    "frontend_id": "1",
    "title_en": "Two Sum",
    "title_cn": "两数之和",
    "difficulty": "easy",
    "paid_only": False,
    "category": "Algorithms",
    "tags": [],
    "statement_html": "<p>题面内容</p>",
    "hints": ["哈希表"],
    "sample_test_case": "[2,7,11,15]\n9",
    "code_snippets": [
        {"lang_slug": "cpp", "code": "class Solution {};\n"},
        {"lang_slug": "python3", "code": "# py\n"},
    ],
}


def test_open_problem_materializes_and_serves_offline(client, monkeypatch):
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)

    first = client.get("/api/problem/two-sum")
    assert first.status_code == 200
    body = first.json()
    assert body["dir"] == "0001-two-sum"
    assert "题面内容" in body["statement_markdown"]
    assert body["testcases"] == "[2,7,11,15]\n9"
    assert body["code"].startswith("class Solution")
    assert body["languages_available"] == ["cpp"]

    detail_calls = [call for call in adapter.calls if call[0] == "detail"]
    assert len(detail_calls) == 1

    second = client.get("/api/problem/two-sum")
    assert second.status_code == 200
    detail_calls = [call for call in adapter.calls if call[0] == "detail"]
    assert len(detail_calls) == 1

    problems_cache = api_module.problems.load_problems()
    assert any(row["slug"] == "two-sum" for row in problems_cache["problems"])


def test_refresh_refetches_detail(client, monkeypatch):
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    client.get("/api/problem/two-sum")
    refreshed = client.get("/api/problem/two-sum?refresh=1")
    assert refreshed.status_code == 200
    detail_calls = [call for call in adapter.calls if call[0] == "detail"]
    assert len(detail_calls) == 2


def test_template_on_demand_then_exists(client, monkeypatch):
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    client.get("/api/problem/two-sum")

    first = client.get("/api/problem/two-sum/template?lang=python3")
    assert first.status_code == 200
    assert first.json()["status"] == "written"

    second = client.get("/api/problem/two-sum/template?lang=python3")
    assert second.json()["status"] == "exists"

    unsupported = client.get("/api/problem/two-sum/template?lang=golang")
    assert unsupported.status_code == 422


def test_put_testcases_writes_file(client, monkeypatch):
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    client.get("/api/problem/two-sum")
    response = client.put(
        "/api/problem/two-sum/testcases",
        json={"content": "[3,3]\n6"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    state = client.get("/api/problem/two-sum").json()
    assert state["testcases"] == "[3,3]\n6"


def test_domain_exception_translated_to_401_shape(client, monkeypatch):
    from lc.exceptions import AuthError

    def fake_standalone(cookie):
        raise AuthError("expired", detail={"shape": "403"})

    monkeypatch.setattr(api_module, "validate_cookie_standalone", fake_standalone)
    response = client.post(
        "/api/setup/validate-cookie", json={"cookie": "bad"}, headers=ORIGIN
    )
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["kind"] == "AuthError"
    assert error["message_key"] == "cookie_invalid"


def test_unknown_problem_returns_404(client, monkeypatch):
    from lc.exceptions import ProblemNotFoundError

    def factory():
        adapter = FakeAdapter()
        adapter.fetch_question_detail = lambda slug: (_ for _ in ()).throw(
            ProblemNotFoundError("missing", detail={"slug": slug})
        )
        return adapter

    monkeypatch.setattr(api_module, "create_adapter", factory)
    response = client.get("/api/problem/does-not-exist")
    assert response.status_code == 404
