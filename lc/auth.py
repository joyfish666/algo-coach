"""LeetCode.cn session management.

Responsibilities (implemented in later milestones):
- requests.Session construction with browser UA / Referer / csrfToken injection
- cookie invalidation detection across three observed shapes: 403 status,
  302 redirect to the login page, and 200 + errors payload (cn-site GraphQL
  sessions often expire this way; checking status codes alone misses it)
- csrfToken extraction
- in-process singleton lifecycle: after a successful cookie update the session
  must be rebuilt immediately, otherwise stale cookies cause an
  "expired right after update" loop until restart
"""

APP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
LEETCODE_CN_BASE = "https://leetcode.cn"
