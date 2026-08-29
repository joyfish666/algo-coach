"""Per-problem workspace materialization (lc.workspace)."""

import json
import os

import pytest

from lc import workspace
from lc.atomicio import atomic_write_text


def test_problem_dir_name_numeric_zfill(tmp_path):
    directory = workspace.problem_dir_for({"slug": "two-sum", "frontend_id": "1"}, tmp_path)
    assert directory == tmp_path / "problems" / "0001-two-sum"


def test_problem_dir_name_non_numeric_uses_slug(tmp_path):
    directory = workspace.problem_dir_for(
        {"slug": "shu-zu-zhong-zhong-fu-de-shu-zi-lcof", "frontend_id": "剑指 Offer 03"}, tmp_path
    )
    assert directory.name == "shu-zu-zhong-zhong-fu-de-shu-zi-lcof"


def test_problem_dir_for_honors_configured_workspace_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOCOACH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ALGOCOACH_WORKSPACE_ROOT", str(tmp_path / "custom"))
    directory = workspace.problem_dir_for({"slug": "two-sum", "frontend_id": "1"})
    assert directory == tmp_path / "custom" / "problems" / "0001-two-sum"


def test_find_problem_dir_rejects_suffix_collision(tmp_path):
    """Regression: slug 'sum' must not hijack the '0001-two-sum' directory -
    matching parses the '<digits>-<slug>' convention instead of endswith."""
    problems_dir = tmp_path / "problems" / "0001-two-sum"
    problems_dir.mkdir(parents=True)
    assert workspace.find_problem_dir(tmp_path, "two-sum") == problems_dir
    assert workspace.find_problem_dir(tmp_path, "sum") is None


def test_find_problem_dir_matches_prefixed_and_plain_dirs(tmp_path):
    prefixed = tmp_path / "problems" / "0007-reverse-integer"
    plain = tmp_path / "problems" / "shu-zu-lcof"
    prefixed.mkdir(parents=True)
    plain.mkdir(parents=True)
    assert workspace.find_problem_dir(tmp_path, "reverse-integer") == prefixed
    assert workspace.find_problem_dir(tmp_path, "shu-zu-lcof") == plain
    assert workspace.find_problem_dir(tmp_path, "missing") is None


def test_build_cases_payload_uses_example_testcases():
    detail = {
        "sample_test_case": "[2,7,11,15]\n9",
        "example_test_cases": ["[2,7,11,15]\n9", "[3,2,4]\n6"],
    }
    payload = workspace.build_cases_payload(detail)
    assert [case["inputs"] for case in payload["cases"]] == [
        ["[2,7,11,15]", "9"],
        ["[3,2,4]", "6"],
    ]


def test_build_cases_payload_falls_back_to_sample():
    payload = workspace.build_cases_payload({"sample_test_case": "a\nb"})
    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["inputs"] == ["a", "b"]
    assert workspace.build_cases_payload({})["cases"] == []


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
    directory = workspace.open_problem(detail_fixture, tmp_path, default_language="cpp")
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
    meta = workspace.load_meta(directory)
    assert "testcases" in meta
    assert "template:cpp" in meta
    state = workspace.read_problem_state(directory, default_language="cpp")
    assert state["languages_available"] == ["cpp"]
    assert state["language"] == "cpp"


def test_refresh_backs_up_user_edited_testcases_only(tmp_path, detail_fixture):
    directory = workspace.open_problem(detail_fixture, tmp_path)

    modified = detail_fixture.copy()
    modified["sample_test_case"] = "[1,2]\n3"
    result = workspace.refresh_problem(directory, modified)
    assert result["backups"] == []

    user_content = "[9,9]\n18\nmy custom case"
    (directory / "testcases.txt").write_text(user_content, encoding="utf-8")
    result = workspace.refresh_problem(directory, detail_fixture)
    assert "testcases.txt" in result["backups"]
    backup = (directory / "testcases.txt.bak").read_text(encoding="utf-8")
    assert backup == user_content
    current = (directory / "testcases.txt").read_text(encoding="utf-8")
    assert current == "[2,7,11,15]\n9"

    statement_before = (directory / "statement.md").read_text(encoding="utf-8")
    workspace.refresh_problem(directory, detail_fixture)
    statement_after = (directory / "statement.md").read_text(encoding="utf-8")
    assert statement_before == statement_after


def test_ensure_template_fetches_once_then_exists(tmp_path, detail_fixture):
    directory = workspace.open_problem(detail_fixture, tmp_path)
    calls = []

    def provider():
        calls.append(1)
        return detail_fixture

    result = workspace.ensure_template(directory, "python3", provider)
    assert result["status"] == "written"
    assert (directory / "solution.py").exists()
    result = workspace.ensure_template(directory, "python3", provider)
    assert result["status"] == "exists"
    assert len(calls) == 1


def test_ensure_template_unsupported_language_raises(tmp_path, detail_fixture):
    directory = workspace.open_problem(detail_fixture, tmp_path)
    with pytest.raises(ValueError):
        workspace.ensure_template(directory, "golang", lambda: detail_fixture)


def test_save_testcases_updates_file(tmp_path, detail_fixture):
    directory = workspace.open_problem(detail_fixture, tmp_path)
    workspace.save_testcases(directory, "custom input line")
    assert (directory / "testcases.txt").read_text(encoding="utf-8") == "custom input line"


# ---------------------------------------------------------------------------
# workbench state: last-used language resume + transient read degrade


def _write_solution(directory, language, code):
    from lc.langs import extension_for

    atomic_write_text(directory / f"solution{extension_for(language)}", code, newline="")


def test_read_problem_state_resumes_last_used_language(tmp_path):
    """Reopening a problem used to land in the config default's (usually
    empty) editor: neither side remembered which language was last in play."""
    directory = tmp_path
    _write_solution(directory, "cpp", "// old cpp")
    _write_solution(directory, "python3", "# newest python work")
    # mtime granularity cannot distinguish two writes in the same clock tick
    # on some filesystems - pin the "python3 edited last" ordering explicitly
    os.utime(directory / "solution.cpp", (1000, 1000))
    os.utime(directory / "solution.py", (2000, 2000))

    state = workspace.read_problem_state(directory, default_language="cpp")
    assert state["language"] == "python3"
    assert state["code"] == "# newest python work"
    assert "python3" in state["languages_available"]


def test_read_problem_state_falls_back_to_default_when_single_template(tmp_path):
    directory = tmp_path
    _write_solution(directory, "cpp", "// template")
    state = workspace.read_problem_state(directory, default_language="cpp")
    assert state["language"] == "cpp"
    assert state["code"] == "// template"


def test_read_problem_state_tolerates_transient_read_errors(tmp_path, monkeypatch):
    """statement/code/testcases reads had no OSError guard while sibling
    reads in the same function degraded to empty - a Windows sharing
    violation on one file turned a plain GET into a 500."""
    (tmp_path / "statement.md").write_text("hello", encoding="utf-8")
    real_read_text = type(tmp_path).read_text

    def flaky_read(self, *args, **kwargs):
        if self.name == "statement.md":
            raise PermissionError("sharing violation")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(tmp_path), "read_text", flaky_read)
    state = workspace.read_problem_state(tmp_path, default_language="cpp")
    assert state["statement_markdown"] == ""
