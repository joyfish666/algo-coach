"""Local submission history archive (append-only JSON Lines).

Design points:
- single file ~/.algocoach/submissions.jsonl; each line is one self-sufficient
  record (difficulty/tags/lang and full verdict fields embedded) so a single
  record can power analytics and AI reports without joining anything
- submission_id is present on all three write paths (judge completion, timeout
  unknown archival, site import) and doubles as the import dedup key
- an in-process qid -> latest-verdict index is maintained under a lock
  (loaded at startup, updated on append) so the problem list never rescans
  the whole file; accepted status derives from that index
- torn/corrupt lines are skipped silently on load (crash-mid-write tolerance)
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from lc.config import archive_path
from lc.logutil import logger


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_record(
    *,
    slug: str,
    frontend_id: str,
    submission_id: str,
    lang: str,
    verdict: dict,
    problem_row: dict = None,
) -> dict:
    row = problem_row or {}
    return {
        "schema": 1,
        "timestamp": _utc_now_iso(),
        "slug": slug,
        "frontend_id": str(frontend_id or ""),
        "submission_id": str(submission_id or ""),
        "lang": lang,
        "status": verdict.get("status_key", "unknown"),
        "runtime_display": verdict.get("runtime_display", ""),
        "runtime_percentile": verdict.get("runtime_percentile"),
        "memory_display": verdict.get("memory_display", ""),
        "memory_percentile": verdict.get("memory_percentile"),
        "total_correct": verdict.get("total_correct"),
        "total_testcases": verdict.get("total_testcases"),
        "outputs": verdict.get("outputs", []),
        "expected_outputs": verdict.get("expected_outputs", []),
        "compile_error": verdict.get("compile_error", ""),
        "runtime_error": verdict.get("runtime_error", ""),
        "difficulty": row.get("difficulty", ""),
        "tags": row.get("tags", []),
        "category": row.get("category", ""),
    }


def compute_stats(latest_index: dict) -> dict:
    solved = [r for r in latest_index.values() if r.get("status") == "accepted"]
    by_difficulty = {"easy": 0, "medium": 0, "hard": 0}
    unknown_difficulty = 0
    for record in solved:
        key = (record.get("difficulty") or "").lower()
        if key in by_difficulty:
            by_difficulty[key] += 1
        else:
            unknown_difficulty += 1
    return {
        "solved_total": len(solved),
        "by_difficulty": by_difficulty,
        "solved_unclassified": unknown_difficulty,
    }


def tag_mastery(latest_index: dict) -> list:
    agg = {}
    for record in latest_index.values():
        accepted = record.get("status") == "accepted"
        for tag in record.get("tags") or []:
            slug = tag.get("slug")
            if not slug:
                continue
            bucket = agg.setdefault(
                slug,
                {
                    "slug": slug,
                    "name_zh": tag.get("name_zh") or tag.get("name_en") or slug,
                    "name_en": tag.get("name_en") or slug,
                    "attempted": 0,
                    "solved": 0,
                },
            )
            bucket["attempted"] += 1
            if accepted:
                bucket["solved"] += 1
    result = []
    for bucket in agg.values():
        mastered = bucket["solved"] / bucket["attempted"] if bucket["attempted"] else 0.0
        result.append({**bucket, "mastered": round(mastered, 3)})
    result.sort(key=lambda item: (item["mastered"], -item["attempted"]))
    return result


_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


def recommend_problems(cache_rows: list, latest_index: dict, weak_tags: list, limit: int = 5) -> list:
    solved_slugs = {slug for slug, r in latest_index.items() if r.get("status") == "accepted"}
    weak = {tag["slug"] for tag in weak_tags[:8]}
    candidates = []
    for row in cache_rows or []:
        slug = row.get("slug")
        if not slug or slug in solved_slugs or row.get("supported") is False:
            continue
        shared = [t for t in (row.get("tags") or []) if t.get("slug") in weak]
        if not shared:
            continue
        rank = _DIFFICULTY_RANK.get((row.get("difficulty") or "").lower(), 3)
        fid = str(row.get("frontend_id", "") or "")
        numeric = int(fid) if fid.isdigit() else 10**9
        candidates.append((rank, numeric, fid, row))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in candidates[:limit]]


class Archive:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else archive_path()
        self._lock = threading.Lock()
        self._latest_by_slug = {}
        self._known_submission_ids = set()
        self._attempts_total = 0
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._absorb(record)

    def _absorb(self, record: dict):
        slug = record.get("slug")
        if slug:
            existing = self._latest_by_slug.get(slug)
            if existing is None or str(record.get("timestamp", "")) >= str(existing.get("timestamp", "")):
                self._latest_by_slug[slug] = record
        sid = str(record.get("submission_id", "") or "")
        if sid:
            self._known_submission_ids.add(sid)
        self._attempts_total += 1

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._absorb(record)

    def recent(self, limit: int = 50) -> list:
        records = []
        if self.path.exists():
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return list(reversed(records[-limit:]))

    def latest_by_slug(self) -> dict:
        with self._lock:
            return dict(self._latest_by_slug)

    def has_submission(self, submission_id: str) -> bool:
        with self._lock:
            return str(submission_id) in self._known_submission_ids

    def attempts_total(self) -> int:
        with self._lock:
            return self._attempts_total

    def stats_snapshot(self) -> dict:
        with self._lock:
            index = dict(self._latest_by_slug)
        return compute_stats(index)

    def tag_mastery(self) -> list:
        with self._lock:
            index = dict(self._latest_by_slug)
        return tag_mastery(index)
