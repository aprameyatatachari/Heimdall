"""FastAPI application factory.

The module exposes both `create_app()` for tests and a module-level `app` for
ASGI servers and the Vercel Python runtime.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analytics.router import portfolio_router as analytics_portfolio_router
from app.analytics.router import runs_router as analysis_runs_router
from app.auth.router import router as auth_router
from app.common.disclaimer import DISCLAIMER
from app.common.errors import ERROR_RESPONSES, register_exception_handlers
from app.common.logging import REQUEST_ID_HEADER, configure_logging, get_logger
from app.common.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.common.rate_limit import RateLimitMiddleware, default_rules
from app.common.security_headers import SecurityHeadersMiddleware
from app.config import (
    API_DESCRIPTION,
    API_TITLE,
    API_V1_PREFIX,
    Environment,
    Settings,
    get_settings,
)
from app.database import dispose_engine
from app.early_warning.router import catalogue_router as ews_catalogue_router
from app.early_warning.router import internal_router as ews_internal_router
from app.early_warning.router import portfolio_router as ews_portfolio_router
from app.early_warning.router import runs_router as ews_runs_router
from app.early_warning.router import signals_router as ews_signals_router
from app.health.router import router as health_router
from app.market_data.router import assets_router, portfolio_market_data_router
from app.portfolios.router import router as portfolios_router
from app.reports.router import portfolio_router as reports_portfolio_router
from app.reports.router import reports_router
from app.stress_testing.router import portfolio_router as stress_portfolio_router
from app.stress_testing.router import runs_router as stress_runs_router
from app.stress_testing.router import scenarios_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-up and shut-down hooks.

    Database migrations are intentionally NOT run here. They are applied by a
    controlled release step so that a cold start never mutates the schema.
    """
    settings: Settings = app.state.settings
    logger.info(
        "application_startup",
        environment=str(settings.environment),
        version=settings.version,
        serverless=settings.serverless,
    )
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the Heimdall API application."""
    resolved = settings or get_settings()
    configure_logging(level=resolved.log_level, log_format=resolved.log_format)

    app = FastAPI(
        title=API_TITLE,
        description=f"{API_DESCRIPTION}\n\n**Disclaimer.** {DISCLAIMER}",
        version=resolved.version,
        docs_url=None if resolved.is_production else "/docs",
        redoc_url=None if resolved.is_production else "/redoc",
        openapi_url=None if resolved.is_production else "/openapi.json",
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
    )
    app.state.settings = resolved

    # Middleware executes bottom-up: CORS wraps the body limit, which wraps
    # request context, so every log line and error carries a request ID.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=resolved.max_request_body_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        rules=default_rules(API_V1_PREFIX),
        enabled=resolved.rate_limit_enabled,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=resolved.environment in (Environment.PRODUCTION, Environment.PREVIEW),
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health_router)

    api = APIRouter(prefix=API_V1_PREFIX)
    api.include_router(auth_router)
    api.include_router(portfolios_router)
    api.include_router(assets_router)
    api.include_router(portfolio_market_data_router)
    api.include_router(analytics_portfolio_router)
    api.include_router(analysis_runs_router)
    api.include_router(scenarios_router)
    api.include_router(stress_portfolio_router)
    api.include_router(stress_runs_router)
    api.include_router(ews_catalogue_router)
    api.include_router(ews_portfolio_router)
    api.include_router(ews_signals_router)
    api.include_router(ews_runs_router)
    api.include_router(ews_internal_router)
    api.include_router(reports_portfolio_router)
    api.include_router(reports_router)
    app.include_router(api)

    app.state.api_prefix = API_V1_PREFIX

    return app


app = create_app()
