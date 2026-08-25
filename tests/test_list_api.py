import json

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from server import api as api_module


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
    "code_snippets": [{"lang_slug": "cpp", "code": "class Solution {};\n"}],
}


class FakeAdapter:
    def __init__(self):
        self.detail = json.loads(json.dumps(DETAIL_FIXTURE))

    def fetch_question_detail(self, slug):
        return json.loads(json.dumps(self.detail))


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


@pytest.fixture
def adapter(client, monkeypatch):
    fake = FakeAdapter()
    monkeypatch.setattr(api_module, "create_adapter", lambda: fake)
    return fake


def seed_cache_row(slug="two-sum", frontend_id="1"):
    from lc import problems

    problems.save_problems(
        {
            "schema_version": 1,
            "synced_at": "2026-08-24T00:00:00+00:00",
            "total": 1,
            "problems": [
                {
                    "slug": slug,
                    "frontend_id": frontend_id,
                    "title_cn": "两数之和",
                    "title_en": "Two Sum",
                    "difficulty": "easy",
                    "paid_only": False,
                    "category": "Algorithms",
                    "tags": [],
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# favorites


def test_favorite_roundtrip_reflects_in_problem_list(client, monkeypatch):
    seed_cache_row()
    response = client.put(
        "/api/problem/two-sum/favorite", json={"favorite": True}, headers=ORIGIN
    )
    assert response.status_code == 200
    assert response.json() == {"slug": "two-sum", "favorite": True}

    rows = client.get("/api/problems").json()["problems"]
    assert rows[0]["favorite"] is True

    response = client.put(
        "/api/problem/two-sum/favorite", json={"favorite": False}, headers=ORIGIN
    )
    assert response.json()["favorite"] is False
    rows = client.get("/api/problems").json()["problems"]
    assert "favorite" not in rows[0]


def test_favorite_rejects_unsafe_slug(client):
    # dots are legal in a URL segment but not in our slug charset, so this
    # exercises _require_safe_slug itself (raw "../" gets normalized away
    # by the HTTP client before routing and can never reach the handler)
    response = client.put(
        "/api/problem/two.sum/favorite", json={"favorite": True}, headers=ORIGIN
    )
    assert response.status_code == 400


def test_open_problem_state_carries_favorite_flag(client, monkeypatch):
    seed_cache_row()
    monkeypatch.setattr(api_module, "create_adapter", lambda: FakeAdapter())
    assert client.get("/api/problem/two-sum").json()["favorite"] is False
    client.put("/api/problem/two-sum/favorite", json={"favorite": True}, headers=ORIGIN)
    assert client.get("/api/problem/two-sum").json()["favorite"] is True


# ---------------------------------------------------------------------------
# notes


def test_notes_roundtrip_through_workspace(client, monkeypatch):
    seed_cache_row()
    monkeypatch.setattr(api_module, "create_adapter", lambda: FakeAdapter())
    client.get("/api/problem/two-sum")  # materialize workspace

    saved = client.put(
        "/api/problem/two-sum/notes", json={"content": "# 思路\n双指针"}, headers=ORIGIN
    )
    assert saved.status_code == 200
    state = client.get("/api/problem/two-sum").json()
    assert state["notes"] == "# 思路\n双指针"


def test_notes_on_unknown_problem_returns_404(client):
    seed_cache_row()
    response = client.put(
        "/api/problem/nonexistent/notes", json={"content": "x"}, headers=ORIGIN
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# archive history query


def _append_records(records):
    from lc.archive import Archive
    from lc.config import archive_path

    archive = Archive(archive_path())
    for record in records:
        archive.append(record)


def test_archive_recent_filters_by_qid_newest_first(client):
    _append_records(
        [
            {"schema": 1, "timestamp": "2026-08-20T10:00:00+00:00", "slug": "a", "status": "accepted"},
            {"schema": 1, "timestamp": "2026-08-21T10:00:00+00:00", "slug": "b", "status": "wrong_answer"},
            {"schema": 1, "timestamp": "2026-08-22T10:00:00+00:00", "slug": "a", "status": "accepted"},
        ]
    )
    body = client.get("/api/archive/recent", params={"qid": "a"}).json()
    slugs = [record["slug"] for record in body["records"]]
    assert slugs == ["a", "a"]
    timestamps = [record["timestamp"] for record in body["records"]]
    assert timestamps == sorted(timestamps, reverse=True)

    everything = client.get("/api/archive/recent").json()["records"]
    assert len(everything) == 3
    assert everything[0]["slug"] == "a"


def test_archive_recent_caps_limit_and_validates_qid(client):
    assert client.get("/api/archive/recent", params={"limit": 500}).status_code == 200
    bad = client.get("/api/archive/recent", params={"qid": "../escape"})
    assert bad.status_code == 400


# ---------------------------------------------------------------------------
# ask with attached code


class FakeLLM:
    captured = None
    model = "fake-model"

    def chat(self, messages):
        FakeLLM.captured = messages
        return "ok"


def test_ask_includes_editor_code_when_provided(client, monkeypatch):
    import lc.config as config

    data = dict(config.DEFAULTS)
    data.update({"llm_api_key": "sk-test", "llm_base_url": "https://llm.example"})
    config.save(data)
    monkeypatch.setattr(api_module, "LLMClient", lambda **kwargs: FakeLLM())

    response = client.post(
        "/api/ask",
        json={"question": "哪里错了？", "qid": "two-sum", "code": "int x = 0;", "lang": "cpp"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    system_prompt = FakeLLM.captured[0]["content"]
    assert "int x = 0;" in system_prompt
    assert "cpp" in system_prompt


def test_ask_without_code_keeps_prompt_clean(client, monkeypatch):
    import lc.config as config

    data = dict(config.DEFAULTS)
    data.update({"llm_api_key": "sk-test", "llm_base_url": "https://llm.example"})
    config.save(data)
    FakeLLM.captured = None
    monkeypatch.setattr(api_module, "LLMClient", lambda **kwargs: FakeLLM())

    response = client.post(
        "/api/ask", json={"question": "hello"}, headers=ORIGIN
    )
    assert response.status_code == 200
    system_prompt = FakeLLM.captured[0]["content"]
    assert "当前代码" not in system_prompt


# ---------------------------------------------------------------------------
# unit level: favorites store + archive query robustness


def test_favorites_store_atomic_and_corrupt_tolerant(tmp_path):
    from lc import favorites

    path = tmp_path / "favorites.json"
    assert favorites.load_favorites(path) == set()
    favorites.save_favorites({"two-sum", "add-two-numbers"}, path)
    assert favorites.is_favorite("two-sum", path)
    assert not favorites.is_favorite("sum", path)
    # corrupt payload degrades to empty instead of crashing list rendering
    path.write_text("{not json", encoding="utf-8")
    assert favorites.load_favorites(path) == set()


def test_set_favorite_survives_concurrent_toggles(tmp_path):
    """Regression: set_favorite used to load outside the lock, so concurrent
    toggles of different slugs could clobber each other's write."""
    import threading

    from lc import favorites

    path = tmp_path / "favorites.json"
    slugs = [f"slug-{i}" for i in range(8)]
    threads = [
        threading.Thread(target=favorites.set_favorite, args=(slug, True, path))
        for slug in slugs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    stored = favorites.load_favorites(path)
    assert stored == set(slugs)


def test_archive_query_skips_corrupt_lines(tmp_path):
    from lc.archive import Archive

    archive_path_file = tmp_path / "submissions.jsonl"
    good1 = json.dumps({"slug": "a", "timestamp": "2026-08-20T10:00:00+00:00"})
    good2 = json.dumps({"slug": "a", "timestamp": "2026-08-21T10:00:00+00:00"})
    archive_path_file.write_text(f"{good1}\n{{broken\n{good2}\n\n", encoding="utf-8")
    archive = Archive(archive_path_file)
    records = archive.query(slug="a", limit=10)
    assert [record["timestamp"] for record in records] == [
        "2026-08-21T10:00:00+00:00",
        "2026-08-20T10:00:00+00:00",
    ]
