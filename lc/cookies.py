"""requests cookie-jar helpers.

requests' ``jar.get(name)`` raises CookieConflictError as soon as one cookie
name exists on two domain/path variants - and leetcode.cn does exactly that
with csrftoken (apex + www), which killed the rotation hook on every
authenticated response and made csrf header reads unusable. The app only
ever reads cookies by name, so lookups tolerate duplicates (most recent
match wins) and jars are collapsed to one cookie per managed name.
"""

from __future__ import annotations


def jar_value(jar, name: str) -> str:
    """Conflict-tolerant lookup: the most recent match wins, "" if absent."""
    matches = [cookie.value for cookie in jar if cookie.name == name]
    return matches[-1] if matches else ""


def dedupe_jar(jar, names) -> int:
    """Collapse same-name cookies for the given names to their latest value.

    Returns how many cookies were removed. Iterates first and clears after,
    so the jar is never mutated while being walked.
    """
    targets = set(names)
    matches_by_name: dict[str, list] = {}
    for cookie in jar:
        if cookie.name in targets:
            matches_by_name.setdefault(cookie.name, []).append(cookie)
    removed = 0
    for matches in matches_by_name.values():
        for cookie in matches[:-1]:
            jar.clear(cookie.domain, cookie.path, cookie.name)
            removed += 1
    return removed
