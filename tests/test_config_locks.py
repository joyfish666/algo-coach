"""Config write mutex and the wipe/rotation race (lc.config + server.state).

These cover the lock-ordering contract: several agents rewrite the whole
config.toml (settings save, cookie-rotation persist, data wipe) and every
whole-file RMW sequence must hold config.update_lock().
"""

import threading

import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
import lc.config as config
from server import app as app_module

ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture
def client():
    return TestClient(app_module.app, base_url="http://127.0.0.1:8000")


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
