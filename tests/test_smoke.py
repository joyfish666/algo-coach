import fastapi.testclient

import lc
from lc.exceptions import AuthError, JudgeError
from lc.langs import DEFAULT_LANGUAGE, LANGUAGE_REGISTRY


def test_package_version():
    assert lc.__version__ == "0.1.0"


def test_language_registry_defaults():
    assert DEFAULT_LANGUAGE == "cpp"
    assert LANGUAGE_REGISTRY == {"cpp": ".cpp", "python3": ".py", "java": ".java"}


def test_exception_hierarchy():
    assert issubclass(AuthError, Exception)
    assert issubclass(JudgeError, Exception)


def test_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOCOACH_HOME", str(tmp_path / "home"))

    from fastapi.testclient import TestClient

    from server.api import app

    client = TestClient(app, base_url="http://127.0.0.1:8000")
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "algocoach"
    assert payload["version"] == lc.__version__
    assert payload["site"] == "leetcode.cn"
    assert payload["configured"] is False
