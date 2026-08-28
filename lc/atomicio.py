"""Cross-platform atomic file persistence primitive.

Tmp-file + os.replace is the project-wide persistence discipline, but on
Windows os.replace raises PermissionError while any thread still holds the
target open: CPython opens files without FILE_SHARE_DELETE, so a concurrent
reader (GET /api/problems streaming problems.json, an endpoint mid-load of
config.toml) turns the rename into a sharing violation. POSIX never fails
this way, which is why the discipline looked safe until it ran on Windows.

Locking every reader would duplicate the locking already done at higher
levels (cache/favorites/config RMW); instead the replace itself retries
briefly. Readers hold their handles for microseconds, so a handful of short
retries absorbs the collision without turning a routine persist into a 500.
All writers must go through here so the retry policy exists in one place.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

_REPLACE_ATTEMPTS = 8
_REPLACE_RETRY_DELAY = 0.015


def _replace_with_retry(tmp_path: Path, target: Path) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp_path, target)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY)


def atomic_write_text(
    path: Path | str,
    content: str,
    *,
    newline: str | None = "\n",
) -> None:
    """Write content to path via tmp file + retried os.replace.

    mkstemp creates the tmp file owner-only (0600 on POSIX), so the
    restrictive-permission guarantee survives the swap; newline follows the
    open() convention (None = os.linesep translation) so existing callers
    keep their exact byte-level behavior.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as fh:
            fh.write(content)
        _replace_with_retry(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
