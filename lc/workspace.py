"""Per-problem workspace materialization.

Layout: one directory per problem under <workspace_root>/problems/, named
``0001-two-sum`` (numeric frontend id) or ``<slug>`` otherwise. Files:

- statement.md   regenerable converter output (htmltomd), overwritten on refresh
- cases.json     regenerable official example cases, overwritten on refresh
- testcases.txt  user-owned; backed up to .bak before overwrite when edited
- solution.<ext> user-owned; templates fetched on demand, same backup rule
- notes.md       fully user-owned; refresh never touches it
- meta.json      internal bookkeeping: internal_question_id and the hashes of
                 programmatic writes to protected files (the refresh backup rule)

``STATEMENT_VERSION`` versions the converter output: a bump makes open_problem
lazily regenerate stored statement.md files (online) so existing workspaces
heal without user action.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from lc.atomicio import atomic_write_text
from lc.exceptions import NetworkError, PremiumProblemError
from lc.htmltomd import html_to_markdown
from lc.i18n import t
from lc.langs import DEFAULT_LANGUAGE, LANGUAGE_REGISTRY, extension_for

# statement.md is regenerable program output of lc.htmltomd; a change in its
# output shape bumps this and open_problem lazily regenerates stored files
# (online) so existing workspaces heal without user action
# v3: GFM pipe tables (v2 rows rendered as literal text) + no literal "**"
# inside code spans
STATEMENT_VERSION = 3

_DIR_NAME_RE = re.compile(r"^(\d+)-(.+)$")


def problem_dir_for(detail_or_summary: dict, workspace_root=None) -> Path:
    from lc.config import effective_config, workspace_root_path

    root = (
        Path(workspace_root)
        if workspace_root is not None
        else workspace_root_path(effective_config())
    )
    slug = detail_or_summary.get("slug") or "unknown-problem"
    frontend_id = str(detail_or_summary.get("frontend_id", "") or "")
    if frontend_id.isdigit():
        name = f"{int(frontend_id):04d}-{slug}"
    else:
        name = slug
    return root / "problems" / name


def find_problem_dir(workspace_root: Path, slug: str) -> Path | None:
    """Locate a materialized problem directory by its exact naming convention.

    A directory is either `<slug>` (non-numeric frontend id) or
    `<digits>-<slug>`. Parsing the convention (instead of a suffix check)
    matters: endswith(f"-{slug}") made slug "sum" hijack "0001-two-sum".
    """
    problems_dir = Path(workspace_root) / "problems"
    direct = problems_dir / slug
    if direct.exists():
        return direct
    if not problems_dir.exists():
        return None
    for child in sorted(problems_dir.iterdir()):
        if not child.is_dir():
            continue
        match = _DIR_NAME_RE.match(child.name)
        if match and match.group(2) == slug:
            return child
    return None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_meta(directory: Path) -> dict:
    meta_path = directory / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_meta(directory: Path, meta: dict) -> None:
    _write(
        directory / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2)
    )


def _write(path: Path, content: str) -> None:
    """Shared persistence primitive (tmp + os.replace with Windows retry).

    A bare write_text let a concurrent reader (or a crash mid-write) observe
    a half-flushed workspace file; the implementation lives in lc.atomicio
    so problems.json, config.toml, favorites.json and workspace files share
    one rename-retry policy instead of four drifting copies."""
    atomic_write_text(path, content, newline="")


def parse_sample_case(raw: str) -> list:
    lines = (raw or "").splitlines()
    return [line.strip() for line in lines if line.strip()]


def build_cases_payload(detail: dict) -> dict:
    """Official example cases as separate entries.

    The detail query returns exampleTestcases as a JSON-encoded list where
    each element is one full input block; those are authoritative. The single
    sampleTestCase is only a fallback for responses without examples, so the
    same case is not stored twice.
    """
    blocks = [block for block in (detail.get("example_test_cases") or []) if str(block).strip()]
    if not blocks:
        sample = detail.get("sample_test_case", "") or ""
        if sample.strip():
            blocks = [sample]
    cases = []
    for block in blocks:
        inputs = parse_sample_case(str(block))
        if inputs:
            cases.append({"inputs": inputs, "expected_output": None})
    return {"schema_version": 1, "cases": cases}


def _write_protected(path: Path, content: str, meta: dict, meta_key: str) -> bool:
    """Write a user-owned file; back up to .bak first when user-edited.

    Returns True when a backup was made.
    """
    backup_made = False
    if path.exists():
        current_hash = _sha256(path.read_text(encoding="utf-8"))
        if current_hash != meta.get(meta_key):
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup)
            backup_made = True
    _write(path, content)
    meta[meta_key] = _sha256(content)
    return backup_made


def snippets_by_lang(detail: dict) -> dict:
    return {snippet["lang_slug"]: snippet["code"] for snippet in detail.get("code_snippets", [])}


def statement_up_to_date(directory: Path) -> bool:
    return load_meta(directory).get("statement_version") == STATEMENT_VERSION


def regenerate_statement(directory: Path, detail: dict) -> None:
    """Re-generate statement.md from freshly fetched detail.

    Used when a stored workspace was materialized by an older converter
    (meta.json carries no/older statement_version): statement.md is
    regenerable program output, so it is overwritten directly while
    user-owned files stay untouched.
    """
    meta = load_meta(directory)
    _write(directory / "statement.md", html_to_markdown(detail.get("statement_html", "")))
    meta["statement_version"] = STATEMENT_VERSION
    save_meta(directory, meta)


def open_problem(detail: dict, workspace_root=None, default_language: str = DEFAULT_LANGUAGE) -> Path:
    directory = problem_dir_for(detail, workspace_root)
    directory.mkdir(parents=True, exist_ok=True)
    meta = load_meta(directory)

    _write(directory / "statement.md", html_to_markdown(detail.get("statement_html", "")))
    _write(
        directory / "cases.json",
        json.dumps(build_cases_payload(detail), ensure_ascii=False, indent=2) + "\n",
    )

    testcases_path = directory / "testcases.txt"
    if not testcases_path.exists():
        _write_protected(testcases_path, detail.get("sample_test_case", "") or "", meta, "testcases")

    internal_id = str(detail.get("internal_question_id", "") or "")
    if internal_id:
        meta["internal_question_id"] = internal_id
    meta["statement_version"] = STATEMENT_VERSION

    lang_snippets = snippets_by_lang(detail)
    template_code = lang_snippets.get(default_language)
    if template_code is not None:
        ext = extension_for(default_language)
        solution_path = directory / f"solution{ext}"
        if not solution_path.exists():
            _write_protected(solution_path, template_code, meta, f"template:{default_language}")

    save_meta(directory, meta)
    return directory


def refresh_problem(directory: Path, detail: dict, default_language: str = DEFAULT_LANGUAGE) -> dict:
    """Re-fetch protection rules: regenerable files overwritten directly,
    protected files backed up only when user-modified."""
    meta = load_meta(directory)
    backups = []

    _write(directory / "statement.md", html_to_markdown(detail.get("statement_html", "")))
    _write(
        directory / "cases.json",
        json.dumps(build_cases_payload(detail), ensure_ascii=False, indent=2) + "\n",
    )
    if _write_protected(
        directory / "testcases.txt",
        detail.get("sample_test_case", "") or "",
        meta,
        "testcases",
    ):
        backups.append("testcases.txt")

    template_code = snippets_by_lang(detail).get(default_language)
    if template_code is not None:
        ext = extension_for(default_language)
        if _write_protected(
            directory / f"solution{ext}", template_code, meta, f"template:{default_language}"
        ):
            backups.append(f"solution{ext}")

    meta["statement_version"] = STATEMENT_VERSION
    save_meta(directory, meta)
    return {"backups": backups}


def ensure_template(directory: Path, language: str, detail_provider) -> dict:
    ext = extension_for(language)
    if ext is None:
        raise ValueError(f"unsupported language: {language}")
    solution_path = directory / f"solution{ext}"
    if solution_path.exists():
        return {"status": "exists", "path": solution_path}
    detail = detail_provider()
    code = snippets_by_lang(detail).get(language)
    if code is None:
        if detail.get("paid_only"):
            raise PremiumProblemError(t("premium_problem"), detail={"slug": detail.get("slug")})
        raise NetworkError(
            t("template_missing_hint"),
            detail={"slug": detail.get("slug"), "lang": language},
        )
    meta = load_meta(directory)
    _write_protected(solution_path, code, meta, f"template:{language}")
    save_meta(directory, meta)
    return {"status": "written", "path": solution_path}


def save_testcases(directory: Path, content: str) -> None:
    _write(directory / "testcases.txt", content)


def read_notes(directory: Path) -> str:
    notes_path = Path(directory) / "notes.md"
    if not notes_path.exists():
        return ""
    try:
        return notes_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def save_notes(directory: Path, content: str) -> None:
    """Persist the user's per-problem notes.

    Notes are fully user-owned (like solution files): no meta.json hash is
    recorded, so refresh never touches them.
    """
    _write(Path(directory) / "notes.md", content)


def save_solution(directory: Path, language: str, code: str) -> Path:
    """Write editor content before judging; deliberately does NOT touch
    meta.json hashes so refresh still treats this as user-owned content."""
    ext = extension_for(language)
    if ext is None:
        raise ValueError(f"unsupported language: {language}")
    path = directory / f"solution{ext}"
    _write(path, code)
    return path


def available_languages(directory: Path) -> list:
    reverse = {ext: slug for slug, ext in LANGUAGE_REGISTRY.items()}
    found = []
    for path in sorted(Path(directory).glob("solution.*")):
        slug = reverse.get(path.suffix)
        if slug:
            found.append(slug)
    return found


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        # same degrade-to-empty policy as the cases.json / notes reads in
        # this module: on Windows a transient sharing violation (editor,
        # indexer or backup tool holding the file) used to turn a plain GET
        # of an open problem into a 500
        return ""


def stored_testcases(directory: Path) -> str:
    """testcases.txt contents; degrades to empty on transient read errors."""
    path = Path(directory) / "testcases.txt"
    if not path.exists():
        return ""
    return _read_text_or_empty(path)


def read_cases(directory: Path) -> list:
    """Official example cases stored in cases.json; degrade to empty."""
    cases_path = Path(directory) / "cases.json"
    if not cases_path.exists():
        return []
    try:
        return json.loads(cases_path.read_text(encoding="utf-8")).get("cases", [])
    except (json.JSONDecodeError, OSError):
        return []


def official_case_input(directory: Path) -> str:
    """Official case inputs newline-concatenated: the site expects every
    stored official case joined under data_input for a remote run."""
    inputs = []
    for case in read_cases(directory):
        inputs.extend(case.get("inputs") or [])
    return "\n".join(inputs)


def read_problem_state(directory: Path, default_language: str = DEFAULT_LANGUAGE) -> dict:
    """Workspace state for the workbench, resuming at the last-used language.

    The language reported is the most recently written solution.* - not the
    config default. The config default made every reopen land in a blank
    editor for a language the user may never have picked: their python3 work
    stayed on disk, but nothing on either side remembered that python3 was
    the language in use, and the only remedy was reselecting it by hand.
    Solution mtime is the natural memory: template fetches and pre-judge
    saves both touch exactly the file of the language last in play.
    """
    statement_path = directory / "statement.md"
    statement = (
        _read_text_or_empty(statement_path) if statement_path.exists() else ""
    )

    reverse = {ext: slug for slug, ext in LANGUAGE_REGISTRY.items()}
    language = default_language
    latest_path = None
    latest_mtime = -1.0
    for path in sorted(Path(directory).glob("solution.*")):
        if reverse.get(path.suffix) is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest_mtime:
            language = reverse[path.suffix]
            latest_path = path
            latest_mtime = mtime

    code = _read_text_or_empty(latest_path) if latest_path is not None else ""

    return {
        "statement_markdown": statement,
        "code": code,
        "language": language,
        "languages_available": available_languages(directory),
        "testcases": stored_testcases(directory),
        "cases": read_cases(directory),
        "solution_mtime": latest_mtime if latest_path is not None else 0.0,
        "notes": read_notes(directory),
    }
