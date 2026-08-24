"""Process-wide test hygiene.

server/api.py keeps lazily-built singletons at module level (the archive
cache). Without a central reset, a case that touches them leaves a stale
object bound to an already-deleted temp data dir, and later cases inherit
its in-memory records - order-dependent failures. Reset around every test.
"""

import pytest

import lc.auth as auth


@pytest.fixture(autouse=True)
def reset_process_singletons():
    from server import api as api_module

    api_module.reset_app_state()
    auth.reset_state()
    yield
    api_module.reset_app_state()
    auth.reset_state()
