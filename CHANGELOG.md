# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Debug-run payload field corrected to `data_input` (matching the browser), which was the cause
  of site-side Internal Error on Run; interpret check responses lacking state/status_msg now
  count as finished via strong result markers, and compile/runtime errors classify properly.
- Session rotation: rotated LEETCODE_SESSION/csrftoken values returned by the site are persisted
  back to config automatically, so the backend stops fighting the browser over the newest value.

### Verified

- Full live round with a real session: sync of all 4421 problems across 45 pages without errors;
  two-sum Run and Submit with rich verdicts (65/65 accepted); daily problem; site import
  (17 imported, 3 deduped); analytics stats, SVG tag-mastery chart and recommendations.

- Live-network schema corrections for leetcode.cn (verified with a real session on 2026-08-23):
  the problem-list query now calls `problemsetQuestionList` directly and reads
  QuestionLightNode fields (`paidOnly`, `frontendQuestionId`, `nameTranslated` tags) instead of
  the guessed com-style shape that crashed sync; question detail drops the nonexistent
  `titleCn` in favor of `translatedTitle`; site submission imports use `submissionList`
  (`recentSubmissionList` does not exist) deriving slugs from submission URLs.
- The server no longer fails judge/daily/sync calls with "cookie missing" after a fresh start:
  the auth singleton now lazily initializes from config on first adapter use.
- The setup wizard's validate button is wired up (it existed only as an unbound function since
  the skeleton), with explicit Validate/Next gating covered by component tests.

### Added

- AI defaults switched to DeepSeek: base URL https://api.deepseek.com and model
  deepseek-v4-flash are prefilled in the wizard and used as fallbacks server-side.
- Data transparency: /api/status exposes the data directory; a new "Data & privacy" settings card
  shows it and offers a one-click erase of everything under ~/.algocoach (cache, archive,
  workspace, config) returning the app to the unconfigured state; usage FAQ documents location,
  deletion and the session-rotation pitfall behind seemingly-valid cookies expiring.
- Packaging polish and release readiness (stage 7): the built frontend is now served directly by
  `coach` through a dist resolution chain (ALGOCOACH_DIST override → repository web/dist →
  packaged server/webdist copy shipped via package-data) with an SPA catch-all fallback to
  index.html, traversal protection and an API-only JSON hint mode when no build exists; a
  single-instance guard built on an O_CREAT|O_EXCL instance lock recording pid and port, PID
  liveness probing (ctypes OpenProcess on Windows, avoiding os.kill signal semantics), stale-lock
  takeover, plus an /api/status probe before port shifting so a running coach refuses duplicates
  instead of silently starting beside it; verified end-to-end from a non-editable pip install.
- Archive, LLM and analytics layer (stage 6): an append-only JSON Lines submission archive whose
  records embed difficulty/tags/lang plus full verdict fields so one line powers analytics and AI
  reports; a lock-guarded qid→latest-verdict index with startup reload and torn-line tolerance;
  submit-mode verdicts now archive automatically (run mode never does) with cache self-healing
  enrichment; site import of the last ~20 recent submissions deduplicated by submission_id; a
  stateless OpenAI-compatible client reusing forced timeouts but no rate limiting or site header
  injection; POST /api/ask combining current problem info and the latest archived verdict as
  context with server-side history trimming; POST /api/analyze producing solved counts by
  difficulty, weakest-first tag mastery and heuristic recommendations from unsolved problems
  sharing weak tags, optionally enriched with an AI weakness report when an LLM key is configured.
- Workbench AI sidebar and analytics UI: a floating AI coach panel on the problem page holding
  the conversation statelessly in the frontend; the analyze page renders stat cards, a
  hand-written SVG horizontal tag-mastery chart (weak to strong), recommended-practice links,
  an import button with result feedback and a markdown-rendered AI report behind an explicit
  generate action.
- Problems list, setup wizard and daily page (stage 5): a card-based problem list with local
  keyword/difficulty/tag filtering (non-numeric frontend ids like 剑指 Offer searchable), local
  pagination, premium and unsupported-category markers, one-click sync with per-second progress
  polling, expected-duration messaging and completion feedback; a three-step setup wizard that
  validates the pasted cookie against the backend before proceeding, optionally collects LLM
  credentials and finishes with language plus theme preferences; a daily-problem card linking to
  the workbench; a global auth-expired banner triggered by any 401 AuthError response guiding the
  user back to setup, closing the cookie-expiry loop; and an update-cookie shortcut on the
  settings page.
- Answering workbench (stage 4): judge pipeline with save-before-judge semantics, run mode via
  the remote interpret flow that never enters submission history, submit mode with bounded
  polling (120s) handling intermediate states and an explicit status-unknown verdict carrying the
  traceable submission_id after timeout plus one final detail lookup; rich result normalization
  classifying verdicts from human-readable messages with runtime/memory percentiles, WA expected/
  actual comparison arrays, CE details and RE output; server endpoints for run, submit and editor
  code persistence; frontend workbench rendering the converted statement through markdown-it with
  HTML escaped, tag/difficulty chips, collapsible hints, language switching that fetches missing
  templates on demand, debounced autosave plus localStorage draft snapshots (LRU-capped at twenty)
  with restore prompts, an in-flight-guarded Run/Submit button pair, a custom-testcases panel
  writing back to testcases.txt for local-input runs, and a verdict panel showing big-status,
  beat percentages, WA diff table and collapsible CE/RE/stdout blocks.
- Frontend skeleton (stage 3): a zh/en i18n store with browser-locale detection and localStorage
  persistence, a backend status store consumed by the route guard (unconfigured visitors land on
  the setup page; an unreachable backend degrades gracefully), a redesigned sidebar with
  hand-written thin-line SVG icons, an icon-based theme switcher plus language switcher, shared
  design-system primitives (cards, pill buttons, inputs, chips, empty states) built on the dual
  theme tokens, restyled skeleton views including analytics stat cards and a two-pane workbench
  preview with the CodeMirror editor, and vitest/jsdom unit coverage for theme persistence and
  i18n behavior.
- Problem data layer and REST surface (stage 2): a thread-safe sync engine paging the full
  problem list into problems.json with atomic writes, in-process resume after a failed page,
  slug/frontendQuestionId duplicate skipping without aborting, and unsupported-category marking;
  workspace materialization per problem directory (zero-padded numeric or slug naming) writing a
  self-authored HTML-to-markdown statement conversion, structured sample cases, prefilled custom
  testcases and on-demand code templates, with user-edited files backed up to .bak on refresh via
  programmatic-write hash bookkeeping; server endpoints for status, cookie validation, masked
  settings read/update with immediate session rebuild, problem list, sync start/progress with
  409 conflict handling, daily question, problem open/refresh with offline reads and cache
  self-healing write-back, template fetching and testcase saving; local Origin/Host guard
  middleware with method-tiered enforcement and domain-exception translation into structured
  error JSON.
- Core library layer (stage 1): configuration stored as `~/.algocoach/config.toml` with schema
  versioning, atomic writes, restrictive permissions on POSIX and the CLI > environment > file
  priority chain; a unified HTTP client enforcing mandatory timeouts, thread-safe rate limiting
  (default interval plus jitter), retries restricted to idempotent reads and Retry-Aware 429
  backoff that honors both integer-second and HTTP-date header forms capped at 30 seconds; an
  authentication module building sessions from pasted cookie strings, extracting CSRF tokens,
  detecting cookie expiration across the 403 / login-redirect / 200-with-errors shapes and
  rebuilding shared singletons immediately after credential updates; a bilingual zh/en message
  catalog selected by system locale with manual override; and a leetcode.cn site adapter that
  concentrates all GraphQL query organization and response parsing in one place, covering cookie
  validation, paged problem lists, question details with code templates and sample cases, and
  the daily question.
- Project skeleton: Python packaging (`algocoach`) with the `coach` console entry point that binds
  to 127.0.0.1 only, auto-increments occupied ports and opens the browser once ready; Vue 3 + Vite
  web scaffold with the five-color minimalist design token system and light/dark themes; GitHub
  Actions CI matrix (ubuntu / windows / macos) running pytest and the frontend build; bilingual
  README; Chinese documentation framework (USAGE / DEVELOPMENT / ARCHITECTURE / ROADMAP /
  PITFALLS).
- Requirement analysis and design decisions made during planning (August 2026) are consolidated
  into the documentation set above, including the canonical slug key for problems, the language
  registry, request discipline (rate limiting, idempotent-only retries), local storage layout and
  known pitfalls.
