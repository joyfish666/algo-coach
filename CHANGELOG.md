# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Root-cause analyses for every fix live in [docs/zh/PITFALLS.md](docs/zh/PITFALLS.md);
the full development history lives in the git log.

## [Unreleased]

### Fixed

- **Statement tables render as tables**: the HTML->Markdown converter flushed
  every `<tr>` as a standalone paragraph - tag-gap whitespace emitted a
  phantom leading "|", rows kept no trailing pipe, and no delimiter row ever
  appeared, so markdown-it rendered whole tables as literal text (e.g.
  颠倒二进制位's 整数/二进制 tables). Rows are now GFM pipe rows with a
  delimiter row after the first, pipes inside cells are escaped, and block
  tags inside cells stay inline (`STATEMENT_VERSION` bumped to 3; stored
  statements regenerate lazily on the next online open).
- **Literal "\*\*1\*\*" inside inline code**: statements wrapping bold inside
  a code span (`<code><strong>1</strong></code>`, e.g. 可被 K 整除的最小整数)
  emitted `` `**1**` `` and the asterisks rendered literally. Emphasis that
  opens inside an inline code span now drops its markers (the code font
  already reads as emphasis).
- The favorite toggle shows one consistent five-pointed star everywhere (SVG,
  outline when unfavorited, filled when favorited) instead of the ★/☆ text
  glyphs whose shape depended on the platform font.

### Changed

- **Notes became a floating sub-panel like the AI coach**: the notes card
  under the statement moved into a draggable, Escape-closable floating panel
  (same mechanics, autosave and flush contract as before), and both panels
  now toggle from two identical accent circular buttons stacked on the right
  edge (AI coach on top, notes below). Opening one closes the other since
  they share the same screen corner, and both open at one shared, persisted
  position (a pre-merge dragged AI-panel spot is adopted).
- **The workbench owns one viewport**: the problem-detail page no longer
  scrolls as a whole - the statement pane, editor and judge-result panel each
  scroll internally when content outgrows the screen (a long 题面 scrolls
  inside its card instead of pushing the page).
- The vertical workbench split is gone: the editor always stretches to fill
  the space above the cases zone. The custom-cases panel starts collapsed and,
  when expanded, is content-sized so it always shows fully; the horizontal
  divider now sizes (and opens) the cases zone instead.
- Statement / AI-chat / report markdown tables render with a visible grid
  (borders and a tinted header row) - pipe tables arrived borderless before.
- Scrollbars are theme-aware everywhere (token-colored thumb, transparent
  track): the browser-default light scrollbar no longer glares on the dark
  statement pane.
- The AI-coach launcher reads "AI" instead of the sparkle glyph; the two
  floating-panel buttons share one accent circle style.
- The judge-result panel gained a close button, so a finished run/submit can
  be dismissed without running anything.
- The web-UI keep-alive heartbeat is sent every 10s (was 20s) and the bundled
  `start.bat` retires the server after 30s without one (was 2 minutes).

### Added

- **Idle auto-exit**: every open web-UI tab sends a heartbeat (~every 20s);
  `coach --idle-exit MINUTES` retires the server once the last tab has been
  closed for the deadline (a running problem sync defers the exit), so the
  double-click `start.bat` launcher now closes its window with the site.
  Plain `coach` keeps the previous always-on behavior.
- **Windows launcher**: double-click `start.bat` starts the server from the
  project venv and opens the browser; it verifies the one-time prerequisites
  (package install, built frontend) and prints exactly what is missing.
  Launching it again while an instance runs adopts that instance - it opens
  the site in the browser (resetting the idle clock) and exits cleanly,
  never starting a second server or showing an error window.

### Changed

- The problem-list filter bar stays on one row: the filter selects drop the
  "全部" prefix (状态 / 难度 / 标签 as placeholder-style labels, mirrored in
  English) and each control gets a width fitted to its option text, so no
  single oversized select pushes the density toggle to a second line; the
  search box grows only to a cap, and on very narrow windows flex shrink
  (not horizontal scrolling) absorbs the squeeze.
- Backend structure (no behavior change): `server/api.py` split into a package —
  `app.py` (composition root), `errors.py` (one error envelope),
  `state.py` (process singletons), and `routers/` grouped by concern
  (settings / problems / coach / archive); `lc/problems.py` split into
  `lc/htmltomd.py` (statement converter), `lc/problems.py` (cache + sync)
  and `lc/workspace.py` (per-problem materialization); coach prompt
  engineering moved to `lc/coach.py`.
- Every error response now uses a single envelope,
  `{"error": {kind, message_key, message, detail?}}`; the frontend
  normalizer and the per-view error extraction collapsed accordingly.
- Frontend: duplicated per-view helpers consolidated into shared modules
  (`utils/errors.js`, `utils/difficulty.js`, `utils/languages.js`,
  `utils/markdown.js`, `utils/storage.js`); settings API field list,
  env overrides and the masked view now derive from `lc.config.DEFAULTS`.
- The answering workbench (`ProblemDetail.vue`, ~1000 lines) is split into
  focused children (`ProblemStatement`, `CasesPanel`, `JudgingIndicator`,
  `ProblemMetaRow`); the parent keeps orchestration only and the
  data-loss-prevention flush contracts are pinned by new tests.

### Fixed

- Pasting a cookie without `csrftoken` (LEETCODE_SESSION only) poisoned the
  whole session: leetcode.cn re-issues csrftoken on two domain variants, and
  the duplicate made every cookie lookup raise CookieConflictError - the
  rotation hook died on each response (no session or csrf persistence,
  warning per request) and csrf header reads broke. Cookie lookups are now
  conflict-tolerant, the jar collapses duplicates to the newest value, and
  the site-issued token is adopted onto the session so judge submit carries
  it.
- Random pick no longer selects premium problems (their statement fetch
  degrades to a premium error); it draws only from free rows within the
  current filter and explains in a toast when every match is paid.
- CI: the wheel-packaging job never installed node_modules, so every run
  failed at its first step (`vite: not found`) since the job was
  introduced; `npm ci` now runs before the frontend build.
- Tests are now physically isolated from the real data directory: conftest
  redirects `ALGOCOACH_HOME` to a per-test temp directory by default. A
  split test file had lost its environment-isolation fixture and its
  data-wipe regression ran against the live `~/.algocoach`, erasing real
  local data (recorded in PITFALLS); the safety net makes that class of
  bug structurally impossible.

## [0.1.0] - 2026-08-29

### Added

- **Practice workbench** for leetcode.cn: rendered statement, CodeMirror 6
  editor with theme-aware highlighting, Run (remote interpret, never enters
  submission history) and Submit (bounded polling, rich verdicts with
  runtime/memory percentiles, WA case diff, CE/RE details), custom testcases,
  per-problem notes, favorites, and last-used-language resume on reopen.
- **Problem list**: full-catalog sync (~4400 problems) with resumable
  progress that survives page switches and reloads; practice-status /
  difficulty / tag / keyword filters, random pick within the current filter,
  compact density mode, URL-driven filter state.
- **AI coach**: stateless per-problem chat sidebar (latest verdict and
  problem context attached automatically, opt-in editor-code attachment,
  markdown-rendered replies, follows the interface language) and an
  analytics weakness report with regenerate; both gated on LLM availability
  with a setup hint when unconfigured.
- **LLM configuration** in Settings, independent of the cookie: API key /
  base URL / model / thinking mode (`off/low/medium/high` mapped to the
  common OpenAI-compatible conventions) with a one-click connectivity probe
  (test never saves).
- **Analytics dashboard**: solved stats by difficulty, tag-mastery chart,
  heuristic recommendations, AI weakness report.
- **Submission history** over the local JSON Lines archive (filterable by
  problem, expandable WA/CE/RE details) and one-click site-side import
  (submission_id dedup, chronological append order).
- **Local-first storage**: everything under `~/.algocoach/` (config.toml,
  problems cache, archive, per-problem workspace files you own); opened
  problems stay reviewable offline. Destructive erase requires typing
  `DELETE` and also purges browser-side code drafts (theme/language
  preferences survive).
- **Packaging & operations**: `coach` entry point serving the built frontend
  (dist resolution chain + SPA fallback with traversal protection and 404
  for stale hashed chunks), single-instance guard (O_EXCL lock with pid
  liveness, `/api/status` probe before port shift, pre-bound socket handed
  to uvicorn), rotating file log, bilingual zh/en UI with light/dark themes.
- **Hardening**: Origin/Host guard middleware (DNS-rebinding protection),
  slug whitelist against path traversal, atomic writes for every persistent
  file (with a Windows sharing-violation retry), rate limiting with capped
  backoff honoring `Retry-After`, config write mutex, cookie-rotation
  persistence with currency re-check, startup validation of environment
  overrides and the config file.

### Fixed

- Statement rendering corruption (`********` runs, leaked `**` markers around
  CJK bold) — the HTML→Markdown converter treats in-fence tags as literal
  text and emits flanking-safe emphasis; stored statements self-heal via a
  converter version stamp.
- Silent workbench data loss on mount/problem-switch and on failed language
  switches (async watcher flush fenced with an explicit hydrating flag).
- Multi-writer config.toml races (settings save reverted by a concurrent
  cookie rotation; erased cookie resurrected after the data wipe) — one
  update lock next to the file.
- Submit-then-archive-failure no longer masks the verdict as a 500
  (`archived: false` + toast; the submission cannot be replayed).
- Transient workspace read/write collisions degrade instead of failing a
  plain GET; every debounced save flushes on leave/switch (notes and code).
- Sync semantics: a second "sync now" always re-reads the site (resume only
  after a failed run); unknown list totals no longer truncate after page
  one; a backend restart mid-sync is reported as interrupted, not complete.
- Error wording follows the UI language for every error shape (message_key
  protocol); network-level failures show a localized message instead of raw
  browser text.
- LLM `content: null` (reasoning-style endpoints) no longer surfaces as the
  literal answer "None".
- Single-instance guard closes the zero-byte lock window and the
  successor-lock deletion window; a corrupt config.toml refuses startup with
  the file named instead of 500-ing every endpoint.
- IME composition Enter no longer sends half-typed drafts; Run/Submit/lang
  switches are mutually excluded; stale chunks trigger a page reload;
  dark mode ships a proper editor palette; secondary text meets WCAG AA.

[Unreleased]: https://github.com/joyfish666/algo-coach/compare/v0.1.0...HEAD
