"""Submission archive: recent history, site import, destructive data wipe."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from lc import auth, problems
from lc.archive import build_record
from lc.config import INSTANCE_LOCK_NAME, app_dir, update_lock
from lc.logutil import logger
from lc.sites.cn import classify_status_text
from server import state
from server.errors import http_domain_error, require_safe_qid

router = APIRouter()


@router.get("/api/archive/recent")
def archive_recent(limit: int = 50, qid: str | None = None):
    capped = max(1, min(int(limit), 200))
    slug = qid or None
    if slug:
        require_safe_qid(slug)
    return {"records": state.get_archive().query(slug=slug, limit=capped)}


class ImportSitePayload(BaseModel):
    limit: int = 20


@router.post("/api/archive/import-site")
def import_site(payload: ImportSitePayload):
    adapter = state.create_adapter()
    items = adapter.fetch_recent_submissions(min(max(1, int(payload.limit)), 20))
    cache_rows = problems.load_problems()["problems"]
    by_slug = {row.get("slug"): row for row in cache_rows}

    imported = 0
    skipped = 0
    records = []
    for item in items:
        if not item.get("submission_id") or state.get_archive().has_submission(item["submission_id"]):
            skipped += 1
            continue
        row = by_slug.get(item["slug"], {})
        if not row and item.get("frontend_id"):
            row = {"frontend_id": item["frontend_id"], "title_cn": item.get("title_cn", "")}
        record = build_record(
            slug=item["slug"],
            frontend_id=row.get("frontend_id", item.get("frontend_id", "")),
            submission_id=item["submission_id"],
            lang=item.get("lang", ""),
            # same classifier as judge results; unmatched text lands on
            # "other" so it stays visible but never inflates solved stats
            verdict={"status_key": classify_status_text(item.get("status")) or "other"},
            problem_row=row,
        )
        if item.get("timestamp", "").isdigit():
            record["timestamp"] = datetime.fromtimestamp(
                int(item["timestamp"]), tz=timezone.utc
            ).isoformat(timespec="seconds")
        records.append(record)

    # the site feed is newest-first, but Archive.query derives its
    # newest-first listing from file append order: append oldest-first so the
    # batch lands in true chronological position (ISO UTC strings sort
    # lexically - both write paths stamp the same format)
    records.sort(key=lambda record: str(record.get("timestamp", "")))
    for record in records:
        state.get_archive().append(record)
        imported += 1

    result = {"imported": imported, "skipped": skipped}
    logger.info("site import: %s", result)
    return result


@router.delete("/api/local-data")
def clear_local_data():
    """Erase everything under the data directory except the live lock file.

    Removes problem cache, submission archive, workspace files and config
    (cookie included); auth singletons are reset so the app returns to the
    unconfigured state immediately.
    """
    if state.sync_engine.progress()["running"]:
        raise http_domain_error(409, "sync_in_progress")

    # hold the same lock start_sync uses: either begin() wins and the
    # running-check above sees it (409), or this wipe completes first and
    # the later sync starts fresh on an empty directory - no interleaving
    with state.lifecycle_lock:
        # auth reset comes FIRST, inside the wipe: an in-flight rotation
        # persist must fail its still-current check instead of winning the
        # config lock race and resurrecting the erased cookie into a fresh
        # config.toml after the directory was declared clean
        auth.reset_state()
        root = app_dir()
        cleared = []
        # the config update lock keeps a concurrent settings save or rotation
        # persist from interleaving with the deletion of config.toml
        with update_lock():
            if root.exists():
                keep = {INSTANCE_LOCK_NAME}
                for entry in sorted(root.iterdir()):
                    if entry.name in keep:
                        continue
                    try:
                        if entry.is_dir():
                            shutil.rmtree(entry)
                        else:
                            entry.unlink()
                        cleared.append(entry.name)
                    except OSError as exc:
                        logger.warning("could not remove %s: %s", entry, exc)

        state.reset_app_state()
    logger.info("local data cleared: %s", cleared)
    return {"cleared": cleared, "data_dir": str(root)}
