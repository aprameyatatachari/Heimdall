"""Scheduled Gjallarhorn monitoring, triggered by Vercel Cron.

Vercel Cron issues a **GET** to a path on the deployment. Heimdall's scheduled
monitoring endpoint is a **POST** guarded by a shared secret, and it stays that
way: a GET that evaluates every portfolio and writes signals would be a mutating
GET, which any crawler, prefetcher or link preview could fire.

So this function is the adapter. It does three things and no more:

1. Refuses to run outside production. A preview deployment shares the code but
   must never run production monitoring — the guard is `VERCEL_ENV`, checked
   before anything else happens.
2. Verifies the caller. Vercel sends `Authorization: Bearer $CRON_SECRET` on
   scheduled invocations when that variable is set; the comparison is
   constant-time, and a missing secret refuses rather than running unprotected.
3. Calls the real endpoint over HTTP on its own deployment, so the request goes
   through the same guard, validation and error handling as any other. Only the
   standard library is used, which keeps the cold start of a function that runs
   once a day from carrying a dependency nobody else needs.

The work itself is bounded and idempotent on the server: one evaluation period
per UTC day, so a retry after a timeout resumes rather than double-evaluating,
and `batch_size` keeps a run inside the function's configured duration. See
docs/deployment.md for the schedule, and for how to disable it safely.
"""

from __future__ import annotations

import hmac
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

MONITORING_PATH = "/api/v1/internal/monitoring/run"
REQUEST_TIMEOUT_SECONDS = 55


def _deployment_origin() -> str:
    """This deployment's own origin.

    `VERCEL_PROJECT_PRODUCTION_URL` is the stable production domain;
    `VERCEL_URL` is the per-deployment one. Either reaches the same functions,
    and neither is a secret.
    """
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or os.environ.get("VERCEL_URL")
    if not host:
        return "http://127.0.0.1:8000"
    return host if host.startswith("http") else f"https://{host}"


def _authorized(header: str | None, secret: str) -> bool:
    """Whether the caller presented the scheduler secret."""
    if not header:
        return False
    token = header[7:] if header.lower().startswith("bearer ") else header
    return hmac.compare_digest(token, secret)


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel requires this name
    """Vercel Python function entrypoint."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's interface
        """Run one bounded batch of scheduled monitoring."""
        environment = os.environ.get("VERCEL_ENV", "development")
        if environment != "production":
            # Preview deployments read the same code and could be pointed at the
            # same database by a misconfigured variable. Refusing here means a
            # preview can never write signals on a production schedule.
            self._respond(403, {"status": "refused", "reason": "not the production environment"})
            return

        secret = os.environ.get("CRON_SECRET")
        if not secret:
            self._respond(503, {"status": "refused", "reason": "no scheduler secret configured"})
            return

        if not _authorized(self.headers.get("Authorization"), secret):
            self._respond(401, {"status": "refused", "reason": "not authorized"})
            return

        request = urllib.request.Request(
            f"{_deployment_origin()}{MONITORING_PATH}",
            # Prices first: a run that evaluated whatever was last stored would
            # re-examine the same close every day nobody opened the app.
            data=json.dumps({"refresh_prices": True}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Cron-Secret": secret,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = json.loads(response.read() or b"{}")
            self._respond(200, {"status": "ran", "result": body})
        except urllib.error.HTTPError as error:
            # The upstream response may carry a reason; the status is what the
            # scheduler needs, and nothing here logs portfolio detail.
            self._respond(502, {"status": "failed", "upstream_status": error.code})
        except Exception:
            self._respond(504, {"status": "failed", "reason": "monitoring did not complete"})

    def _respond(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        """Silence the default access log, which writes to stderr unstructured."""
        return
