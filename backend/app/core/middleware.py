import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF defence in depth. Auth uses Bearer tokens (never cookies), so classic CSRF does not
    apply; we additionally reject state-changing browser requests from unknown origins."""

    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin not in get_settings().cors_origin_list:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding window. In-memory: fine for one web instance; swap for Redis when scaling."""

    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/health"):
            return await call_next(request)
        limit = get_settings().rate_limit_per_minute
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self.hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"}
            )
        window.append(now)
        return await call_next(request)
