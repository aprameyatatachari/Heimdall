"""Security response headers.

Applied to every response. The values suit an API that serves JSON and PDF
downloads; the frontend, served separately, sets its own policy for HTML.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# `frame-ancestors 'none'` and `X-Frame-Options: DENY` both refuse framing, which
# matters because a framed API response can be used in a clickjacking flow.
# `default-src 'none'` is correct for an API: it serves no scripts, styles, or
# images of its own.
CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

BASE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # This API needs none of these device capabilities.
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
    # Responses carry portfolio data, so no shared cache may retain them.
    "Cache-Control": "no-store",
}

# Only meaningful over HTTPS, so it is added only in deployed environments.
HSTS_HEADER = "Strict-Transport-Security"
HSTS_VALUE = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        for header, value in BASE_HEADERS.items():
            # A route that set its own value keeps it: a PDF download, for example,
            # sets `private, no-store` deliberately.
            response.headers.setdefault(header, value)

        if self._enable_hsts:
            response.headers.setdefault(HSTS_HEADER, HSTS_VALUE)

        return response
