"""Problem list synchronization and caching.

Responsibilities (implemented in later milestones):
- paged full problem-list fetch into problems.json (number <-> slug mapping,
  premium flag, difficulty, tags, category)
- atomic writes (temp file + rename); resumable sync within a process lifetime
- statement and template fetching with .bak backup of user-edited files on
  refresh; statement.md / cases.json are regenerable and overwritten directly
- canonical key is the slug (frontendQuestionId can be non-numeric such as
  "剑指 Offer 03"); slug/frontendQuestionId uniqueness validated at sync time,
  anomalies logged and skipped without aborting
- non-algorithm categories (e.g. SQL) kept but marked unsupported
"""
