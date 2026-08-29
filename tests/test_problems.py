"""Problem cache and sync engine (lc.problems)."""

import json

from lc import problems
from lc.exceptions import NetworkError


# ---------------------------------------------------------------------------
# cache helpers


def test_is_supported_category():
    assert problems.is_supported_category("Algorithms")
    assert problems.is_supported_category("")
    assert not problems.is_supported_category("Database")
    assert not problems.is_supported_category("Concurrency")


def test_load_problems_missing_cache(tmp_path):
    payload = problems.load_problems(tmp_path / "none.json")
    assert payload["problems"] == []
    assert payload["total"] == 0


def test_upsert_summary_into_cache_self_heal(tmp_path):
    cache = tmp_path / "problems.json"
    seed = {
        "schema_version": 1,
        "synced_at": None,
        "total": 1,
        "problems": [{"slug": "two-sum", "frontend_id": "1", "title_cn": ""}],
    }
    cache.write_text(json.dumps(seed), encoding="utf-8")
    problems.upsert_summary_into_cache(
        {"slug": "add-two-num", "frontend_id": "2", "title_cn": "两数相加"}, cache
    )
    updated = problems.load_problems(cache)
    slugs = [row["slug"] for row in updated["problems"]]
    assert slugs == ["two-sum", "add-two-num"]
    row_two_sum = updated["problems"][0]
    assert "supported" in row_two_sum

    problems.upsert_summary_into_cache(
        {"slug": "two-sum", "frontend_id": "1", "title_cn": "两数之和"}, cache
    )
    final = problems.load_problems(cache)
    assert len(final["problems"]) == 2
    assert final["problems"][0]["title_cn"] == "两数之和"


# ---------------------------------------------------------------------------
# SyncEngine


class FakePageAdapter:
    def __init__(self, pages, total, fail_on_page=None):
        self.pages = pages
        self.total = total
        self.fail_on_page = fail_on_page
        self.calls = []

    def fetch_problem_list_page(self, skip, limit):
        self.calls.append(skip)
        page_index = skip // limit
        if self.fail_on_page is not None and page_index == self.fail_on_page:
            raise NetworkError("boom on page")
        return {"total": self.total, "problems": self.pages[page_index]}


def make_row(n):
    return {
        "slug": f"problem-{n}",
        "frontend_id": str(n),
        "title_en": f"Problem {n}",
        "title_cn": f"题目 {n}",
        "difficulty": "easy",
        "paid_only": False,
        "category": "Algorithms",
        "tags": [],
    }


def test_sync_engine_happy_path_writes_sorted_cache(tmp_path):
    pages = [
        [make_row(2), make_row(1)],
        [make_row(10), make_row(3)],
    ]
    adapter = FakePageAdapter(pages, total=4)
    engine = problems.SyncEngine()
    cache = tmp_path / "problems.json"
    engine.run_blocking(adapter, cache)
    payload = problems.load_problems(cache)
    ids = [row["frontend_id"] for row in payload["problems"]]
    assert ids == ["1", "2", "3", "10"]
    assert payload["total"] == 4
    progress = engine.progress()
    assert progress["running"] is False
    assert progress["error"] is None
    assert progress["pages_done"] == 2
    assert progress["fetched"] == 4
    rows = payload["problems"]
    assert all(row["supported"] for row in rows)


def test_sync_engine_resumes_after_failure_within_process(tmp_path):
    cache = tmp_path / "problems.json"
    failing = FakePageAdapter(
        [[make_row(101 + i) for i in range(100)], [make_row(i) for i in range(50)]],
        total=150,
        fail_on_page=1,
    )
    engine = problems.SyncEngine()
    engine.run_blocking(failing, cache)
    progress = engine.progress()
    assert progress["error"] == "boom on page"
    assert progress["fetched"] == 100
    assert progress["resumable"] is True

    healthy = FakePageAdapter(
        [[make_row(100 + i) for i in range(100)], [make_row(i) for i in range(50)]],
        total=150,
    )
    engine.run_blocking(healthy, cache)
    final = engine.progress()
    assert final["error"] is None
    assert final["fetched"] == 150
    payload = problems.load_problems(cache)
    assert payload["total"] == 150
    assert healthy.calls[0] == 100


def test_sync_engine_dedupes_slug_and_frontend_id(tmp_path):
    dup_alt = make_row(6)
    dup_alt["slug"] = "problem-5"
    pages = [[make_row(1), make_row(2)], [make_row(5), dup_alt]]
    adapter = FakePageAdapter(pages, total=4)
    engine = problems.SyncEngine()
    cache = tmp_path / "problems.json"
    engine.run_blocking(adapter, cache)
    payload = problems.load_problems(cache)
    slugs = sorted(row["slug"] for row in payload["problems"])
    assert slugs == ["problem-1", "problem-2", "problem-5"]
    assert engine.progress()["fetched"] == 3


def test_sync_engine_unsupported_category_marked(tmp_path):
    sql_row = make_row(7)
    sql_row["category"] = "Database"
    adapter = FakePageAdapter([[sql_row]], total=1)
    engine = problems.SyncEngine()
    cache = tmp_path / "problems.json"
    engine.run_blocking(adapter, cache)
    payload = problems.load_problems(cache)
    assert payload["problems"][0]["supported"] is False


def test_sync_engine_unknown_total_does_not_truncate_after_page_one(tmp_path):
    """Regression: a missing site 'total' used to fall back to the current
    page's row count, silently ending the sync after one page."""
    pages = [
        [make_row(i) for i in range(100)],
        [make_row(100 + i) for i in range(50)],
    ]
    adapter = FakePageAdapter(pages, total=None)
    engine = problems.SyncEngine()
    cache = tmp_path / "problems.json"
    engine.run_blocking(adapter, cache)

    assert adapter.calls == [0, 100]
    payload = problems.load_problems(cache)
    assert payload["total"] == 150
    assert engine.progress()["fetched"] == 150
    assert engine.progress()["error"] is None


def test_sync_engine_refetches_everything_after_completed_sync(tmp_path):
    """Regression: a second sync used to resume past the final page and
    terminate instantly, so problems added on the site were invisible until
    process restart. Resume must apply only after a FAILED run."""
    pages = {0: [make_row(i) for i in range(2)]}
    state = {"total": 2}

    class LiveSite:
        def fetch_problem_list_page(self, skip, limit):
            rows = pages.get(skip // limit, [])
            return {"total": state["total"], "problems": rows}

    engine = problems.SyncEngine()
    cache = tmp_path / "problems.json"
    engine.run_blocking(LiveSite(), cache)
    assert engine.progress()["fetched"] == 2
    assert engine.progress()["resumable"] is False

    # the site gains a problem; a fresh manual sync must pick it up
    pages[0].append(make_row(3))
    state["total"] = 3
    engine.run_blocking(LiveSite(), cache)

    progress = engine.progress()
    assert progress["error"] is None
    assert progress["fetched"] == 3
    assert [row["slug"] for row in problems.load_problems(cache)["problems"]][-1] == "problem-3"


def test_progress_resumable_only_after_failure(tmp_path):
    adapter = FakePageAdapter(
        [[make_row(i) for i in range(100)], [make_row(i) for i in range(1)]],
        total=101,
        fail_on_page=1,
    )
    engine = problems.SyncEngine()
    cache = tmp_path / "problems.json"
    engine.run_blocking(adapter, cache)
    assert engine.progress()["error"] == "boom on page"
    assert engine.progress()["resumable"] is True
