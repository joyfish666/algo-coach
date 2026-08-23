"""SiteAdapter abstraction: minimal interface, one adapter per site.

Only the cn adapter is implemented for now; a leetcode.com adapter awaits
demand validation. All response parsing lives inside each adapter so the rest
of the app never touches raw payloads.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SiteAdapter(ABC):
    name = "site"

    @abstractmethod
    def validate_cookie(self) -> dict:
        """Lightweight credential check; returns profile info or raises AuthError."""

    @abstractmethod
    def fetch_problem_list_page(self, skip: int, limit: int) -> dict:
        """One paged slice of the problem list; returns {total, problems}."""

    @abstractmethod
    def fetch_question_detail(self, slug: str) -> dict:
        """Statement/tags/hints/templates/sample cases for a slug."""

    @abstractmethod
    def fetch_daily_question(self) -> dict:
        """Today's problem (00:00 UTC+8 boundary)."""
