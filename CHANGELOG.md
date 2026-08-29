# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Root-cause analyses for every fix live in [docs/zh/PITFALLS.md](docs/zh/PITFALLS.md);
the full development history lives in the git log.

## [Unreleased]

### Changed

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
