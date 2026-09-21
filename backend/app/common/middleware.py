"""HTTP middleware: request identity, access logging, and body-size limits."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.common.errors import build_error_response
from app.common.logging import (
    REQUEST_ID_HEADER,
    bind_request_id,
    clear_request_context,
    get_logger,
)

logger = get_logger(__name__)

# Paths that should not produce an access log line on every poll.
_QUIET_PATHS = frozenset({"/health", "/ready"})

# Requests slower than this are logged at warning level. Analytics and report
# generation are the expensive paths, and a serverless function has a hard
# duration limit, so a request approaching this is worth seeing in the logs.
SLOW_REQUEST_MS = 3000.0

# Reported so a client can see server-side time without guessing from the wire.
RESPONSE_TIME_HEADER = "X-Response-Time-Ms"


def _new_request_id() -> str:
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request ID, bind it to the log context, and log the outcome.

    An inbound `X-Request-ID` is accepted when it looks safe, so a request can be
    traced across the frontend, a proxy, and the API.
    """

    def __init__(self, app: ASGIApp, *, quiet_paths: frozenset[str] = _QUIET_PATHS) -> None:
        super().__init__(app)
        self._quiet_paths = quiet_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = self._resolve_request_id(request)
        request.state.request_id = request_id

        clear_request_context()
        bind_request_id(request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
            )
            raise
        finally:
            clear_request_context()

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[RESPONSE_TIME_HEADER] = f"{duration_ms:.1f}"

        if duration_ms >= SLOW_REQUEST_MS:
            logger.warning(
                "slow_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
                threshold_ms=SLOW_REQUEST_MS,
            )
        elif request.url.path not in self._quiet_paths or response.status_code >= 400:
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
            )
        return response

    @staticmethod
    def _resolve_request_id(request: Request) -> str:
        """Use the inbound request ID when it is short and alphanumeric."""
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        candidate = inbound.strip()
        if 8 <= len(candidate) <= 64 and all(c.isalnum() or c in "-_" for c in candidate):
            return candidate
        return _new_request_id()


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body exceeds the configured limit.

    This is a cheap first line of defence. Endpoints that stream uploads perform
    their own byte accounting, because `Content-Length` can be absent or wrong.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > self._max_body_bytes:
                return build_error_response(
                    status_code=413,
                    code="payload_too_large",
                    message=(f"Request body exceeds the maximum of {self._max_body_bytes} bytes."),
                    request_id=getattr(request.state, "request_id", None),
                )
        return await call_next(request)
