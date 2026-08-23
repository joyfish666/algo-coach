# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
