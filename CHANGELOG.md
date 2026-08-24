# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Feature completion + second review pass (2026-08-24)

Every fix again lists its root cause; symptom patches were not accepted.

**Features**

- Problem list gains practice-status filtering (solved / attempted / not-tried /
  favorites), per-problem favorites with an index file `~/.algocoach/favorites.json`,
  a random-pick button scoped to the current filter result, and a compact/cozy
  density toggle. Root cause of the gap: the archive already derived practice
  status but the list query never exposed it; favorites need list-level state for
  all 4400+ rows while workspace directories only exist for opened problems, so
  state lives in a dedicated index instead of per-directory meta flags.
- New `/history` view over the local archive (time / problem / lang / verdict /
  runtime / memory, expandable WA diff and CE/RE detail, filterable by problem).
  Backend reads converge on one locked scan primitive `Archive.query(slug, limit)`;
  the old `recent()` now delegates to it so read paths cannot drift.
- Per-problem notes (`notes.md` in the workspace, debounced autosave, untouched
  by refresh like solutions).
- AI coach questions can attach the current editor code explicitly (truncated at
  6000 chars); opt-in per question so casual asks don't upload long code.

**Bug fixes (root-caused)**

- Sync failures were invisible once a sync had ever succeeded: the header's
  display cascade ranked the stale "last synced" line above error text, so the
  error branch never rendered. Errors moved to a dedicated toast channel where
  failures persist until dismissed; inline spans only carry informational state.
- A transient save/judge failure tore down the entire workbench UI: fatal load
  errors and transient action errors shared one `errorText`. Now only load
  failure replaces the page (`loadError`); action failures toast and keep the
  editor alive.
- Leaving the problems page silently dropped the progress UI of an in-flight
  backend sync, and a backend restart mid-sync was announced as "sync complete":
  polling was owned by the view, and `progress()` reports `running:false`
  both for "finished" and "engine never ran". Polling moved into an app-level
  sync store that survives route changes and re-adopts a running backend sync
  after reload; genuine completion now requires `started_at`/`finished_at`.
- Every fetch now carries an abort deadline (default 45s; LLM/submit 150s;
  run 90s; import 120s) - previously a hung backend froze the calling view
  forever. Degrades to no-timeout when `AbortSignal.timeout` is unavailable.

**UI**

- Semantic color tokens (ok / warn / danger + soft variants) applied to
  difficulty chips, judge verdict headlines, WA diff column and warning banners -
  everything used to share a single blue accent. Dark theme regains card
  separation (subtle shadow + more opaque border instead of flat none).
- Skeleton rows replace the text-only loading card in the problem list; shortcut
  hints (`Ctrl ↵`, `Ctrl+⇧ ↵`) are permanently visible next to Run/Submit.

**Tests & tooling**

- Frontend 36 → 78 cases: new view tests (Problems incl. status filter /
  favorite rollback / random / density, History, Daily, Analyze, Settings),
  store tests for the new sync/toast stores, and a router smoke suite asserting
  every lazy chunk resolves plus guard redirects. Browser-level E2E remains a
  registered deferred decision (heavyweight dep vs. repo policy, see ROADMAP).
- Backend 188 → 199 cases: favorites store/endpoint, notes roundtrip,
  archive qid filtering, ask-with-code context, corrupt-line tolerance.
- New `npm run check:i18n`: static scan proving every `t('...')` key exists in
  both zh and en catalogs - first run immediately caught a live bug where the
  auth-expired banner rendered the raw key `action_relogin` as its button label.
- pytest now reports coverage by default (pytest-cov added to dev extras;
  lc/ + server/, branch coverage).

**Docs**

- ARCHITECTURE: storage layout (favorites.json, notes.md), REST contract rows
  for the new endpoints/params, frontend global-store notes. USAGE: new pages,
  toast behavior, timeout/interrupted-sync error table entries. PITFALLS: five
  backfilled traps (error-channel masking, empty-progress ambiguity,
  fatal-vs-transient error split, test-client URL dot-segment normalization,
  AbortSignal.timeout fallback). DEVELOPMENT: check:i18n and coverage usage.
  ROADMAP: this batch table + deferred browser-E2E decision. README feature
  lists updated in both languages.

### Hardening pass (2026-08-24): full review across design / UI / logic / tests / docs

Every fix below lists its root cause; symptom patches were not accepted.

**Functional**

- Sync engine: a second "sync now" used to resume past the final page and exit
  instantly, hiding site-side additions until process restart. Root cause:
  resume semantics were tied to "rows exist" instead of "last run failed";
  accumulators are now reset on every start that does not follow a failed run
  (`progress().resumable` now reflects the same condition). Regression-tested.
- Workspace lookup: `find_problem_dir` matched directories with `endswith`,
  letting slug `sum` hijack `0001-two-sum` (wrong read/write/judge target).
  Root cause: string heuristic instead of parsing the actual
  `<digits>-<slug>` naming convention. Now parses and compares exactly.
- Judge run: every official example case now participates in a remote run
  (inputs newline-concatenated under `data_input`); previously only the first
  stored case was sent. `cases.json` is now built from the detail query's
  `exampleTestcases` (JSON-encoded list) with `sampleTestCase` as fallback,
  so fetched-but-unused example data is no longer dropped.
- Settings: removed dead config keys `theme` / `ui_language` (browser
  localStorage is the single source of truth for UI preferences; the backend
  copies had zero consumers). Legacy files carrying them load cleanly and the
  keys are dropped on next save. `request_interval` is now validated to
  [0.5, 60] seconds (422 otherwise) instead of silently disabling the rate
  limiter; secret masking reveals only the last 4 chars (no more 6-char
  prefix leak). Destructive "erase all data" now requires typing `DELETE`.
- AI sidebar: switching problems resets the conversation (the workbench is
  reused across routes, so the previous problem's chat leaked into the next
  problem's LLM context) and error bubbles are excluded from follow-up
  history; stale in-flight answers are discarded after a switch.

**UI**

- Error messages now follow the UI language: the api layer translates the
  server's stable `message_key` centrally instead of every view showing the
  backend-locale `message`. This also exposed and fixed the auth banner
  rendering the raw key `cookie_invalid` (missing catalog entry).
- Submit/run show a live judging indicator with elapsed time and a keep-page-
  open hint (a formal submission can take up to ~2 minutes). Note: client-side
  cancel is deliberately NOT provided - the site-side submission has already
  started and cannot be retracted, so an abort button would only fake safety.
- WA diff table dropped its always-empty input column (backend returns one
  merged input blob, so per-row inputs were rendered as meaningless dashes).
- Language dropdown marks not-yet-downloaded languages explicitly ("未获取")
  instead of a bare "·"; Ctrl+Enter runs and Ctrl+Shift+Enter submits;
  Analyze uses proper generating/attempts copy instead of borrowing the setup
  wizard's "saving…" string.

**Logic**

- Status classification collapsed to a single source (`cn.classify_status_text`)
  shared by judge results and site import - the duplicated api-layer table had
  already drifted (imports mislabeled Internal Error).
- `problem_dir_for` resolves its default workspace root through the effective
  config instead of an empty dict that silently ignored `workspace_root`.
- `Archive.recent()` takes the append lock (concurrent reads can no longer see
  half-written lines); judge endpoints read the problem cache once per request;
  `cli` binds and holds the listener socket before uvicorn starts, closing the
  find-port/release/rebind TOCTOU window; LLM failures are logged.

**Tests & tooling**

- Live-network regression suite added (`tests/test_integration_live.py`,
  opt-in via `ALGOCOACH_TEST_COOKIE` + `pytest -m integration`; excluded from
  default runs and CI by pyproject addopts) - the `integration` marker was
  previously declared but had zero tests.
- Full-chain mocked E2E (`tests/test_flow_api.py`) covering setup → sync →
  open → run → submit → analyze, plus regression tests for every fix above;
  central per-test reset of process singletons (`tests/conftest.py`) removes
  order-dependent leakage of the archive cache between cases.
- CI: Python matrix extended to 3.10/3.11/3.12 (3.10/3.11 exercise the
  no-tomllib fallback parser), ruff lint job added, `--passWithNoTests`
  removed from the vitest invocation, eslint introduced for the web app
  (`npm run lint`). Ruff also surfaced a latent NameError in test_httpclient.

**Docs**

- ARCHITECTURE corrected against reality: `GET /api/problem/{qid}` documented
  as lazy materialization (fetch-once-then-offline), not "pure read"; storage
  layout, settings contract, sync resume semantics and the socket-hold guard
  updated. PITFALLS backfilled (data_input serialization entry closed, new
  entries for sync-resume semantics, directory-name parsing, silent i18n
  missing keys, error-language policy).

### Fixed

- Security hardening: user-supplied `{qid}` path parameters and site-returned
  `titleSlug` values are now validated against an `[A-Za-z0-9_-]` whitelist at the
  API boundary and in the cn adapter (fail-closed), closing path-traversal vectors
  that could write outside the workspace (`PUT /api/problem/../solution`,
  backslash payloads on Windows, hostile sync rows).
- SPA static hosting: dist containment check replaced a flawed `startswith`
  prefix comparison with `Path.relative_to`, so sibling directories such as
  `dist-old/` can no longer be served through crafted paths.
- Local origin guard: the Host header is parsed with `urlparse` so bracketed
  IPv6 (`[::1]:8000`) validates correctly; forced refresh moved from the
  side-effectful `GET /api/problem/{qid}?refresh=1` to
  `POST /api/problem/{qid}/refresh` (GET is now strictly read-only).
- Logging was never wired up: `coach` now configures the algocoach logger on
  startup with an always-on rotating file (`~/.algocoach/coach.log`, 1 MB x 1
  backup) and `--debug` verbosity, making the redacted HTTP debug trail and the
  "share the debug log" support flow actually work.
- Cookie-rotation persistence races: rotated-cookie write-back is serialized
  behind a dedicated lock (a sync thread and an API thread could previously
  interleave load/save and lose unrelated config updates), and an in-memory
  cache skips the per-response disk round-trip while the cookie is unchanged.
- Problem sync no longer truncates after page one when leetcode.cn omits the
  list `total`: unknown totals now fall back to short-page detection instead of
  impersonating a complete single-page catalog.
- Web: navigating between two problems (`/problem/a` -> `/problem/b`) reuses the
  component without remounting; ProblemDetail now watches the qid param, flushes
  pending autosave under the old qid, resets state and reloads, discarding
  out-of-order responses.
- Web: sync-progress polling now has a failure budget (5 consecutive errors)
  instead of showing "syncing" forever when the endpoint keeps failing.
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
