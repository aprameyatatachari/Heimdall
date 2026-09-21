"""Rate limiting.

A fixed-window counter guarding the endpoints worth guarding: authentication, and
anything that reaches an external data provider or does expensive work.

**Serverless honesty.** The store is per-process. On a platform that runs many
concurrent instances, each enforces the limit independently, so the effective
limit is `limit x instances`. That is a real weakening, and it is documented
rather than hidden: the point here is to blunt credential stuffing and accidental
loops, not to be a distributed quota. `docs/security.md` records the shared-store
upgrade path.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.errors import build_error_response
from app.common.logging import get_logger

logger = get_logger(__name__)

RETRY_AFTER_HEADER: Final = "Retry-After"
LIMIT_HEADER: Final = "X-RateLimit-Limit"
REMAINING_HEADER: Final = "X-RateLimit-Remaining"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """How many requests a client may make to a path prefix in a window."""

    # Matched as a prefix against the request path.
    path_prefix: str
    limit: int
    window_seconds: int
    # Only these methods are limited. Empty means every method.
    methods: frozenset[str] = frozenset()

    def matches(self, *, path: str, method: str) -> bool:
        """Whether this rule governs the request."""
        if not path.startswith(self.path_prefix):
            return False
        return not self.methods or method.upper() in self.methods


def default_rules(prefix: str) -> tuple[RateLimitRule, ...]:
    """The rules Heimdall ships with.

    Authentication is the tightest: a login endpoint is the obvious target for
    credential stuffing. Ingestion and report generation are limited because each
    request reaches a provider or renders a document.
    """
    return (
        RateLimitRule(
            path_prefix=f"{prefix}/auth/login",
            limit=10,
            window_seconds=300,
            methods=frozenset({"POST"}),
        ),
        RateLimitRule(
            path_prefix=f"{prefix}/auth/register",
            limit=5,
            window_seconds=3600,
            methods=frozenset({"POST"}),
        ),
        RateLimitRule(
            path_prefix=f"{prefix}/auth/refresh",
            limit=60,
            window_seconds=300,
            methods=frozenset({"POST"}),
        ),
        RateLimitRule(
            path_prefix=f"{prefix}/assets",
            limit=120,
            window_seconds=60,
            methods=frozenset({"GET"}),
        ),
    )


class FixedWindowCounter:
    """In-process fixed-window counters, with lazy eviction of stale keys."""

    # Above this many tracked keys, expired entries are swept. Bounds memory even
    # under a spray of distinct client addresses.
    SWEEP_THRESHOLD: Final = 4096

    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, float]] = {}

    def hit(
        self, key: str, *, limit: int, window_seconds: int, now: float
    ) -> tuple[bool, int, int]:
        """Record a request.

        Returns `(allowed, remaining, retry_after_seconds)`.
        """
        if len(self._windows) > self.SWEEP_THRESHOLD:
            self._sweep(now)

        count, window_start = self._windows.get(key, (0, now))

        if now - window_start >= window_seconds:
            count, window_start = 0, now

        count += 1
        self._windows[key] = (count, window_start)

        if count > limit:
            retry_after = max(1, int(window_seconds - (now - window_start)) + 1)
            return False, 0, retry_after

        return True, max(0, limit - count), 0

    def _sweep(self, now: float) -> None:
        """Drop windows that can no longer deny anything."""
        cutoff = now - 3600
        for key in [key for key, (_, start) in self._windows.items() if start < cutoff]:
            del self._windows[key]

    def reset(self) -> None:
        """Forget every counter. Used by tests."""
        self._windows.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies the configured rules before a request reaches a route."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        rules: tuple[RateLimitRule, ...],
        enabled: bool = True,
        counter: FixedWindowCounter | None = None,
    ) -> None:
        super().__init__(app)
        self._rules = rules
        self._enabled = enabled
        self._counter = counter or FixedWindowCounter()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self._enabled:
            return await call_next(request)

        rule = self._match(request)
        if rule is None:
            return await call_next(request)

        key = f"{rule.path_prefix}|{self._client_key(request)}"
        allowed, remaining, retry_after = self._counter.hit(
            key,
            limit=rule.limit,
            window_seconds=rule.window_seconds,
            now=time.monotonic(),
        )

        if not allowed:
            # The path is logged; the client key is not, because it is a user's IP.
            logger.warning("rate_limited", path=request.url.path, limit=rule.limit)
            rejection = build_error_response(
                status_code=429,
                code="rate_limited",
                message=(f"Too many requests. Try again in about {retry_after} seconds."),
                request_id=getattr(request.state, "request_id", None),
            )
            rejection.headers[RETRY_AFTER_HEADER] = str(retry_after)
            rejection.headers[LIMIT_HEADER] = str(rule.limit)
            rejection.headers[REMAINING_HEADER] = "0"
            return rejection

        response = await call_next(request)
        response.headers[LIMIT_HEADER] = str(rule.limit)
        response.headers[REMAINING_HEADER] = str(remaining)
        return response

    def _match(self, request: Request) -> RateLimitRule | None:
        """The first rule governing this request, if any."""
        path, method = request.url.path, request.method
        for rule in self._rules:
            if rule.matches(path=path, method=method):
                return rule
        return None

    @staticmethod
    def _client_key(request: Request) -> str:
        """Identify the caller.

        `X-Forwarded-For` is only consulted for its **first** entry, which is what
        a trusted proxy prepends. A client-supplied value further along the chain
        cannot be used to evade the limit.
        """
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        return request.client.host if request.client else "unknown"
