"""Process-wide test hygiene.

server.state keeps lazily-built singletons at module level (the archive
cache, the sync engine). Without a central reset, a case that touches them
leaves a stale object bound to an already-deleted temp data dir, and later
cases inherit its in-memory records - order-dependent failures. Reset around
every test.

Safety net: ALGOCOACH_HOME is redirected to a per-test temp directory by
default. Tests that manage their own environment override it afterwards
(file-level fixtures instantiate after conftest ones); a test that forgets
isolation can therefore never read or - worse - wipe the real ~/.algocoach
(the DELETE /api/local-data regression once ran against it and erased the
user's live data; this default makes that class of bug impossible).
"""

import pytest

import lc.auth as auth


@pytest.fixture(autouse=True)
def reset_process_singletons(tmp_path, monkeypatch):
    from server import state as state_module

    monkeypatch.setenv("ALGOCOACH_HOME", str(tmp_path / "home"))
    state_module.reset_app_state()
    auth.reset_state()
    yield
    state_module.reset_app_state()
    auth.reset_state()
