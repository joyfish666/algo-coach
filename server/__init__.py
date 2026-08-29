"""AlgoCoach FastAPI server package.

Layout:
- app.py      composition root: middleware, error handlers, dist hosting
- errors.py   the unified error envelope and HTTP status mapping
- state.py    process singletons, config-derived factories (test seam)
- routers/    endpoint groups: settings, problems, coach, archive

Domain logic lives in lc.*; this package is the transport layer.
"""
