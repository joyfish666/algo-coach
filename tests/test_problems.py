import json

import pytest

from lc import problems
from lc.exceptions import NetworkError


# ---------------------------------------------------------------------------
# html_to_markdown


def test_html_paragraphs_and_inline_marks():
    html = "<p>Hello <strong>world</strong> and <em>grace</em></p>"
    md = problems.html_to_markdown(html)
    assert "Hello **world** and *grace*" in md


def test_html_pre_block_becomes_fence():
    html = '<pre><code>int x = 1;\nfoo(x);</code></pre>'
    md = problems.html_to_markdown(html)
    assert "```\nint x = 1;\nfoo(x);\n```" in md


def test_html_pre_with_language_class():
    html = '<pre><code class="language-cpp">auto v = 1;</code></pre>'
    md = problems.html_to_markdown(html)
    assert "```cpp\nauto v = 1;\n```" in md


def test_html_list_items():
    html = "<ul><li>first</li><li>second</li></ul>"
    md = problems.html_to_markdown(html)
    assert "- first" in md
    assert "- second" in md


def test_html_ordered_list_numbers_items():
    html = "<ol><li>one</li><li>two</li><li>three</li></ol>"
    lines = [line for line in problems.html_to_markdown(html).splitlines() if line.strip()]
    assert lines == ["1. one", "2. two", "3. three"]


def test_html_nested_ordered_lists_restart_numbering():
    html = "<ol><li>a<ol><li>x</li><li>y</li></ol></li><li>b</li></ol>"
    md = problems.html_to_markdown(html)
    assert "1. a" in md
    assert "1. x" in md
    assert "2. y" in md
    assert "2. b" in md


def test_html_table_cells_keep_separator():
    html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
    md = problems.html_to_markdown(html)
    assert "a | b" in md
    assert "c | d" in md


def test_html_formula_superscript_stays_raw():
    html = "<p>x<sup>2</sup> + y<sub>1</sub> &lt; 3</p>"
    md = problems.html_to_markdown(html)
    assert "x^2 + y1 < 3" in md


def test_html_link_and_image():
    html = '<p>see <a href="https://a.b">doc</a></p><img src="https://img/1.png" alt="pic">'
    md = problems.html_to_markdown(html)
    assert "[doc](https://a.b)" in md
    assert "![pic](https://img/1.png)" in md


def test_html_empty_input():
    assert problems.html_to_markdown("") == ""


# ---------------------------------------------------------------------------
# cache helpers


def test_is_supported_category():
    assert problems.is_supported_category("Algorithms")
    assert problems.is_supported_category("")
    assert not problems.is_supported_category("Database")
    assert not problems.is_supported_category("Concurrency")


def test_problem_dir_name_numeric_zfill(tmp_path):
    directory = problems.problem_dir_for({"slug": "two-sum", "frontend_id": "1"}, tmp_path)
    assert directory == tmp_path / "problems" / "0001-two-sum"


def test_problem_dir_name_non_numeric_uses_slug(tmp_path):
    directory = problems.problem_dir_for(
        {"slug": "shu-zu-zhong-zhong-fu-de-shu-zi-lcof", "frontend_id": "剑指 Offer 03"}, tmp_path
    )
    assert directory.name == "shu-zu-zhong-zhong-fu-de-shu-zi-lcof"


def test_load_problems_missing_cache(tmp_path):
    payload = problems.load_problems(tmp_path / "none.json")
    assert payload["problems"] == []
    assert payload["total"] == 0


def test_find_problem_dir_rejects_suffix_collision(tmp_path):
    """Regression: slug 'sum' must not hijack the '0001-two-sum' directory -
    matching parses the '<digits>-<slug>' convention instead of endswith."""
    problems_dir = tmp_path / "problems" / "0001-two-sum"
    problems_dir.mkdir(parents=True)
    assert problems.find_problem_dir(tmp_path, "two-sum") == problems_dir
    assert problems.find_problem_dir(tmp_path, "sum") is None


def test_find_problem_dir_matches_prefixed_and_plain_dirs(tmp_path):
    prefixed = tmp_path / "problems" / "0007-reverse-integer"
    plain = tmp_path / "problems" / "shu-zu-lcof"
    prefixed.mkdir(parents=True)
    plain.mkdir(parents=True)
    assert problems.find_problem_dir(tmp_path, "reverse-integer") == prefixed
    assert problems.find_problem_dir(tmp_path, "shu-zu-lcof") == plain
    assert problems.find_problem_dir(tmp_path, "missing") is None


def test_build_cases_payload_uses_example_testcases():
    detail = {
        "sample_test_case": "[2,7,11,15]\n9",
        "example_test_cases": ["[2,7,11,15]\n9", "[3,2,4]\n6"],
    }
    payload = problems.build_cases_payload(detail)
    assert [case["inputs"] for case in payload["cases"]] == [
        ["[2,7,11,15]", "9"],
        ["[3,2,4]", "6"],
    ]


def test_build_cases_payload_falls_back_to_sample():
    payload = problems.build_cases_payload({"sample_test_case": "a\nb"})
    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["inputs"] == ["a", "b"]
    assert problems.build_cases_payload({})["cases"] == []


def test_problem_dir_for_honors_configured_workspace_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOCOACH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ALGOCOACH_WORKSPACE_ROOT", str(tmp_path / "custom"))
    directory = problems.problem_dir_for({"slug": "two-sum", "frontend_id": "1"})
    assert directory == tmp_path / "custom" / "problems" / "0001-two-sum"


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


# ---------------------------------------------------------------------------
# workspace materialization


@pytest.fixture
def detail_fixture():
    return {
        "slug": "two-sum",
        "frontend_id": "1",
        "title_en": "Two Sum",
        "title_cn": "两数之和",
        "difficulty": "easy",
        "paid_only": False,
        "category": "Algorithms",
        "tags": [],
        "statement_html": "<p>两数之和<strong>题面</strong></p>",
        "hints": ["哈希"],
        "sample_test_case": "[2,7,11,15]\n9",
        "code_snippets": [
            {"lang_slug": "cpp", "code": "class Solution {};\n"},
            {"lang_slug": "python3", "code": "class Solution:\n    pass\n"},
        ],
    }


def test_open_problem_materializes_files(tmp_path, detail_fixture):
    directory = problems.open_problem(detail_fixture, tmp_path, default_language="cpp")
    assert directory.name == "0001-two-sum"
    statement = (directory / "statement.md").read_text(encoding="utf-8")
    assert "两数之和**题面**" in statement
    cases = json.loads((directory / "cases.json").read_text(encoding="utf-8"))
    assert cases["cases"][0]["inputs"] == ["[2,7,11,15]", "9"]
    assert cases["cases"][0]["expected_output"] is None
    testcases = (directory / "testcases.txt").read_text(encoding="utf-8")
    assert testcases == "[2,7,11,15]\n9"
    solution = (directory / "solution.cpp").read_text(encoding="utf-8")
    assert "class Solution" in solution
    assert not (directory / "solution.py").exists()
    meta = problems.load_meta(directory)
    assert "testcases" in meta
    assert "template:cpp" in meta
    state = problems.read_problem_state(directory, default_language="cpp")
    assert state["languages_available"] == ["cpp"]
    assert state["language"] == "cpp"


def test_refresh_backs_up_user_edited_testcases_only(tmp_path, detail_fixture):
    directory = problems.open_problem(detail_fixture, tmp_path)

    modified = detail_fixture.copy()
    modified["sample_test_case"] = "[1,2]\n3"
    result = problems.refresh_problem(directory, modified)
    assert result["backups"] == []

    user_content = "[9,9]\n18\nmy custom case"
    (directory / "testcases.txt").write_text(user_content, encoding="utf-8")
    result = problems.refresh_problem(directory, detail_fixture)
    assert "testcases.txt" in result["backups"]
    backup = (directory / "testcases.txt.bak").read_text(encoding="utf-8")
    assert backup == user_content
    current = (directory / "testcases.txt").read_text(encoding="utf-8")
    assert current == "[2,7,11,15]\n9"

    statement_before = (directory / "statement.md").read_text(encoding="utf-8")
    problems.refresh_problem(directory, detail_fixture)
    statement_after = (directory / "statement.md").read_text(encoding="utf-8")
    assert statement_before == statement_after


def test_ensure_template_fetches_once_then_exists(tmp_path, detail_fixture):
    directory = problems.open_problem(detail_fixture, tmp_path)
    calls = []

    def provider():
        calls.append(1)
        return detail_fixture

    result = problems.ensure_template(directory, "python3", provider)
    assert result["status"] == "written"
    assert (directory / "solution.py").exists()
    result = problems.ensure_template(directory, "python3", provider)
    assert result["status"] == "exists"
    assert len(calls) == 1


def test_ensure_template_unsupported_language_raises(tmp_path, detail_fixture):
    directory = problems.open_problem(detail_fixture, tmp_path)
    with pytest.raises(ValueError):
        problems.ensure_template(directory, "golang", lambda: detail_fixture)


def test_save_testcases_updates_file(tmp_path, detail_fixture):
    directory = problems.open_problem(detail_fixture, tmp_path)
    problems.save_testcases(directory, "custom input line")
    assert (directory / "testcases.txt").read_text(encoding="utf-8") == "custom input line"


def test_html_strong_inside_pre_stays_literal():
    """cn wraps the 输入：/输出： labels in <strong> inside <pre>. Emitting
    markers for them appended to the PARAGRAPH buffer (not the fence lines)
    and resurfaced as "************" runs before the next heading."""
    html = (
        "<p><strong>示例 1：</strong></p>"
        "<pre><strong>输入：</strong>nums = [2,7,11,15]\n<strong>输出：</strong>[0,1]</pre>"
        "<p><strong>示例 2：</strong></p>"
    )
    md = problems.html_to_markdown(html)
    assert "********" not in md
    fence = md.split("```")[1]
    assert "输入：nums = [2,7,11,15]" in fence
    assert "**" not in fence
    assert "**示例 2**：" in md


def test_html_strong_trailing_cjk_punctuation_stays_renderable():
    """CommonMark flanking rules refuse to close "**进阶：**你" (punctuation
    before the closer, letter after) - the markers used to leak as literal
    "**" in the rendered statement. Punctuation moves outside the markers."""
    html = "<p><strong>进阶：</strong>你可以想出更快的算法吗？</p>"
    md = problems.html_to_markdown(html)
    assert md.strip() == "**进阶**：你可以想出更快的算法吗？"


def test_html_strong_inner_whitespace_moved_outside():
    html = "<p><strong>和为目标值 </strong><em><code>target</code></em></p>"
    md = problems.html_to_markdown(html)
    # trailing space inside the wrap broke the closer; it moves outside, and
    # the whitespace keeps the two adjacent runs unambiguous
    assert md.strip() == "**和为目标值** *`target`*"


def test_html_empty_strong_dropped():
    html = "<p>a<strong></strong>b</p>"
    md = problems.html_to_markdown(html)
    assert "****" not in md
    assert "ab" in md
