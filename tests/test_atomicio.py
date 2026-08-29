"""lc.atomicio: Windows sharing-violation retry on os.replace."""

import pytest

from lc.atomicio import atomic_write_text


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
