"""Problem list synchronization, caching and workspace materialization.

Responsibilities:
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
- workspace materialization per problem directory (0001-two-sum naming,
  slug for non-numeric frontend ids): statement.md (regenerable),
  cases.json (regenerable), testcases.txt (protected), solution.<ext>
  templates fetched on demand (protected); user-edited protected files are
  backed up to .bak before overwrite on refresh, untouched ones are
  overwritten directly; meta.json records hashes of programmatic writes
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from lc.config import problems_cache_path
from lc.exceptions import NetworkError, PremiumProblemError
from lc.i18n import t
from lc.langs import DEFAULT_LANGUAGE, LANGUAGE_REGISTRY, extension_for
from lc.logutil import logger

CACHE_SCHEMA_VERSION = 1
PAGE_SIZE = 100

_UNSUPPORTED_CATEGORY_MARKERS = ("database", "sql", "shell", "concurrency", "pandas")

_CACHE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# HTML -> Markdown conversion (self-authored, covers cn-site statement tags)


class _HTMLToMarkdown(HTMLParser):
    _HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}
    _BLOCK_END = {"p", "div", "blockquote"} | set(_HEADINGS)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.buf = []
        self.pending_prefix = ""
        self.list_stack = []  # entries: {"ordered": bool, "n": int}
        self.in_table = False
        self.pre_lines = None
        self.pre_language = ""
        self.link_stack = []

    def flush_block(self):
        text = "".join(self.buf).strip()
        if text:
            self.blocks.append(self.pending_prefix + text)
        self.buf = []
        self.pending_prefix = ""

    @staticmethod
    def _attr(attrs, name):
        for key, value in attrs:
            if key == name:
                return value or ""
        return ""

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self.flush_block()
            classes = self._attr(attrs, "class")
            match = re.search(r"language-([\w+#-]+)", classes)
            self.pre_language = match.group(1) if match else ""
            self.pre_lines = []
            return
        if tag == "code" and self.pre_lines is not None and not self.pre_language:
            classes = self._attr(attrs, "class")
            match = re.search(r"language-([\w+#-]+)", classes)
            if match:
                self.pre_language = match.group(1)
            return
        if tag == "br":
            self.buf.append("\n")
            return
        if tag in ("ul", "ol"):
            self.flush_block()
            self.list_stack.append({"ordered": tag == "ol", "n": 0})
            return
        if tag == "li":
            self.flush_block()
            level = self.list_stack[-1] if self.list_stack else {"ordered": False, "n": 0}
            if level["ordered"]:
                level["n"] += 1
                self.buf.append(f"{level['n']}. ")
            else:
                self.buf.append("- ")
            return
        if tag in self._HEADINGS:
            self.flush_block()
            self.pending_prefix = self._HEADINGS[tag]
            return
        if tag in ("strong", "b"):
            self.buf.append("**")
            return
        if tag in ("em", "i"):
            self.buf.append("*")
            return
        if tag == "code" and self.pre_lines is None:
            self.buf.append("`")
            return
        if tag == "sup":
            self.buf.append("^")
            return
        if tag in ("td", "th"):
            # keep cells distinguishable when the statement carries a table
            if self.buf and self.in_table:
                self.buf.append(" | ")
            return
        if tag == "table":
            self.flush_block()
            self.in_table = True
            return
        if tag == "a":
            href = self._attr(attrs, "href") or ""
            self.buf.append("[")
            self.link_stack.append(href)
            return
        if tag == "img":
            src = self._attr(attrs, "src") or ""
            alt = self._attr(attrs, "alt") or ""
            self.buf.append(f"![{alt}]({src})")
            return

    def handle_endtag(self, tag):
        if tag == "pre":
            code = "".join(self.pre_lines).strip("\n")
            fence = f"```{self.pre_language}" if self.pre_language else "```"
            self.blocks.append(f"{fence}\n{code}\n```")
            self.pre_lines = None
            self.pre_language = ""
            return
        if tag in ("strong", "b"):
            self.buf.append("**")
            return
        if tag in ("em", "i"):
            self.buf.append("*")
            return
        if tag == "code" and self.pre_lines is None:
            self.buf.append("`")
            return
        if tag == "a":
            href = self.link_stack.pop() if self.link_stack else ""
            label = "".join(self.buf).strip()
            self.buf = [label + f"]({href})" if href else label + "]"]
            return
        if tag == "li":
            self.flush_block()
            return
        if tag in ("ul", "ol"):
            self.flush_block()
            if self.list_stack:
                self.list_stack.pop()
            return
        if tag == "table":
            self.in_table = False
            self.flush_block()
            return
        if tag == "tr" and self.in_table:
            self.flush_block()
            return
        if tag in self._BLOCK_END:
            self.flush_block()

    def handle_data(self, data):
        if self.pre_lines is not None:
            self.pre_lines.append(data)
            return
        collapsed = re.sub(r"[ \t\r\f\v]+", " ", data.replace("\n", " "))
        self.buf.append(collapsed)

    def close(self):
        super().close()
        self.flush_block()


def html_to_markdown(html_text: str) -> str:
    """Convert leetcode statement HTML into plain markdown-ish text.

    Formulas stay as raw text (sup/sub flattened); images keep markdown
    syntax so they render online and visibly break offline (documented
    v0.1 limitation).
    """
    parser = _HTMLToMarkdown()
    parser.feed(html_text or "")
    parser.close()
    joined = "\n\n".join(block.strip() for block in parser.blocks if block.strip())
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip() + ("\n" if joined else "")


# ---------------------------------------------------------------------------
# Cache read/write


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


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


# ---------------------------------------------------------------------------
# Sync engine


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
        self._started_at = _utc_now_iso()
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
                self._finished_at = _utc_now_iso()

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
                "synced_at": _utc_now_iso(),
                "total": len(ordered),
                "problems": ordered,
            }
        with _CACHE_LOCK:
            save_problems(payload, cache_path)


# ---------------------------------------------------------------------------
# Workspace materialization


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


_DIR_NAME_RE = re.compile(r"^(\d+)-(.+)$")


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
    (directory / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _write_regenerable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


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
    path.write_text(content, encoding="utf-8")
    meta[meta_key] = _sha256(content)
    return backup_made


def snippets_by_lang(detail: dict) -> dict:
    return {snippet["lang_slug"]: snippet["code"] for snippet in detail.get("code_snippets", [])}


def open_problem(detail: dict, workspace_root=None, default_language: str = DEFAULT_LANGUAGE) -> Path:
    directory = problem_dir_for(detail, workspace_root)
    directory.mkdir(parents=True, exist_ok=True)
    meta = load_meta(directory)

    _write_regenerable(directory / "statement.md", html_to_markdown(detail.get("statement_html", "")))
    _write_regenerable(
        directory / "cases.json",
        json.dumps(build_cases_payload(detail), ensure_ascii=False, indent=2) + "\n",
    )

    testcases_path = directory / "testcases.txt"
    if not testcases_path.exists():
        _write_protected(testcases_path, detail.get("sample_test_case", "") or "", meta, "testcases")

    internal_id = str(detail.get("internal_question_id", "") or "")
    if internal_id:
        meta["internal_question_id"] = internal_id

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

    _write_regenerable(directory / "statement.md", html_to_markdown(detail.get("statement_html", "")))
    _write_regenerable(
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
    (directory / "testcases.txt").write_text(content, encoding="utf-8")


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
    (Path(directory) / "notes.md").write_text(content, encoding="utf-8")


def save_solution(directory: Path, language: str, code: str) -> Path:
    """Write editor content before judging; deliberately does NOT touch
    meta.json hashes so refresh still treats this as user-owned content."""
    ext = extension_for(language)
    if ext is None:
        raise ValueError(f"unsupported language: {language}")
    path = directory / f"solution{ext}"
    path.write_text(code, encoding="utf-8")
    return path


def available_languages(directory: Path) -> list:
    reverse = {ext: slug for slug, ext in LANGUAGE_REGISTRY.items()}
    found = []
    for path in sorted(Path(directory).glob("solution.*")):
        slug = reverse.get(path.suffix)
        if slug:
            found.append(slug)
    return found


def read_problem_state(directory: Path, default_language: str = DEFAULT_LANGUAGE) -> dict:
    statement = ""
    statement_path = directory / "statement.md"
    if statement_path.exists():
        statement = statement_path.read_text(encoding="utf-8")
    code = ""
    default_ext = extension_for(default_language)
    solution_path = directory / f"solution{default_ext}" if default_ext else None
    if solution_path is not None and solution_path.exists():
        code = solution_path.read_text(encoding="utf-8")
    testcases = ""
    testcases_path = directory / "testcases.txt"
    if testcases_path.exists():
        testcases = testcases_path.read_text(encoding="utf-8")
    cases = []
    cases_path = directory / "cases.json"
    if cases_path.exists():
        try:
            cases = json.loads(cases_path.read_text(encoding="utf-8")).get("cases", [])
        except (json.JSONDecodeError, OSError):
            cases = []
    solution_mtime = 0.0
    if solution_path is not None and solution_path.exists():
        solution_mtime = solution_path.stat().st_mtime
    return {
        "statement_markdown": statement,
        "code": code,
        "language": default_language,
        "languages_available": available_languages(directory),
        "testcases": testcases,
        "cases": cases,
        "solution_mtime": solution_mtime,
        "notes": read_notes(directory),
    }


def summary_from_detail(detail: dict) -> dict:
    keys = ("slug", "frontend_id", "title_en", "title_cn", "difficulty", "paid_only", "category", "tags")
    return {key: detail.get(key) for key in keys}
