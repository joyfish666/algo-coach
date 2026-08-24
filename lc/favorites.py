"""Favorite-problem index (~/.algocoach/favorites.json).

Why a dedicated index file instead of a flag inside each workspace's
meta.json: the problem list must render favorite state for every row of a
4400+ problem cache, and workspace directories only exist for problems that
have been opened - scanning/deriving per-directory flags would make the list
endpoint O(opened problems) with unpredictable latency. A single tiny JSON
document mirrors the archive's "index file for list queries" pattern:
- whole-file read/write under one lock (favorites mutate rarely)
- atomic replace on save (tmp + rename), same as the problems cache
- unknown slugs are tolerated and pruned lazily on next write
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from lc.config import favorites_path

_LOCK = threading.Lock()


def _resolve(path: Path | None) -> Path:
    return path if path is not None else favorites_path()


def load_favorites(path: Path | None = None) -> set:
    source = _resolve(path)
    if not source.exists():
        return set()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    slugs = payload.get("slugs") if isinstance(payload, dict) else None
    if not isinstance(slugs, list):
        return set()
    return {str(slug) for slug in slugs if slug}


def save_favorites(slugs, path: Path | None = None) -> None:
    target = _resolve(path)
    ordered = sorted({str(slug) for slug in slugs if slug})
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(
            json.dumps({"schema": 1, "slugs": ordered}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        tmp.replace(target)


def is_favorite(slug: str, path: Path | None = None) -> bool:
    return str(slug or "") in load_favorites(path)


def set_favorite(slug: str, favorite: bool, path: Path | None = None) -> bool:
    """Set (or clear) one slug; returns the resulting state."""
    slug = str(slug or "")
    if not slug:
        raise ValueError("slug is required")
    current = load_favorites(path)
    if favorite:
        current.add(slug)
    else:
        current.discard(slug)
    save_favorites(current, path)
    return favorite
