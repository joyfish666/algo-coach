import json
import threading


from lc.archive import (
    Archive,
    build_record,
    compute_stats,
    recommend_problems,
    tag_mastery,
)


def make_verdict(status="accepted", **overrides):
    base = {
        "status_key": status,
        "runtime_display": "50 ms",
        "runtime_percentile": 80.0,
        "memory_display": "41.0 MB",
        "memory_percentile": 60.5,
        "total_correct": 57,
        "total_testcases": 57,
        "outputs": ["x"],
        "expected_outputs": ["x"],
        "compile_error": "",
        "runtime_error": "",
        "submission_id": "s1",
    }
    base.update(overrides)
    return base


ROW = {
    "slug": "two-sum",
    "frontend_id": "1",
    "difficulty": "easy",
    "category": "Algorithms",
    "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}],
}


def test_build_record_is_self_sufficient():
    record = build_record(
        slug="two-sum",
        frontend_id="1",
        submission_id="9001",
        lang="cpp",
        verdict=make_verdict(),
        problem_row=ROW,
    )
    assert record["status"] == "accepted"
    assert record["difficulty"] == "easy"
    assert record["tags"][0]["slug"] == "array"
    assert record["lang"] == "cpp"
    assert record["timestamp"]


def test_archive_roundtrip_and_latest_index(tmp_path):
    path = tmp_path / "submissions.jsonl"
    archive = Archive(path)
    archive.append(build_record(slug="a", frontend_id="1", submission_id="1", lang="cpp",
                                verdict=make_verdict("wrong_answer"), problem_row=ROW))
    archive.append(build_record(slug="a", frontend_id="1", submission_id="2", lang="cpp",
                                verdict=make_verdict("accepted"), problem_row=ROW))
    archive.append(build_record(slug="b", frontend_id="2", submission_id="3", lang="python3",
                                verdict=make_verdict(), problem_row={**ROW, "slug": "b"}))

    latest = archive.latest_by_slug()
    assert latest["a"]["status"] == "accepted"
    assert latest["a"]["submission_id"] == "2"
    assert latest["b"]["status"] == "accepted"
    assert archive.attempts_total() == 3
    assert archive.has_submission("3")
    assert not archive.has_submission("999")

    recent = archive.recent(2)
    assert [r["submission_id"] for r in recent] == ["3", "2"]


def test_archive_reloads_index_from_disk_with_torn_lines(tmp_path):
    path = tmp_path / "submissions.jsonl"
    good = build_record(slug="a", frontend_id="1", submission_id="7", lang="cpp",
                        verdict=make_verdict(), problem_row=ROW)
    torn = '{"slug": "broken", "stat'
    path.write_text(json.dumps(good) + "\n" + torn + "\n", encoding="utf-8")

    reloaded = Archive(path)
    assert reloaded.latest_by_slug()["a"]["status"] == "accepted"
    assert reloaded.has_submission("7")
    stats = reloaded.stats_snapshot()
    assert stats["solved_total"] == 1
    assert stats["by_difficulty"]["easy"] == 1


def test_archive_concurrent_appends(tmp_path):
    path = tmp_path / "submissions.jsonl"
    archive = Archive(path)

    def worker(n):
        for i in range(20):
            archive.append(
                build_record(
                    slug=f"p-{n}-{i}", frontend_id=str(i), submission_id=f"{n}-{i}",
                    lang="cpp", verdict=make_verdict(), problem_row=ROW,
                )
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert archive.attempts_total() == 80
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 80


def test_compute_stats_excludes_unclassified():
    index = {
        "a": {"status": "accepted", "difficulty": "easy"},
        "b": {"status": "accepted", "difficulty": "hard"},
        "c": {"status": "accepted", "difficulty": ""},
        "d": {"status": "wrong_answer", "difficulty": "easy"},
        "e": {"status": "unknown", "difficulty": "medium"},
    }
    stats = compute_stats(index)
    assert stats == {
        "solved_total": 3,
        "by_difficulty": {"easy": 1, "medium": 0, "hard": 1},
        "solved_unclassified": 1,
    }


def test_tag_mastery_sorted_weakest_first():
    index = {
        "a": {"status": "accepted", "tags": [{"slug": "dp", "name_zh": "动态规划", "name_en": "DP"}]},
        "b": {"status": "wrong_answer", "tags": [{"slug": "dp", "name_zh": "动态规划", "name_en": "DP"}]},
        "c": {"status": "accepted", "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}]},
    }
    tags = tag_mastery(index)
    assert tags[0]["slug"] == "dp"
    assert tags[0]["mastered"] == 0.5
    assert tags[1]["mastered"] == 1.0


def test_recommend_problems_skips_solved_and_unsupported():
    cache = [
        {"slug": "done", "frontend_id": "1", "difficulty": "easy", "supported": True,
         "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}]},
        {"slug": "sql", "frontend_id": "175", "difficulty": "easy", "supported": False,
         "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}]},
        {"slug": "next-easy", "frontend_id": "9", "difficulty": "easy", "supported": True,
         "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}]},
        {"slug": "next-med", "frontend_id": "5", "difficulty": "medium", "supported": True,
         "tags": [{"slug": "array", "name_zh": "数组", "name_en": "Array"}]},
        {"slug": "unrelated", "frontend_id": "11", "difficulty": "easy", "supported": True,
         "tags": []},
    ]
    latest = {"done": {"status": "accepted"}}
    weak = [{"slug": "array", "mastered": 0.4}]
    recs = recommend_problems(cache, latest, weak)
    assert [r["slug"] for r in recs] == ["next-easy", "next-med"]


def test_recent_never_reads_half_written_line(tmp_path):
    """recent() shares the append lock; under concurrent writes every record
    it returns must still be a complete JSON object."""
    import threading

    archive = Archive(tmp_path / "submissions.jsonl")
    writer = threading.Thread(
        target=lambda: [archive.append({"n": i, "pad": "x" * 200}) for i in range(300)]
    )
    writer.start()
    reads = 0
    while writer.is_alive():
        for record in archive.recent(limit=10_000):
            assert isinstance(record, dict) and "n" in record
            reads += 1
    writer.join()
    final = archive.recent(limit=10_000)
    assert len(final) == 300
    assert archive.attempts_total() == 300
