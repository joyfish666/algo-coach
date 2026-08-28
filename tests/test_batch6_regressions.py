"""Batch-6 root-cause regressions: config write mutex, Windows atomic-rename
retry, lock-window robustness, degrade-on-persist-failure policies, and the
last-used-language workbench resume."""

import threading

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
import lc.config as config
import lc.problems as problems
from lc.atomicio import atomic_write_text
from lc.exceptions import RateLimitError
from server import api as api_module

ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ALGOCOACH_HOME", str(home))
    auth.reset_state()
    api_module.reset_app_state()
    yield
    auth.reset_state()
    api_module.reset_app_state()


@pytest.fixture
def client():
    return TestClient(api_module.app, base_url="http://127.0.0.1:8000")


# ---------------------------------------------------------------------------
# lc.atomicio: Windows sharing-violation retry


def test_atomic_write_retries_replace_on_permission_error(tmp_path, monkeypatch):
    """On Windows os.replace raises PermissionError while any thread holds the
    target open (no FILE_SHARE_DELETE); a reader mid-request used to turn a
    routine persist into a 500. The primitive must absorb short collisions."""
    target = tmp_path / "data.json"
    target.write_text("old", encoding="utf-8")

    real_replace = __import__("os").replace
    failures = {"count": 2}

    def flaky_replace(src, dst):
        if failures["count"] > 0:
            failures["count"] -= 1
            raise PermissionError("sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr("lc.atomicio.os.replace", flaky_replace)
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_write_gives_up_after_bounded_retries(tmp_path, monkeypatch):
    target = tmp_path / "data.json"
    monkeypatch.setattr(
        "lc.atomicio.os.replace", lambda *_a, **_k: (_ for _ in ()).throw(PermissionError())
    )
    monkeypatch.setattr("lc.atomicio._REPLACE_RETRY_DELAY", 0.0)
    with pytest.raises(PermissionError):
        atomic_write_text(target, "new")
    # no .tmp litter left behind on the failure path
    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_config_saves_do_not_lose_updates(tmp_path):
    """Two whole-file writers racing used to be resolved by whoever wrote
    last, with no mutual exclusion at all; the config lock must serialize the
    swaps so both payloads land intact in some order (not interleaved)."""
    results = []

    def writer(value):
        data = dict(config.DEFAULTS)
        data["llm_model"] = value
        config.save(data, path=tmp_path / "config.toml")
        results.append(config.load(tmp_path / "config.toml")["llm_model"])

    threads = [threading.Thread(target=writer, args=(f"model-{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 8
    # every save fully landed: the final read must be exactly one writer's
    # payload, never a torn mixture
    assert config.load(tmp_path / "config.toml")["llm_model"].startswith("model-")


# ---------------------------------------------------------------------------
# config.toml writers vs the data wipe: no cookie resurrection


def test_rotation_persist_does_not_resurrect_after_wipe(client):
    """Regression: clear_local_data deleted config.toml, but a rotation
    persist that had already passed its still-current check could win the
    lock afterwards and write the erased cookie back into a fresh config."""
    seed = dict(config.DEFAULTS)
    seed["cookie"] = "csrftoken=t; LEETCODE_SESSION=s1234567890"
    config.save(seed)

    response = client.delete("/api/local-data", headers=ORIGIN)
    assert response.status_code == 200
    assert not config.config_path().exists()

    # simulate a rotation response from the OLD client racing the wipe
    stale_client = auth.configure("csrftoken=t; LEETCODE_SESSION=s9876543210")
    auth.reset_state()  # what clear_local_data does before deleting
    auth._persist_rotated_cookies(stale_client)

    stored = config.load()
    assert stored.get("cookie") != "csrftoken=t; LEETCODE_SESSION=s9876543210"


def test_settings_save_survives_concurrent_rotation_persist():
    """A rotation persist wrote its stale whole-file snapshot after a settings
    save and silently reverted it; both writers now share config.update_lock,
    so whichever critical section runs second still sees the other's field."""
    order = []

    real_save = config.save

    def tracked_save(payload, path=None):
        order.append("save")
        return real_save(payload, path)

    def settings_writer():
        with config.update_lock():
            order.append("settings-enter")
            current = config.effective_config()
            current["workspace_root"] = "/tmp/ws"
            tracked_save(current)
            order.append("settings-exit")

    def rotation_writer():
        with config.update_lock():
            order.append("rotation-enter")
            current = config.effective_config()
            current["csrf_token"] = "rotated"
            tracked_save(current)
            order.append("rotation-exit")

    first = threading.Thread(target=settings_writer)
    second = threading.Thread(target=rotation_writer)
    first.start()
    second.start()
    first.join()
    second.join()

    stored = config.load()
    assert stored["workspace_root"] == "/tmp/ws"
    assert stored["csrf_token"] == "rotated"
    # the critical sections cannot interleave
    assert order.index("settings-enter") < order.index("settings-exit")
    assert order.index("rotation-enter") < order.index("rotation-exit")


# ---------------------------------------------------------------------------
# env overrides share the range policy


def test_validate_environment_enforces_range_bounds(monkeypatch):
    monkeypatch.setenv("ALGOCOACH_REQUEST_INTERVAL", "0.01")
    with pytest.raises(ValueError) as exc_info:
        config.validate_environment()
    assert "ALGOCOACH_REQUEST_INTERVAL" in str(exc_info.value)

    monkeypatch.setenv("ALGOCOACH_REQUEST_INTERVAL", "2.0")
    monkeypatch.setenv("ALGOCOACH_LLM_TIMEOUT", "0")
    with pytest.raises(ValueError):
        config.validate_environment()


# ---------------------------------------------------------------------------
# judge submit degrades when the local archive cannot be written


def test_submit_returns_verdict_when_archive_append_fails(client, monkeypatch):
    """The submit succeeded on the site and cannot be replayed; an OSError on
    the local append used to mask it as a 500 and invited a duplicate."""
    directory = problems.problem_dir_for({"slug": "two-sum", "frontend_id": "1"})
    directory.mkdir(parents=True, exist_ok=True)
    problems.save_meta(directory, {"internal_question_id": "1"})
    cache = {"schema_version": 1, "synced_at": None, "total": 0, "problems": []}
    problems.save_problems(cache)

    class FailingArchive:
        def append(self, record):
            raise OSError("disk full")

        def has_submission(self, submission_id):
            return False

    monkeypatch.setattr(api_module, "get_archive", lambda: FailingArchive())

    class FakeAdapter:
        def fetch_question_detail(self, slug):
            return {"slug": slug, "internal_question_id": "1"}

    monkeypatch.setattr(api_module, "create_adapter", lambda: FakeAdapter())

    from lc import judge as judge_module

    def fake_judge_submit(adapter, **kwargs):
        return {"status_key": "accepted", "submission_id": "s1", "total_correct": 1}

    monkeypatch.setattr(judge_module, "judge_submit", fake_judge_submit)

    response = client.post(
        "/api/judge/submit",
        json={"qid": "two-sum", "lang": "cpp", "code": "int main(){}"},
        headers=ORIGIN,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status_key"] == "accepted"
    assert body["archived"] is False


# ---------------------------------------------------------------------------
# RateLimitError carries Retry-After through the API boundary


def test_rate_limit_error_maps_to_429_with_retry_after_header(client, monkeypatch):
    def boom(cookie):
        raise RateLimitError("slow down", retry_after=12.0, detail={"context": "validate"})

    monkeypatch.setattr(api_module, "validate_cookie_standalone", boom)
    response = client.post(
        "/api/setup/validate-cookie", json={"cookie": "x"}, headers=ORIGIN
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "12"


def test_daily_endpoint_requires_configuration(client):
    """The happy path had coverage; the unconfigured 400 never did. The
    reply must carry the message_key so the UI language, not the backend
    process locale, decides the wording."""
    response = client.get("/api/daily")
    assert response.status_code == 400
    assert response.json()["detail"]["message_key"] == "cookie_missing"


# ---------------------------------------------------------------------------
# workbench state: last-used language resume + transient read degrade


def _write_solution(directory, language, code):
    from lc.langs import extension_for

    atomic_write_text(directory / f"solution{extension_for(language)}", code, newline="")


def test_read_problem_state_resumes_last_used_language(tmp_path):
    """Reopening a problem used to land in the config default's (usually
    empty) editor: neither side remembered which language was last in play."""
    directory = tmp_path
    _write_solution(directory, "cpp", "// old cpp")
    _write_solution(directory, "python3", "# newest python work")

    state = problems.read_problem_state(directory, default_language="cpp")
    assert state["language"] == "python3"
    assert state["code"] == "# newest python work"
    assert "python3" in state["languages_available"]


def test_read_problem_state_falls_back_to_default_when_single_template(tmp_path):
    directory = tmp_path
    _write_solution(directory, "cpp", "// template")
    state = problems.read_problem_state(directory, default_language="cpp")
    assert state["language"] == "cpp"
    assert state["code"] == "// template"


def test_read_problem_state_tolerates_transient_read_errors(tmp_path, monkeypatch):
    """statement/code/testcases reads had no OSError guard while sibling
    reads in the same function degraded to empty - a Windows sharing
    violation on one file turned a plain GET into a 500."""
    (tmp_path / "statement.md").write_text("hello", encoding="utf-8")
    real_read_text = type(tmp_path).read_text

    def flaky_read(self, *args, **kwargs):
        if self.name == "statement.md":
            raise PermissionError("sharing violation")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), "read_text", flaky_read)
    state = problems.read_problem_state(tmp_path, default_language="cpp")
    assert state["statement_markdown"] == ""


# ---------------------------------------------------------------------------
# status payload drives the AI gate


def test_status_exposes_llm_configured(client):
    body = client.get("/api/status").json()
    assert body["llm_configured"] is False

    seed = dict(config.DEFAULTS)
    seed["llm_api_key"] = "sk-abcdef123456"
    seed["llm_base_url"] = "https://api.x.com/v1"
    config.save(seed)
    body = client.get("/api/status").json()
    assert body["llm_configured"] is True
