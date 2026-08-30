"""FastAPI application: composition root of the REST layer.

Layer rules:
- domain exceptions are translated to structured error JSON (one envelope,
  see server.errors)
- blocking network endpoints are plain def so they run in the thread pool
- Origin / Host guard middleware: state-changing methods require a whitelisted
  local origin (including the Vite dev origin http://localhost:5173); GET may
  omit Origin but the Host header must be local (DNS-rebinding protection);
  forced refresh lives on POST /api/problem/{qid}/refresh so GET never force-
  refetches; note GET still lazily materializes a not-yet-open problem (fetch
  once, then serve from disk) - that is documented behavior, not an accident
- the built frontend is served when present (find_dist_dir), with an SPA
  fallback registered last on purpose

Endpoints live in server.routers, grouped by concern:
settings (app status / setup / config), problems (list, sync, workspace,
judge), groups (practice-plan trees, share codes), coach (AI ask / analyze),
archive (history, import, data wipe).
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import lc
from lc.exceptions import AlgoCoachError
from lc.logutil import logger
from server.errors import error_payload, status_for
from server.routers import archive, coach, groups, problems, settings

LOCAL_HOSTNAMES = ("127.0.0.1", "localhost", "::1")
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def find_dist_dir() -> Path | None:
    """Locate the built frontend (web/dist).

    Resolution chain: ALGOCOACH_DIST env override -> repository layout
    (editable installs / source checkout, searched upward from this file) ->
    packaged copy inside the installed server package. None means API-only
    mode; the dev flow serves the UI through Vite instead.
    """
    env = os.environ.get("ALGOCOACH_DIST")
    if env and (Path(env) / "index.html").is_file():
        return Path(env)

    here = Path(__file__).resolve().parent
    for base in [here.parent, *here.parents[:4]]:
        candidate = base / "web" / "dist" / "index.html"
        if candidate.is_file():
            return candidate.parent

    packaged = here / "webdist"
    if (packaged / "index.html").is_file():
        return packaged
    return None


DIST_DIR = find_dist_dir()

app = FastAPI(title="AlgoCoach", version=lc.__version__)


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    host_header = request.headers.get("host") or ""
    # urlparse("//[::1]:8000").hostname -> "::1"; handles bracketed IPv6
    host = (urlparse(f"//{host_header}").hostname or "").lower()
    if host not in LOCAL_HOSTNAMES:
        return JSONResponse(
            status_code=403,
            content={"error": error_payload("ForbiddenHost", "host not allowed",
                                            message_key="network_error")},
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if not origin:
            return JSONResponse(
                status_code=403,
                content={"error": error_payload(
                    "MissingOrigin", "origin required for state-changing requests",
                    message_key="network_error")},
            )
        parsed = urlparse(origin)
        allowed = (
            origin in DEV_ORIGINS
            or (parsed.hostname or "").lower() in LOCAL_HOSTNAMES
        )
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"error": error_payload("ForbiddenOrigin", "origin not allowed",
                                                message_key="network_error")},
            )
    return await call_next(request)


@app.exception_handler(AlgoCoachError)
async def domain_error_handler(request: Request, exc: AlgoCoachError):
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(int(retry_after))} if retry_after else None
    return JSONResponse(
        status_code=status_for(exc),
        content={
            "error": error_payload(
                type(exc).__name__,
                str(exc),
                message_key=exc.message_key,
                detail=exc.detail,
            )
        },
        headers=headers,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """Reshape every HTTPException into the unified error envelope.

    detail may be a message_key-carrying dict (http_domain_error) or a plain
    string (validation messages); both land on the same envelope so the
    frontend normalizer has one primary shape.
    """
    detail = exc.detail
    if isinstance(detail, dict):
        payload = error_payload(
            detail.get("kind", "HTTPException"),
            str(detail.get("message", "")),
            message_key=detail.get("message_key"),
        )
    else:
        payload = error_payload(
            "HTTPException", str(detail) if detail is not None else "error"
        )
    return JSONResponse(
        status_code=exc.status_code, content={"error": payload}, headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    """Flatten pydantic's list-of-errors body into the unified envelope."""
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = first.get("msg", "invalid request")
    payload = error_payload("ValidationError", f"{loc}: {message}" if loc else message)
    return JSONResponse(status_code=422, content={"error": payload})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled error on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": error_payload(
                type(exc).__name__, f"{type(exc).__name__}: {exc}",
                message_key="network_error",
            )
        },
    )


app.include_router(settings.router)
app.include_router(problems.router)
app.include_router(groups.router)
app.include_router(coach.router)
app.include_router(archive.router)


# ---------------------------------------------------------------------------
# built-frontend hosting + SPA fallback (registered last on purpose)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        # generic not-found: this fallback only sees paths no route matched,
        # which is a client typo, not a missing problem
        raise HTTPException(status_code=404, detail="not found")

    if DIST_DIR is not None:
        dist_root = DIST_DIR.resolve()
        served = None
        if full_path:
            candidate = (dist_root / full_path.lstrip("/")).resolve()
            try:
                candidate.relative_to(dist_root)
                inside = True
            except ValueError:
                inside = False
            if inside and candidate.is_file():
                served = candidate
        if served is not None:
            immutable = "/assets/" in full_path
            return FileResponse(
                served,
                headers={
                    "Cache-Control": (
                        "public, max-age=31536000, immutable"
                        if immutable
                        else "no-cache"
                    )
                },
            )
        last_segment = full_path.rstrip("/").rsplit("/", 1)[-1]
        if "." in last_segment:
            # asset-shaped misses (a hashed chunk from before a redeploy)
            # must 404: rewriting them to index.html answered a JS request
            # with HTML, and the browser reported an opaque MIME error while
            # every navigation from the stale tab silently died
            raise HTTPException(status_code=404, detail="not found")
        index = dist_root / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    if not full_path:
        return JSONResponse(
            {
                "app": f"AlgoCoach v{lc.__version__}",
                "hint": "frontend not built; run `cd web && npm run build` or use Vite dev mode",
                "endpoints": [
                    "/api/status",
                    "/api/settings",
                    "/api/problems",
                    "/api/problems/sync/progress",
                    "/api/daily",
                ],
            }
        )
    raise HTTPException(status_code=404, detail="not found")
