# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
