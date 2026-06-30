"""CORS, rate-limiting, origin-check, request timing, and error-handling middleware."""

from __future__ import annotations

import collections
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

_NextHandler = Callable[[Request], Awaitable[Response]]

log = logging.getLogger("hard_workers.api.middleware")

# ── Rate limiter (in-memory sliding window) ──────────────────────────────────


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, collections.deque[float]] = collections.defaultdict(
            lambda: collections.deque(maxlen=max_requests)
        )

    def is_allowed(self, ip: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets[ip]
        while bucket and bucket[0] < now - self._window:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True


_RATE_LIMITER = RateLimiter()
_RATE_LIMIT_BYPASS_PATHS = {"/api/v1/ws", "/api/v1/docs", "/api/v1/redoc", "/"}


def setup_cors(app: FastAPI, origins: list[str] | None = None) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: _NextHandler) -> Response:
        path = request.url.path
        if path in _RATE_LIMIT_BYPASS_PATHS or path.startswith(("/api/v1/ws",)):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        if not _RATE_LIMITER.is_allowed(ip):
            log.warning("Rate limit exceeded for %s (%s)", ip, path)
            return Response(status_code=429, content='{"error":"Too many requests","code":"RATE_LIMITED"}')
        return await call_next(request)


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Verify Origin/Referer header for state-changing requests (defence in depth)."""

    ALLOWED_ORIGINS: set[str] = set()

    async def dispatch(self, request: Request, call_next: _NextHandler) -> Response:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        if not self.ALLOWED_ORIGINS:
            return await call_next(request)
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        if not origin and not referer:
            return await call_next(request)
        if origin in self.ALLOWED_ORIGINS:
            return await call_next(request)
        if any(ref.startswith(o) for o in self.ALLOWED_ORIGINS for ref in (referer,)):
            return await call_next(request)
        log.warning("Blocked request with unexpected Origin: %s", origin)
        return Response(status_code=403, content='{"error":"Forbidden","code":"ORIGIN_MISMATCH"}')


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: _NextHandler) -> Response:
        t0 = time.monotonic()
        response = await call_next(request)
        elapsed = (time.monotonic() - t0) * 1000
        response.headers["X-Request-Time-Ms"] = f"{elapsed:.1f}"
        log.debug("%s %s → %s (%.1fms)", request.method, request.url.path, response.status_code, elapsed)
        return response


def setup_middleware(app: FastAPI, cors_origins: list[str] | None = None) -> None:
    origins = cors_origins or ["http://localhost:5173"]
    setup_cors(app, origins)
    OriginCheckMiddleware.ALLOWED_ORIGINS = set(origins)
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestTimingMiddleware)
