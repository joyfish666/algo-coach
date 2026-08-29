"""Problem list cache and synchronization.

- paged full problem-list fetch into problems.json with atomic writes;
  resume semantics apply ONLY after a failed run: the retry continues from
  the last completed page. A sync requested after a completed (or never
  started) run is a fresh full sync - otherwise a finished engine would
  resume past the final page and silently no-op, hiding newly added
  problems until process restart
- slug / frontendQuestionId uniqueness validation during sync; anomalies are
  logged and skipped without aborting
- non-algorithm categories (SQL database etc.) are kept but marked
  unsupported
- self-healing write-back when a problem is opened before any sync ran

The per-problem workspace files live in lc.workspace; statement conversion
in lc.htmltomd.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from lc.atomicio import atomic_write_text
from lc.clock import utc_now_iso
from lc.config import problems_cache_path
from lc.logutil import logger

CACHE_SCHEMA_VERSION = 1
PAGE_SIZE = 100

_UNSUPPORTED_CATEGORY_MARKERS = ("database", "sql", "shell", "concurrency", "pandas")

_CACHE_LOCK = threading.Lock()


def is_supported_category(category: str) -> bool:
    lowered = (category or "").lower()
    if not lowered:
        return True
    return not any(marker in lowered for marker in _UNSUPPORTED_CATEGORY_MARKERS)


def decorate_problem_row(row: dict) -> dict:
    decorated = dict(row)
    decorated["supported"] = is_supported_category(row.get("category", ""))
    return decorated


def _sort_key(frontend_id: str):
    fid = str(frontend_id or "")
    if fid.isdigit():
        return (0, int(fid), "")
    return (1, 0, fid)


def cache_path_or_default(cache_path=None) -> Path:
    return Path(cache_path) if cache_path is not None else problems_cache_path()


def load_problems(cache_path=None) -> dict:
    path = cache_path_or_default(cache_path)
    if not path.exists():
        return {"schema_version": CACHE_SCHEMA_VERSION, "synced_at": None, "total": 0, "problems": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("problems cache unreadable at %s, treating as empty", path)
        return {"schema_version": CACHE_SCHEMA_VERSION, "synced_at": None, "total": 0, "problems": []}
    payload.setdefault("problems", [])
    payload.setdefault("total", len(payload["problems"]))
    return payload


def save_problems(payload: dict, cache_path=None) -> None:
    path = cache_path_or_default(cache_path)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write_text(path, text, newline="")


def upsert_summary_into_cache(summary: dict, cache_path=None) -> None:
    """Self-healing write-back used when a problem is opened before sync."""
    with _CACHE_LOCK:
        payload = load_problems(cache_path)
        rows = payload.setdefault("problems", [])
        target_slug = summary.get("slug")
        replaced = False
        for index, row in enumerate(rows):
            if row.get("slug") == target_slug:
                rows[index] = decorate_problem_row(summary)
                replaced = True
                break
        if not replaced:
            rows.append(decorate_problem_row(summary))
        rows = [decorate_problem_row(row) for row in rows]
        rows.sort(key=lambda row: _sort_key(row.get("frontend_id")))
        payload["problems"] = rows
        payload["total"] = max(int(payload.get("total") or 0), len(rows))
        save_problems(payload, cache_path)


def summary_from_detail(detail: dict) -> dict:
    """Project a site detail payload onto the cached problem-row shape."""
    keys = ("slug", "frontend_id", "title_en", "title_cn", "difficulty", "paid_only", "category", "tags")
    return {key: detail.get(key) for key in keys}


class SyncEngine:
    """Thread-safe sync orchestrator.

    Resume is tied to failure: accumulators survive a run only when that run
    errored mid-way (partial data worth continuing from). Any start after a
    successful or never-run state resets them, so repeated "sync now" always
    re-reads the site.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._seen_slugs = set()
        self._seen_ids = set()
        self._rows = []
        self._pages_done = 0
        self._total = None
        self._running = False
        self._error = None
        self._started_at = None
        self._finished_at = None
        self._failed = False

    # -- public API ---------------------------------------------------------

    def begin(self, adapter, cache_path=None) -> bool:
        with self._lock:
            if self._running:
                return False
            self._start_bookkeeping_locked(resume=self._failed and bool(self._rows))
        thread = threading.Thread(
            target=self._guarded_execute,
            args=(adapter, cache_path),
            daemon=True,
        )
        thread.start()
        return True

    def run_blocking(self, adapter, cache_path=None) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("sync already running")
            self._start_bookkeeping_locked(resume=self._failed and bool(self._rows))
        self._guarded_execute(adapter, cache_path)

    def reset(self) -> None:
        """Drop all run state (used after the data directory was wiped)."""
        with self._lock:
            self._seen_slugs = set()
            self._seen_ids = set()
            self._rows = []
            self._pages_done = 0
            self._total = None
            self._running = False
            self._error = None
            self._started_at = None
            self._finished_at = None
            self._failed = False

    def progress(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "total": self._total,
                "pages_done": self._pages_done,
                "fetched": len(self._rows),
                "error": self._error,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "resumable": self._failed and len(self._rows) > 0 and not self._running,
            }

    # -- internals ------------------------------------------------------------

    def _start_bookkeeping_locked(self, *, resume: bool):
        if not resume:
            # fresh full sync: drop any accumulated rows/pages/dedup sets so
            # the loop re-reads every page instead of resuming past the end
            self._seen_slugs = set()
            self._seen_ids = set()
            self._rows = []
            self._pages_done = 0
            self._total = None
        self._running = True
        self._error = None
        self._started_at = utc_now_iso()
        self._finished_at = None

    def _guarded_execute(self, adapter, cache_path):
        try:
            self._sync_loop(adapter, cache_path)
            with self._lock:
                self._failed = False
        except Exception as exc:
            logger.exception("problem sync failed: %s", exc)
            with self._lock:
                self._error = str(exc)
                self._failed = True
        finally:
            with self._lock:
                self._running = False
                self._finished_at = utc_now_iso()

    def _register(self, row: dict) -> bool:
        slug = row.get("slug")
        frontend_id = row.get("frontend_id")
        duplicate_reason = None
        if slug in self._seen_slugs:
            duplicate_reason = f"duplicate slug {slug!r}"
        elif frontend_id and frontend_id in self._seen_ids:
            duplicate_reason = f"duplicate frontendQuestionId {frontend_id!r}"
        if duplicate_reason:
            logger.warning("skipping problem row: %s", duplicate_reason)
            return False
        self._seen_slugs.add(slug)
        if frontend_id:
            self._seen_ids.add(frontend_id)
        return True

    def _sync_loop(self, adapter, cache_path=None):
        while True:
            with self._lock:
                skip = self._pages_done * PAGE_SIZE
            page = adapter.fetch_problem_list_page(skip, PAGE_SIZE)
            rows = page.get("problems") or []
            accepted = [row for row in rows if self._register(row)]
            with self._lock:
                self._rows.extend(decorate_problem_row(row) for row in accepted)
                self._pages_done += 1
                if self._total is None:
                    self._total = page.get("total")
                try:
                    known_total = int(self._total) if self._total is not None else None
                except (TypeError, ValueError):
                    known_total = None
            if not rows:
                break
            if known_total is not None and skip + len(rows) >= known_total:
                break
            # unknown total: a short page is the last one (otherwise the site
            # would have filled PAGE_SIZE); prevents both truncation and an
            # infinite loop
            if known_total is None and len(rows) < PAGE_SIZE:
                break
        with self._lock:
            ordered = sorted(self._rows, key=lambda row: _sort_key(row.get("frontend_id")))
            payload = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "synced_at": utc_now_iso(),
                "total": len(ordered),
                "problems": ordered,
            }
        with _CACHE_LOCK:
            save_problems(payload, cache_path)
