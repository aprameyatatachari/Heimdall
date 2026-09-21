"""Unit tests for the PDF renderer and the hardening middleware.

The renderer is pure, so these run without a database.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.common.disclaimer import DISCLAIMER, EARLY_WARNING_DISCLAIMER
from app.common.rate_limit import (
    FixedWindowCounter,
    RateLimitMiddleware,
    RateLimitRule,
    default_rules,
)
from app.common.security_headers import BASE_HEADERS, HSTS_HEADER
from app.config import API_V1_PREFIX
from app.reports.renderer import (
    MetricRow,
    ReportData,
    TableBlock,
    format_money,
    format_percent,
    format_ratio,
    render_report,
)

GENERATED = datetime(2026, 9, 20, 12, 30, tzinfo=UTC)


def report_data(**overrides) -> ReportData:
    """A fully populated report, so every section is exercised."""
    data = ReportData(
        portfolio_name="Retirement",
        base_currency="USD",
        generated_at=GENERATED,
        data_as_of=date(2026, 9, 18),
        analysis_period="2025-09-18 to 2026-09-18",
        summary=[
            MetricRow("Portfolio market value", "125,430.22 USD", "USD"),
            MetricRow("Holdings", "4", "count"),
        ],
        performance=[
            MetricRow("Total return", "+12.40%", "percent", note="not annualized"),
            MetricRow("Annualized return", "+11.90%", "percent", note="annualized"),
        ],
        risk=[
            MetricRow("Volatility (annualized)", "18.20%", "percent", note="annualized"),
            MetricRow(
                "Value at Risk (historical)",
                "2,380.11 USD",
                "USD",
                note="95% confidence; not a maximum possible loss",
            ),
            MetricRow("Sharpe ratio (annualized)", "0.74", "ratio"),
        ],
        holdings=TableBlock(
            title="Positions",
            columns=[
                "Symbol",
                "Quantity",
                "Average cost",
                "Market value",
                "Weight",
                "Profit / loss",
            ],
            rows=[
                ["AAPL", "10", "185.20 USD", "2,010.00 USD", "45.00%", "+158.00 USD"],
                ["MSFT", "5", "402.10 USD", "1,900.00 USD", "55.00%", "-110.50 USD"],
            ],
            signed_column=5,
        ),
        allocation=TableBlock(
            title="Allocation by sector",
            columns=["Sector", "Weight"],
            rows=[["Technology", "100.00%"]],
        ),
        risk_contribution=TableBlock(
            title="Contribution to portfolio volatility",
            columns=["Symbol", "Weight", "Marginal", "Component", "Share of risk"],
            rows=[["AAPL", "45.00%", "0.21", "0.09", "48.00%"]],
        ),
        stress_tests=[
            TableBlock(
                title="COVID-19 crash — 10,000.00 USD to 7,000.00 USD, -3,000.00 USD (-30.00%)",
                columns=["Holding", "Starting value", "Applied return", "Impact", "Share of loss"],
                rows=[["AAPL", "10,000.00 USD", "-30.00%", "-3,000.00 USD", "100.00%"]],
                signed_column=3,
            )
        ],
        signals=TableBlock(
            title="Signals",
            columns=["Severity", "Condition", "Observed vs threshold", "Status", "Data as of"],
            rows=[
                [
                    "high",
                    "High position concentration",
                    "0.3420 vs 0.3000 (percent_of_portfolio_value)",
                    "active",
                    "2026-09-18",
                ]
            ],
        ),
        assumptions=["Portfolio returns use today's weights applied to historical asset returns."],
        limitations=["A stress test is an estimate of sensitivity, not a forecast."],
        data_sources=["Daily price history from the configured market-data provider."],
        unavailable=["information_ratio: Tracking error is zero, so it is undefined."],
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


# --- Rendering ----------------------------------------------------------------


def test_a_report_renders_to_a_pdf():
    content = render_report(report_data())

    assert content.startswith(b"%PDF-")
    assert content.rstrip().endswith(b"%%EOF")
    assert len(content) > 3000


def test_the_pdf_carries_the_document_title():
    content = render_report(report_data())

    assert b"Heimdall Risk Report" in content


def test_a_report_with_no_optional_sections_still_renders():
    minimal = ReportData(
        portfolio_name="Empty",
        base_currency="USD",
        generated_at=GENERATED,
        data_as_of=None,
        analysis_period="no analysis available",
    )

    content = render_report(minimal)

    assert content.startswith(b"%PDF-")


def test_a_report_renders_empty_tables_as_a_note():
    data = report_data(
        holdings=TableBlock(
            title="Positions",
            columns=["Symbol"],
            rows=[],
            empty_note="This portfolio has no holdings.",
        )
    )

    content = render_report(data)

    assert content.startswith(b"%PDF-")


def test_rendering_is_deterministic_for_the_same_input():
    """Two renders of identical data differ only in the PDF's internal id."""
    first = render_report(report_data())
    second = render_report(report_data())

    assert len(first) == len(second)


def test_a_long_portfolio_name_does_not_break_rendering():
    content = render_report(report_data(portfolio_name="A" * 300))

    assert content.startswith(b"%PDF-")


# --- Formatting ---------------------------------------------------------------


def test_money_is_formatted_with_its_currency():
    assert format_money(Decimal("1234.5"), "USD") == "1,234.50 USD"


def test_a_negative_amount_always_carries_a_minus_sign():
    """The sign must survive black-and-white printing and colour blindness."""
    assert format_money(Decimal("-1234.5"), "USD").startswith("-")


def test_a_positive_amount_can_be_explicitly_signed():
    assert format_money(Decimal("10"), "USD", signed=True).startswith("+")


def test_an_unavailable_value_says_so_rather_than_showing_zero():
    assert format_money(None, "USD") == "unavailable"
    assert format_percent(None) == "unavailable"
    assert format_ratio(None) == "unavailable"


def test_percentages_are_scaled_from_fractions():
    assert format_percent(Decimal("0.1234")) == "12.34%"


def test_a_negative_percentage_keeps_its_sign():
    assert format_percent(Decimal("-0.3")) == "-30.00%"


def test_a_signed_positive_percentage_gets_a_plus():
    assert format_percent(Decimal("0.05"), signed=True) == "+5.00%"


def test_a_zero_percentage_is_not_signed():
    assert format_percent(Decimal("0"), signed=True) == "0.00%"


def test_ratios_use_two_decimal_places():
    assert format_ratio(1.23456) == "1.23"


# --- Disclaimers --------------------------------------------------------------


def test_the_general_disclaimer_is_about_education_not_advice():
    assert "educational" in DISCLAIMER
    assert "do not constitute financial advice" in DISCLAIMER


def test_the_early_warning_disclaimer_denies_prediction():
    assert "not predictions" in EARLY_WARNING_DISCLAIMER
    assert "recommendations to buy, sell, or hold" in EARLY_WARNING_DISCLAIMER


# --- Rate limiting ------------------------------------------------------------


def test_a_counter_allows_requests_up_to_the_limit():
    counter = FixedWindowCounter()

    results = [counter.hit("key", limit=3, window_seconds=60, now=100.0)[0] for _ in range(3)]

    assert results == [True, True, True]


def test_a_counter_denies_the_request_after_the_limit():
    counter = FixedWindowCounter()
    for _ in range(3):
        counter.hit("key", limit=3, window_seconds=60, now=100.0)

    allowed, remaining, retry_after = counter.hit("key", limit=3, window_seconds=60, now=100.0)

    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_a_counter_reports_the_remaining_allowance():
    counter = FixedWindowCounter()

    _, remaining, _ = counter.hit("key", limit=5, window_seconds=60, now=100.0)

    assert remaining == 4


def test_a_new_window_resets_the_counter():
    counter = FixedWindowCounter()
    for _ in range(4):
        counter.hit("key", limit=3, window_seconds=60, now=100.0)

    allowed, _, _ = counter.hit("key", limit=3, window_seconds=60, now=200.0)

    assert allowed is True


def test_counters_are_independent_per_key():
    counter = FixedWindowCounter()
    for _ in range(3):
        counter.hit("first", limit=3, window_seconds=60, now=100.0)

    allowed, _, _ = counter.hit("second", limit=3, window_seconds=60, now=100.0)

    assert allowed is True


def test_the_default_rules_cover_authentication():
    prefixes = {rule.path_prefix for rule in default_rules(API_V1_PREFIX)}

    assert f"{API_V1_PREFIX}/auth/login" in prefixes
    assert f"{API_V1_PREFIX}/auth/register" in prefixes


def test_login_is_limited_more_tightly_than_asset_search():
    rules = {rule.path_prefix: rule for rule in default_rules(API_V1_PREFIX)}

    assert rules[f"{API_V1_PREFIX}/auth/login"].limit < rules[f"{API_V1_PREFIX}/assets"].limit


def test_a_rule_only_matches_its_configured_methods():
    rule = RateLimitRule(
        path_prefix="/api/v1/auth/login",
        limit=1,
        window_seconds=60,
        methods=frozenset({"POST"}),
    )

    assert rule.matches(path="/api/v1/auth/login", method="POST") is True
    assert rule.matches(path="/api/v1/auth/login", method="GET") is False
    assert rule.matches(path="/api/v1/portfolios", method="POST") is False


async def test_the_middleware_returns_429_with_the_standard_envelope():
    app = FastAPI()

    @app.get("/limited")
    async def _limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(RateLimitRule(path_prefix="/limited", limit=2, window_seconds=60),),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/limited")
        second = await client.get("/limited")
        third = await client.get("/limited")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert third.headers["Retry-After"]
    assert third.headers["X-RateLimit-Remaining"] == "0"


async def test_the_middleware_reports_the_remaining_allowance():
    app = FastAPI()

    @app.get("/limited")
    async def _limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(RateLimitRule(path_prefix="/limited", limit=5, window_seconds=60),),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/limited")

    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"


async def test_an_unlimited_path_is_untouched():
    app = FastAPI()

    @app.get("/free")
    async def _free() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(RateLimitRule(path_prefix="/limited", limit=1, window_seconds=60),),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(5):
            response = await client.get("/free")

    assert response.status_code == 200
    assert "X-RateLimit-Limit" not in response.headers


async def test_limiting_can_be_disabled():
    app = FastAPI()

    @app.get("/limited")
    async def _limited() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        rules=(RateLimitRule(path_prefix="/limited", limit=1, window_seconds=60),),
        enabled=False,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for _ in range(5):
            response = await client.get("/limited")

    assert response.status_code == 200


# --- Security headers ---------------------------------------------------------


async def test_security_headers_are_present_on_every_response(client):
    response = await client.get("/health")

    for header, value in BASE_HEADERS.items():
        assert response.headers.get(header) == value, header


async def test_framing_is_refused_two_ways(client):
    response = await client.get("/health")

    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


async def test_responses_are_not_cached(client):
    response = await client.get("/health")

    assert "no-store" in response.headers["Cache-Control"]


async def test_hsts_is_absent_outside_deployed_environments(client):
    response = await client.get("/health")

    assert HSTS_HEADER not in response.headers


async def test_hsts_is_present_in_production():
    from app.config import Environment, Settings
    from app.main import create_app

    production = Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment=Environment.PRODUCTION,
        cors_allow_origins="https://app.test",
        auth_secret="a" * 48,
        refresh_cookie_secure=True,
    )

    transport = ASGITransport(app=create_app(production))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.headers[HSTS_HEADER].startswith("max-age=")


async def test_documentation_is_disabled_in_production():
    from app.config import Environment, Settings
    from app.main import create_app

    production = Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment=Environment.PRODUCTION,
        cors_allow_origins="https://app.test",
        auth_secret="a" * 48,
        refresh_cookie_secure=True,
    )

    transport = ASGITransport(app=create_app(production))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs = await client.get("/docs")
        openapi = await client.get("/openapi.json")

    assert docs.status_code == 404
    assert openapi.status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_documentation_is_available_outside_production(client, path):
    response = await client.get(path)

    assert response.status_code == 200
