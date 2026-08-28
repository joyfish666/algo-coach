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
        },
        headers=ORIGIN,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert "sessionvalue123456" not in body["cookie_masked"]
    assert "sk-abcdef123456" not in body["llm_api_key_masked"]
    # only the tail may leak, never a usable prefix
    assert not body["llm_api_key_masked"].startswith("sk-abcd")
    assert "theme" not in body
    assert "ui_language" not in body

    session = auth.get_session()
    assert session.cookies.get("csrftoken") == "tok123"

    fetched = client.get("/api/settings").json()
    assert fetched["configured"] is True


def test_settings_reject_out_of_range_request_interval(client):
    seed_config()
    for bad in (0.0, 0.1, 61.0, -2.0):
        response = client.put(
            "/api/settings", json={"request_interval": bad}, headers=ORIGIN
        )
        assert response.status_code == 422, bad
    ok = client.put("/api/settings", json={"request_interval": 1.5}, headers=ORIGIN)
    assert ok.status_code == 200
    assert ok.json()["request_interval"] == 1.5


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


def test_problems_list_enriches_practice_status(client):
    import lc.config as config

    cache_rows = [
        {"slug": "two-sum", "frontend_id": "1", "title_cn": "两数之和",
         "difficulty": "easy", "paid_only": False, "category": "Algorithms", "tags": []},
        {"slug": "add-two-num", "frontend_id": "2", "title_cn": "两数相加",
         "difficulty": "medium", "paid_only": False, "category": "Algorithms", "tags": []},
    ]
    cache_path = config.problems_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({
        "schema_version": 1, "synced_at": None,
        "total": len(cache_rows), "problems": cache_rows,
    }), encoding="utf-8")

    archive = api_module.get_archive()
    archive.append({
        "schema": 1, "timestamp": "2026-08-23T10:00:00+00:00", "slug": "two-sum",
        "frontend_id": "1", "submission_id": "s1", "lang": "cpp", "status": "accepted",
        "runtime_display": "", "runtime_percentile": None, "memory_display": "",
        "memory_percentile": None, "total_correct": 57, "total_testcases": 57,
        "outputs": [], "expected_outputs": [], "compile_error": "", "runtime_error": "",
        "difficulty": "easy", "tags": [], "category": "Algorithms",
    })
    body = client.get("/api/problems").json()
    row = next(r for r in body["problems"] if r["slug"] == "two-sum")
    assert row["practice_status"] == "accepted"
    assert row["last_practice_at"] == "2026-08-23T10:00:00+00:00"
    other = next(r for r in body["problems"] if r["slug"] == "add-two-num")
    assert "practice_status" not in other


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


def test_post_refresh_refetches_detail(client, monkeypatch):
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    client.get("/api/problem/two-sum")
    refreshed = client.post("/api/problem/two-sum/refresh", headers=ORIGIN)
    assert refreshed.status_code == 200
    detail_calls = [call for call in adapter.calls if call[0] == "detail"]
    assert len(detail_calls) == 2


def test_get_refresh_query_no_longer_triggers_fetch(client, monkeypatch):
    """GET is side-effect free now: ?refresh=1 must not refetch remotely."""
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    client.get("/api/problem/two-sum")
    response = client.get("/api/problem/two-sum?refresh=1")
    assert response.status_code == 200
    detail_calls = [call for call in adapter.calls if call[0] == "detail"]
    assert len(detail_calls) == 1


def test_require_safe_slug_rejects_traversal_payloads():
    from fastapi import HTTPException

    for bad in ["..", "../solution", r"..\..\target", "a/b", ".hidden", "%2e%2e", "", None]:
        with pytest.raises(HTTPException) as excinfo:
            api_module._require_safe_slug(bad)
        assert excinfo.value.status_code == 400
    assert api_module._require_safe_slug("two-sum") == "two-sum"


def test_get_problem_rejects_traversal_qid_over_http(client):
    # %5C survives httpx untouched and decodes to a single-segment backslash
    response = client.get("/api/problem/a%5Cb")
    assert response.status_code == 400


def test_put_solution_rejects_windows_traversal_qid(client):
    response = client.put(
        "/api/problem/a%5Cb/solution",
        json={"lang": "cpp", "code": "x"},
        headers=ORIGIN,
    )
    assert response.status_code == 400


def test_host_guard_accepts_ipv6_loopback(client):
    response = client.get("/api/status", headers={"Host": "[::1]:8000"})
    assert response.status_code == 200


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


def test_spa_fallback_never_serves_sibling_of_dist(tmp_path, monkeypatch):
    """Regression: 'dist-old/x' passed the old startswith('...dist') check."""
    from fastapi import HTTPException

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    sibling_file = tmp_path / "dist-old" / "secret.txt"
    sibling_file.parent.mkdir()
    sibling_file.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(api_module, "DIST_DIR", dist)

    # asset-shaped paths (and traversal payloads) must 404 instead of being
    # rewritten to index.html: a missing hashed chunk answered with HTML used
    # to surface as an opaque MIME error and silently kill every navigation
    # from a stale tab
    with pytest.raises(HTTPException) as excinfo:
        api_module.spa_fallback("../dist-old/secret.txt")
    assert excinfo.value.status_code == 404
    assert str(sibling_file) not in str(excinfo.value)

    with pytest.raises(HTTPException) as stale_info:
        api_module.spa_fallback("assets/ProblemDetail-deadbeef.js")
    assert stale_info.value.status_code == 404

    normal = api_module.spa_fallback("index.html")
    assert str(dist / "index.html") == str(getattr(normal, "path", ""))

    root = api_module.spa_fallback("")
    assert str(dist / "index.html") == str(getattr(root, "path", ""))


# ---------------------------------------------------------------------------
# DELETE /api/local-data (most destructive endpoint)


def test_local_data_erase_removes_files_keeps_lock_and_resets_auth(client):
    from lc.config import INSTANCE_LOCK_NAME, app_dir, archive_path
    from lc.archive import Archive

    seed_config(cookie="csrftoken=t; LEETCODE_SESSION=s1234567890")
    root = app_dir()
    (root / INSTANCE_LOCK_NAME).write_text("lock", encoding="utf-8")
    Archive(archive_path()).append({"slug": "two-sum", "status": "accepted"})
    assert (root / "submissions.jsonl").exists()
    assert client.get("/api/status").json()["configured"] is True

    response = client.delete("/api/local-data", headers=ORIGIN)
    assert response.status_code == 200
    cleared = response.json()["cleared"]
    assert "config.toml" in cleared
    assert "submissions.jsonl" in cleared
    # the live lock file must survive, or the single-instance guard breaks
    assert (root / INSTANCE_LOCK_NAME).exists()

    # auth state reset: the app reports unconfigured without re-seeding
    assert client.get("/api/status").json()["configured"] is False


def test_local_data_rejects_while_sync_running(client, monkeypatch):
    monkeypatch.setattr(
        api_module._sync_engine, "progress", lambda: {"running": True}
    )
    response = client.delete("/api/local-data", headers=ORIGIN)
    assert response.status_code == 409


def test_local_data_erase_resets_sync_engine_state(client):
    """Regression: stale engine accumulators survived the wipe and surfaced
    as a bogus "resumable" progress snapshot pointing at deleted data."""
    class TinyAdapter:
        def fetch_problem_list_page(self, skip, limit):
            return {"total": 0, "problems": []}

    assert api_module._sync_engine.run_blocking(TinyAdapter()) is None
    before = api_module._sync_engine.progress()
    assert before["started_at"] is not None

    response = client.delete("/api/local-data", headers=ORIGIN)
    assert response.status_code == 200

    after = api_module._sync_engine.progress()
    assert after["started_at"] is None
    assert after["finished_at"] is None
    assert after["resumable"] is False
    assert after["fetched"] == 0


def test_template_defaults_to_configured_language(client, monkeypatch):
    seed_config(default_language="python3")
    adapter = FakeAdapter(detail=DETAIL_FIXTURE)
    monkeypatch.setattr(api_module, "create_adapter", lambda: adapter)
    client.get("/api/problem/two-sum")

    response = client.get("/api/problem/two-sum/template")
    assert response.status_code == 200
    assert response.json()["lang"] == "python3"


def test_settings_rejects_explicit_null_cookie(client):
    seed_config(cookie="csrftoken=t; LEETCODE_SESSION=s1234567890")
    before = client.get("/api/settings").json()["cookie_masked"]

    response = client.put("/api/settings", json={"cookie": None}, headers=ORIGIN)
    assert response.status_code == 422
    # the current cookie is untouched by the rejected request
    assert client.get("/api/settings").json()["cookie_masked"] == before


def test_settings_reject_explicit_null_for_any_field(client):
    """Regression: only cookie used to be null-guarded. A null elsewhere was
    a TypeError 500 for numeric fields and, worse, the literal string "None"
    silently written into config.toml for text fields."""
    seed_config()
    for payload in (
        {"request_interval": None},
        {"llm_timeout": None},
        {"llm_base_url": None},
        {"llm_model": None},
        {"workspace_root": None},
        {"default_language": None},
        {"llm_api_key": None},
    ):
        response = client.put("/api/settings", json=payload, headers=ORIGIN)
        assert response.status_code == 422, payload

    import lc.config as config

    stored = config.load()
    for key in ("llm_base_url", "llm_model", "workspace_root", "default_language"):
        assert stored.get(key) != "None", key


def test_settings_llm_timeout_roundtrip_and_bounds(client):
    seed_config()
    ok = client.put("/api/settings", json={"llm_timeout": 30}, headers=ORIGIN)
    assert ok.status_code == 200
    assert ok.json()["llm_timeout"] == 30.0
    fetched = client.get("/api/settings").json()
    assert fetched["llm_timeout"] == 30.0
    for bad in (4, 601, -1):
        response = client.put("/api/settings", json={"llm_timeout": bad}, headers=ORIGIN)
        assert response.status_code == 422, bad


def test_mask_secret_short_values_stay_fully_masked():
    assert api_module.mask_secret("") == ""
    assert api_module.mask_secret("short") == "***"
    # 15 chars: revealing tail-4 would expose >25% of the entropy
    assert api_module.mask_secret("x" * 15) == "***"
    masked = api_module.mask_secret("y" * 32)
    assert masked.startswith("…")
    assert "yyyy" not in masked[:-1] or masked.endswith("yyyy")
