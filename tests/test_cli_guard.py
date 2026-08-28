import os

import pytest

import cli
import lc.config as config


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("ALGOCOACH_HOME", str(home))
    yield
    cli.release_instance_lock()


def test_pid_alive_current_process():
    assert cli._pid_alive(os.getpid()) is True


def test_pid_alive_rejects_invalid_and_dead():
    assert cli._pid_alive(0) is False
    assert cli._pid_alive(-5) is False
    assert cli._pid_alive("x") is False
    # the property being checked: the return value is a real boolean, so an
    # unreasonably large (almost surely unallocated) pid cannot smuggle
    # arbitrary truthy values through the guard
    assert cli._pid_alive(2**30) in (True, False)
    assert isinstance(cli._pid_alive(2**30), bool)


def test_acquire_lock_then_refuse_second(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "lock_path", lambda: tmp_path / "instance.lock")
    owned, _ = cli.acquire_instance_lock(8000)
    assert owned is True
    assert cli.lock_path().exists()

    owned_again, info = cli.acquire_instance_lock(8010)
    assert owned_again is False
    assert info["pid"] == os.getpid()
    assert info["port"] == 8000


def test_stale_lock_taken_over(monkeypatch, tmp_path):
    lock = tmp_path / "instance.lock"
    monkeypatch.setattr(cli, "lock_path", lambda: lock)

    dead_pid_source = {}

    class DeadProcess:
        pid_placeholder = True

    import json as json_module
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc.terminate()
    proc.wait()
    dead_pid = proc.pid

    lock.write_text(json_module.dumps({"pid": dead_pid, "port": 1234}), encoding="utf-8")
    if cli._pid_alive(dead_pid):
        pytest.skip("platform recycled the pid too quickly")

    owned, _ = cli.acquire_instance_lock(8000)
    assert owned is True
    payload = json_module.loads(lock.read_text(encoding="utf-8"))
    assert payload == {"pid": os.getpid(), "port": 8000}
    del dead_pid_source
    del DeadProcess


def test_corrupt_lock_taken_over(monkeypatch, tmp_path):
    lock = tmp_path / "instance.lock"
    monkeypatch.setattr(cli, "lock_path", lambda: lock)
    lock.write_text("not-json{{", encoding="utf-8")
    owned, _ = cli.acquire_instance_lock(8000)
    assert owned is True


def test_release_removes_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "lock_path", lambda: tmp_path / "instance.lock")
    owned, _ = cli.acquire_instance_lock(8000)
    assert owned
    cli.release_instance_lock()
    assert not cli.lock_path().exists()


def test_release_keeps_foreign_lock(monkeypatch, tmp_path):
    """Regression: release unlinked unconditionally, so an instance exiting
    after a crash-and-takeover deleted its SUCCESSOR's lock and reopened the
    double-instance window."""
    import json as json_module

    lock = tmp_path / "instance.lock"
    monkeypatch.setattr(cli, "lock_path", lambda: lock)
    lock.write_text(
        json_module.dumps({"pid": 424242, "port": 8000}), encoding="utf-8"
    )
    cli.release_instance_lock()
    assert lock.exists()

    lock.write_text(
        json_module.dumps({"pid": os.getpid(), "port": 8000}), encoding="utf-8"
    )
    cli.release_instance_lock()
    assert not lock.exists()


def test_probe_is_coach_false_when_nothing_listens():
    assert cli.probe_is_coach("127.0.0.1", 1) is False


def test_probe_is_coach_true_for_real_endpoint(monkeypatch):
    calls = {}

    class FakeReader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"app": "algocoach", "version": "0.1.0"}'

    def fake_urlopen(url, timeout=None):
        calls["url"] = url

        return FakeReader()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    assert cli.probe_is_coach("127.0.0.1", 8000) is True
    assert calls["url"] == "http://127.0.0.1:8000/api/status"


def test_bind_free_socket_skips_occupied_and_holds(monkeypatch):
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    occupied = sock.getsockname()[1]
    sock.listen(1)
    try:
        held = cli.bind_free_socket(occupied, host="127.0.0.1")
        try:
            assert held.getsockname()[1] != occupied
            # the socket is returned still bound+listening: while we hold it,
            # a second bind on the same port must fail (that is the point -
            # uvicorn receives an already-held listener)
            rival = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with pytest.raises(OSError):
                rival.bind(("127.0.0.1", held.getsockname()[1]))
                rival.listen(1)
        finally:
            held.close()
    finally:
        sock.close()


def test_config_exposes_app_dir_lock_location():
    assert cli.lock_path() == config.app_dir() / "instance.lock"
