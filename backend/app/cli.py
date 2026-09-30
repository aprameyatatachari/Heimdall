"""Operational commands.

Currently one: seeding a demo portfolio so a fresh deployment has something to
look at. It is deliberately not part of the application — nothing in `app.main`
imports this module, and a running server has no route that reaches it.

The seed drives the **public API** through an in-process ASGI transport rather
than writing rows directly. That means it goes through the same validation,
ownership checks and transaction handling as any request, so it cannot create a
shape of data the application itself could not: a seeded portfolio is a real
portfolio, not a fixture that happens to resemble one.

Three safety properties, in order of how much they matter:

* It refuses to touch a production database unless the operator sets
  `HEIMDALL_ALLOW_DEMO_SEED=true` as well as passing the command. Two deliberate
  acts, because demo data in a production database is very hard to unpick.
* It never invents a password. `DEMO_PASSWORD` must be supplied, so no
  credential is generated, printed, logged or committed by this tool.
* It is idempotent. Re-running it reuses the existing account and portfolio
  rather than stacking duplicates, so it is safe in a deploy pipeline.

Usage:

    DEMO_PASSWORD='...' uv run python -m app.cli seed-demo --email demo@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date

from httpx import ASGITransport, AsyncClient

from app.config import Environment, get_settings
from app.main import create_app

# A small, diversified set drawn from the committed fixtures, so seeding never
# depends on a third party being reachable.
DEMO_HOLDINGS: tuple[tuple[str, str, str], ...] = (
    ("AAPL", "40", "120.50"),
    ("MSFT", "25", "210.00"),
    ("SPY", "30", "300.00"),
    ("TLT", "35", "110.00"),
    ("XOM", "60", "70.00"),
)

DEMO_PORTFOLIO_NAME = "Demo portfolio"
DEMO_WINDOW_START = date(2022, 1, 3)
DEMO_WINDOW_END = date(2023, 12, 29)
MINIMUM_PASSWORD_LENGTH = 12


class SeedError(RuntimeError):
    """The seed could not be completed. The message is safe to print."""


async def seed_demo(*, email: str, password: str) -> dict[str, str]:
    """Create (or reuse) the demo account, portfolio, prices and first analysis."""
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://seed") as client:
        token = await _sign_in_or_register(client, email=email, password=password)
        headers = {"Authorization": f"Bearer {token}"}

        portfolio_id = await _existing_portfolio(client, headers)
        created = portfolio_id is None
        if portfolio_id is None:
            response = await client.post(
                "/api/v1/portfolios",
                json={
                    "name": DEMO_PORTFOLIO_NAME,
                    "description": (
                        "Seeded demonstration data. Prices come from committed fixtures."
                    ),
                    "base_currency": "USD",
                    "benchmark_symbol": "SPY",
                },
                headers=headers,
            )
            if response.status_code != 201:
                raise SeedError(f"Could not create the demo portfolio ({response.status_code}).")
            portfolio_id = str(response.json()["id"])

            for symbol, quantity, average_cost in DEMO_HOLDINGS:
                added = await client.post(
                    f"/api/v1/portfolios/{portfolio_id}/positions",
                    json={"symbol": symbol, "quantity": quantity, "average_cost": average_cost},
                    headers=headers,
                )
                if added.status_code != 201:
                    raise SeedError(f"Could not add {symbol} ({added.status_code}).")

        # Idempotent on the server: already-stored bars are not refetched.
        await client.post(
            f"/api/v1/portfolios/{portfolio_id}/market-data/refresh",
            params={"start": DEMO_WINDOW_START.isoformat(), "end": DEMO_WINDOW_END.isoformat()},
            headers=headers,
            timeout=120.0,
        )
        await client.post(
            f"/api/v1/portfolios/{portfolio_id}/analysis-runs",
            json={"start": DEMO_WINDOW_START.isoformat(), "end": DEMO_WINDOW_END.isoformat()},
            headers=headers,
            timeout=120.0,
        )
        # Rules are provisioned explicitly rather than at portfolio creation, so
        # the demo shows the Gjallarhorn screen with something in it.
        await client.post(
            f"/api/v1/portfolios/{portfolio_id}/alert-rules/defaults",
            headers=headers,
        )
        await client.post(
            f"/api/v1/portfolios/{portfolio_id}/monitoring-runs",
            headers=headers,
            timeout=120.0,
        )

    return {
        "portfolio_id": portfolio_id,
        "portfolio": DEMO_PORTFOLIO_NAME,
        "created": "yes" if created else "no, it already existed",
    }


async def _sign_in_or_register(client: AsyncClient, *, email: str, password: str) -> str:
    """Return an access token, registering the account only if it does not exist."""
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if login.status_code == 200:
        return str(login.json()["access_token"])

    registration = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    if registration.status_code == 201:
        return str(registration.json()["access_token"])

    # Neither worked: most often the account exists with a different password.
    # The reason is not echoed, because it would distinguish "wrong password"
    # from "no such account" in a log.
    raise SeedError(
        "Could not sign in or register the demo account. "
        "Check DEMO_PASSWORD against the existing account."
    )


async def _existing_portfolio(client: AsyncClient, headers: dict[str, str]) -> str | None:
    """The demo portfolio's id, when this account already has one."""
    response = await client.get("/api/v1/portfolios", params={"limit": 50}, headers=headers)
    if response.status_code != 200:
        return None
    for item in response.json().get("items", []):
        if item.get("name") == DEMO_PORTFOLIO_NAME:
            return str(item["id"])
    return None


def _check_allowed() -> None:
    """Refuse to seed a production database without a second, explicit act."""
    settings = get_settings()
    if settings.environment is not Environment.PRODUCTION:
        return
    if os.environ.get("HEIMDALL_ALLOW_DEMO_SEED", "").lower() != "true":
        raise SeedError(
            "Refusing to seed demo data into a production database. "
            "Set HEIMDALL_ALLOW_DEMO_SEED=true if that is genuinely what you want."
        )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="app.cli", description="Heimdall operational commands.")
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser("seed-demo", help="Create a demonstration portfolio.")
    seed.add_argument("--email", required=True, help="Account to create or reuse.")

    arguments = parser.parse_args(argv)

    if arguments.command == "seed-demo":
        password = os.environ.get("DEMO_PASSWORD", "")
        if len(password) < MINIMUM_PASSWORD_LENGTH:
            print(
                f"DEMO_PASSWORD must be set and at least {MINIMUM_PASSWORD_LENGTH} characters. "
                "This tool never generates a credential for you.",
                file=sys.stderr,
            )
            return 2
        try:
            _check_allowed()
            result = asyncio.run(seed_demo(email=arguments.email, password=password))
        except SeedError as error:
            print(str(error), file=sys.stderr)
            return 1
        # Deliberately no credential in the output.
        print(f"Demo portfolio ready: {result['portfolio']} ({result['portfolio_id']})")
        print(f"Created this run: {result['created']}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
