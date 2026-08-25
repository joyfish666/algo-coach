import pytest
from fastapi.testclient import TestClient

import lc.auth as auth
from server import api as api_module


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


@pytest.fixture
def fake_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="app"></div></body></html>', encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text("console.log(1)\n", encoding="utf-8")
    return dist


def test_env_override_dist_serves_index(client, monkeypatch, fake_dist):
    monkeypatch.setattr(api_module, "DIST_DIR", fake_dist)
    response = client.get("/")
    assert response.status_code == 200
    assert 'div id="app"' in response.text


def test_spa_deep_links_fall_back_to_index(client, monkeypatch, fake_dist):
    monkeypatch.setattr(api_module, "DIST_DIR", fake_dist)
    for path in ("/problems", "/settings", "/analyze", "/problem/two-sum"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'div id="app"' in response.text


def test_static_assets_served_from_dist(client, monkeypatch, fake_dist):
    monkeypatch.setattr(api_module, "DIST_DIR", fake_dist)
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_traversal_blocked(client, monkeypatch, fake_dist):
    secret = fake_dist.parent / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    monkeypatch.setattr(api_module, "DIST_DIR", fake_dist)
    response = client.get("/../secret.txt")
    assert b"top secret" not in response.content


def test_unknown_api_paths_stay_json(client, monkeypatch, fake_dist):
    monkeypatch.setattr(api_module, "DIST_DIR", fake_dist)
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    # a client typo is not a missing problem: must not leak the misleading
    # problem_not_found copy
    assert "problem" not in str(response.json()["detail"]).lower()


def test_no_dist_json_hint_and_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api_module, "DIST_DIR", None)
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["app"].startswith("AlgoCoach v")
    missing = client.get("/problems")
    assert missing.status_code == 404
