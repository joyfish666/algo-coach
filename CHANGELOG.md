# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
