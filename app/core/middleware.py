"""Pure-ASGI HTTP middleware: request context + access log, security headers,
request body limits and rate limiting.

Pure ASGI (rather than BaseHTTPMiddleware) keeps streaming uploads streaming and
lets the body limit count bytes as they arrive, including chunked requests that
send no Content-Length.
"""

import logging
import math
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import RequestTooLargeError
from app.utils.logging import request_id_var

access_logger = logging.getLogger("app.access")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def error_response(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status_code, headers=headers
    )


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    return client[0] if client else "unknown"


class RequestContextMiddleware:
    """Assigns a request ID (or accepts a well-formed incoming one), echoes it in the
    response, and writes one structured access-log line per request.

    The query string is deliberately not logged (it can carry identifiers or tokens).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
        request_id = (
            incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        status = {"code": 500}
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            access_logger.info(
                "%s %s %s %.1fms",
                scope["method"],
                scope["path"],
                status["code"],
                duration_ms,
                extra={
                    "http_method": scope["method"],
                    "path": scope["path"],
                    "status": status["code"],
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(scope),
                },
            )
            request_id_var.reset(token)


SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, api_prefix: str) -> None:
        self.app = app
        self.api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith(self.api_prefix)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if is_api:  # API responses can contain user data; never cache them
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_wrapper)


class BodySizeLimitMiddleware:
    """Rejects oversized bodies with 413 before the application buffers them.

    multipart/form-data (file uploads) may be up to MAX_UPLOAD_SIZE_MB plus framing
    overhead; everything else is limited to MAX_REQUEST_BODY_MB. The upload service
    additionally enforces the exact per-file limit while writing to disk.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int, max_upload_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.max_multipart_bytes = max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        is_multipart = headers.get("content-type", "").startswith("multipart/form-data")
        limit = self.max_multipart_bytes if is_multipart else self.max_body_bytes

        declared = headers.get("content-length")
        if declared is not None:
            try:
                too_large = int(declared) > limit
            except ValueError:
                response = error_response(400, "bad_request", "Invalid Content-Length header.")
                await response(scope, receive, send)
                return
            if too_large:
                response = error_response(
                    413, "request_too_large", f"Request body exceeds {limit} bytes."
                )
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:  # chunked/understated bodies
                    raise RequestTooLargeError(f"Request body exceeds {limit} bytes.")
            return message

        await self.app(scope, limited_receive, send)


class TokenBucketLimiter:
    """In-memory token buckets (per process). Thread-safe; prunes idle keys."""

    def __init__(
        self, *, max_keys: int = 10_000, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_keys = max_keys
        self._clock = clock
        self._buckets: dict[Any, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: Any, per_minute: int) -> tuple[bool, int]:
        """Take one token. Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        refill_per_second = per_minute / 60
        with self._lock:
            tokens, last = self._buckets.get(key, (float(per_minute), now))
            tokens = min(float(per_minute), tokens + (now - last) * refill_per_second)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                allowed, retry_after = True, 0
            else:
                self._buckets[key] = (tokens, now)
                allowed = False
                retry_after = max(1, math.ceil((1 - tokens) / refill_per_second))
            if len(self._buckets) > self.max_keys:
                self._prune(now)
        return allowed, retry_after

    def _prune(self, now: float) -> None:
        stale = [k for k, (_, last) in self._buckets.items() if now - last > 120]
        for key in stale or list(self._buckets)[: len(self._buckets) // 2]:
            self._buckets.pop(key, None)


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    per_minute: int


class RateLimitMiddleware:
    """Per-client rate limits with separate budgets for expensive endpoints.

    Clients are identified by their socket address. Behind a reverse proxy run
    uvicorn with --proxy-headers and --forwarded-allow-ips set to the proxy's
    address, otherwise all clients share the proxy's budget. Limits are per
    process: with N workers the effective limit is up to N times higher. Use a
    shared store (e.g. Redis) or the gateway's limiter for strict global limits.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        api_prefix: str,
        default_per_minute: int,
        ai_per_minute: int,
        training_per_minute: int,
        limiter: TokenBucketLimiter | None = None,
    ) -> None:
        self.app = app
        self.limiter = limiter or TokenBucketLimiter()
        self.default = RateLimitRule("default", default_per_minute)
        self.ai = RateLimitRule("ai", ai_per_minute)
        self.training = RateLimitRule("training", training_per_minute)
        self.exempt = {"/health", f"{api_prefix}/health", "/docs", "/redoc", "/openapi.json"}
        self.ai_prefixes = tuple(f"{api_prefix}{p}" for p in ("/llm", "/nlp", "/embeddings"))
        self.training_routes = {
            ("POST", f"{api_prefix}/models/train"),
            ("POST", f"{api_prefix}/datasets"),
            ("POST", f"{api_prefix}/datasets/validate"),
        }

    def rule_for(self, method: str, path: str) -> RateLimitRule | None:
        if method == "OPTIONS" or path in self.exempt:
            return None
        if path.startswith(self.ai_prefixes):
            return self.ai
        if (method, path.rstrip("/")) in self.training_routes:
            return self.training
        return self.default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rule = self.rule_for(scope["method"], scope["path"])
        if rule is not None:
            allowed, retry_after = self.limiter.acquire(
                (_client_ip(scope), rule.name), rule.per_minute
            )
            if not allowed:
                response = error_response(
                    429,
                    "rate_limited",
                    f"Too many requests ({rule.name} limit: {rule.per_minute}/min). Retry later.",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(rule.per_minute),
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
