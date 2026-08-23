"""FastAPI thin REST layer.

Responsibilities (implemented in later milestones):
- domain exceptions translated to structured error JSON
- SPA catch-all fallback to index.html; static hosting of web/dist
- Origin / Sec-Fetch-Site / Host validation middleware (whitelist includes the
  Vite dev origin http://localhost:5173); method-tiered: state-changing
  methods require a whitelisted Origin, GET alone may fall back to Host checks
- blocking long endpoints (judge polling, problem sync) are plain def so they
  run in the thread pool instead of stalling the event loop
"""

import fastapi

import lc

app = fastapi.FastAPI(title="AlgoCoach", version=lc.__version__)


@app.get("/api/status")
def get_status():
    return {
        "app": "algocoach",
        "version": lc.__version__,
        "site": "leetcode.cn",
        "configured": False,
    }
