"""Input validation shared by the site adapter and the API layer.

One slug policy with two error doors: the site adapter wraps a bad slug from
remote data in NetworkError, while the API layer answers 400 for bad client
input. The policy itself lives here so the two doors cannot drift.
"""

from __future__ import annotations

import re

SAFE_SLUG_RE = re.compile(r"[A-Za-z0-9_-]+")


def is_safe_slug(slug) -> bool:
    """False for anything that could escape the workspace as a path part."""
    return bool(SAFE_SLUG_RE.fullmatch(str(slug or "")))
