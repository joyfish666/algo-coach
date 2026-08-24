import pytest
import requests

import lc.auth as auth


class FakeResponse:
    def __init__(self, status_code=200, headers=None, payload=None, history=None, url="https://leetcode.cn/graphql/"):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self.history = history or []
        self.url = url

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture(autouse=True)
def clean_auth_state():
    auth.reset_state()
    yield
    auth.reset_state()


def test_parse_cookie_string():
    jar = auth.parse_cookie_string('LEETCODE_SESSION=abc=def; csrftoken=tok123; empty=; ;x=y')
    assert jar["LEETCODE_SESSION"] == "abc=def"
    assert jar["csrftoken"] == "tok123"
    assert jar["empty"] == ""
    assert "x" in jar


def test_extract_csrf_token_missing():
    assert auth.extract_csrf_token("a=b") == ""
    assert auth.extract_csrf_token("") == ""


def test_build_session_sets_cookies_and_headers():
    session = auth.build_session("csrftoken=tok123; LEETCODE_SESSION=sess")
    assert session.cookies.get("csrftoken") == "tok123"
    assert session.cookies.get("LEETCODE_SESSION") == "sess"
    assert session.headers["User-Agent"].startswith("Mozilla/5.0")
    assert session.headers["Referer"] == auth.LEETCODE_CN_BASE
    assert session.headers["X-CSRFToken"] == "tok123"


def test_check_response_403_raises_auth_error():
    with pytest.raises(auth.AuthError):
        auth.check_response(FakeResponse(status_code=403))


def test_check_response_login_redirect_raises_auth_error():
    redirect = FakeResponse(
        status_code=302,
        headers={"Location": "https://leetcode.cn/accounts/login/?next=/"},
    )
    response = FakeResponse(status_code=200, history=[redirect])
    with pytest.raises(auth.AuthError):
        auth.check_response(response)


def test_check_response_final_url_login_page():
    response = FakeResponse(
        status_code=200,
        url="https://leetcode.cn/accounts/login/",
    )
    with pytest.raises(auth.AuthError):
        auth.check_response(response)


def test_check_response_normal_200_passes():
    response = FakeResponse(status_code=200, payload={"data": {}})
    auth.check_response(response)


def test_is_auth_error_payload_variants():
    assert auth.is_auth_error_payload([{"message": "User is not logged in"}])
    assert auth.is_auth_error_payload([{"message": "认证失败"}])
    assert not auth.is_auth_error_payload([{"message": "Cannot query field 'x'"}])
    assert not auth.is_auth_error_payload([])
    assert not auth.is_auth_error_payload(None)
    assert not auth.is_auth_error_payload({"message": "not a list"})


def test_body_reports_auth_error_on_200_with_errors():
    payload = {"errors": [{"message": "Not logged in"}]}
    assert auth.body_reports_auth_error(FakeResponse(payload=payload))
    assert not auth.body_reports_auth_error(FakeResponse(payload={"data": {}}))


def test_configure_registers_singletons_and_rebuild_swaps_session():
    first_client = auth.configure("csrftoken=a1")
    assert auth.get_http_client() is first_client
    first_session = auth.get_session()
    assert first_session.cookies.get("csrftoken") == "a1"

    second_client = auth.rebuild("csrftoken=b2")
    assert auth.get_http_client() is second_client
    assert auth.get_http_client() is not first_client
    second_session = auth.get_session()
    assert second_session is not first_session
    assert second_session.cookies.get("csrftoken") == "b2"


def test_configure_reads_interval_from_config_file(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    import lc.config as config

    data = dict(config.DEFAULTS)
    data["request_interval"] = 4.5
    config.save(data, config_path)

    original = config.config_path
    monkeypatch.setattr(config, "config_path", lambda: config_path)
    try:
        client = auth.configure("cookie=x", timeout=9.0)
        assert client.limiter.interval == 4.5
        assert client.timeout == 9.0
    finally:
        monkeypatch.setattr(config, "config_path", original)


def test_requests_exception_types_available():
    assert requests.ConnectionError is not None


# ---------------------------------------------------------------------------
# rotated-cookie persistence (C2)


def _client_with_session(session_value, csrf_value):
    return auth.configure(f"csrftoken={csrf_value}; LEETCODE_SESSION={session_value}")


def test_persist_rotated_cookies_writes_only_on_change(monkeypatch):
    import lc.config as config

    saved = []
    current = {"cookie": "csrftoken=old; LEETCODE_SESSION=old"}
    monkeypatch.setattr(config, "load", lambda *a, **k: dict(current))

    def fake_save(data, *a, **k):
        current.update(data)
        saved.append(data.get("cookie"))

    monkeypatch.setattr(config, "save", fake_save)

    client = _client_with_session("new-sess", "new-tok")
    auth._persist_rotated_cookies(client)
    assert saved == ["csrftoken=new-tok; LEETCODE_SESSION=new-sess"]

    # steady state: identical cookie must not hit the disk again
    auth._persist_rotated_cookies(client)
    auth._persist_rotated_cookies(client)
    assert len(saved) == 1

    # rotation: a changed session value is persisted exactly once
    rotated = _client_with_session("rotated-sess", "new-tok")
    auth._persist_rotated_cookies(rotated)
    assert len(saved) == 2
    assert saved[1].endswith("LEETCODE_SESSION=rotated-sess")


def test_persist_rotated_cookies_skips_disk_when_config_matches(monkeypatch):
    import lc.config as config

    cookie = "csrftoken=t1; LEETCODE_SESSION=s1"
    monkeypatch.setattr(config, "load", lambda *a, **k: {"cookie": cookie})
    calls = []
    monkeypatch.setattr(
        config, "save", lambda data, *a, **k: calls.append(dict(data))
    )

    client = _client_with_session("s1", "t1")
    auth._last_persisted_cookie = None
    auth._persist_rotated_cookies(client)
    assert calls == []
    assert auth._last_persisted_cookie == cookie


def test_persist_rotated_cookies_thread_safety(monkeypatch):
    import threading

    import lc.config as config

    monkeypatch.setattr(config, "load", lambda *a, **k: {})
    saves = []
    saves_lock = threading.Lock()

    def fake_save(data, *a, **k):
        with saves_lock:
            saves.append(data.get("cookie"))

    monkeypatch.setattr(config, "save", fake_save)

    clients = [_client_with_session(f"s{i}", f"t{i}") for i in range(8)]
    threads = [
        threading.Thread(target=auth._persist_rotated_cookies, args=(c,))
        for c in clients
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(saves) == sorted(
        f"csrftoken=t{i}; LEETCODE_SESSION=s{i}" for i in range(8)
    )
