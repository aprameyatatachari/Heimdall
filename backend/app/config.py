"""Application configuration.

All configuration is environment-based. No secret ever has a usable default:
production startup fails loudly when a required secret is missing.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_NAME = "Heimdall"
API_TITLE = "Heimdall Risk Intelligence API"
API_DESCRIPTION = (
    "Heimdall is a portfolio risk-intelligence platform for measuring exposure, "
    "analyzing performance, and testing how investments respond to adverse market scenarios."
)
API_V1_PREFIX = "/api/v1"

# Placeholder signing key. Usable in local development and tests only; the
# settings validator refuses it in preview and production.
DEV_AUTH_SECRET = "dev-only-insecure-secret-do-not-use-outside-local"  # noqa: S105


class Environment(StrEnum):
    """Deployment environment."""

    LOCAL = "local"
    TEST = "test"
    PREVIEW = "preview"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Runtime settings loaded from the environment (and `.env` locally)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core -----------------------------------------------------------------
    environment: Environment = Environment.LOCAL
    debug: bool = False
    version: str = "0.1.0"

    # --- Database -------------------------------------------------------------
    # Pooled URL used by the application at runtime.
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://heimdall:heimdall@localhost:5433/heimdall"),
    )
    # Direct (non-pooled) URL, required by some managed providers for migrations.
    database_url_direct: PostgresDsn | None = None
    db_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    db_connect_timeout_seconds: int = Field(default=10, ge=1, le=120)

    # Serverless deployments must not hold a connection pool across invocations.
    serverless: bool = False

    # --- HTTP -----------------------------------------------------------------
    # Comma-separated in the environment, e.g. "http://localhost:5173,https://app.example.com".
    # `NoDecode` keeps pydantic-settings from JSON-decoding the raw value, so the
    # validator below can accept a plain comma-separated string.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    max_request_body_bytes: int = Field(default=2 * 1024 * 1024, ge=1024)

    # --- Rate limiting --------------------------------------------------------
    # In-process fixed-window limiting. Disabled in tests so they stay hermetic.
    # See docs/security.md for the per-instance caveat under serverless execution.
    rate_limit_enabled: bool = True

    # --- Logging --------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "console"

    # --- Market data ----------------------------------------------------------
    # Only the offline fixture provider exists so far. Every test and local
    # development run uses it, so results never depend on a third party.
    market_data_provider: Literal["fixture"] = "fixture"
    market_data_api_key: SecretStr | None = None
    # Where the fixture provider reads its committed series from. Set explicitly in
    # a container, where the repository's `fixtures/` directory is mounted rather
    # than baked into the image.
    market_data_fixture_root: str | None = None

    # --- Early Warning System -------------------------------------------------
    # Protects the scheduled monitoring endpoint. When unset, that endpoint refuses
    # to run rather than running unprotected.
    cron_secret: SecretStr | None = None
    # Portfolios evaluated per scheduled invocation. Bounded so a run fits inside a
    # serverless function's configured duration.
    monitoring_batch_size: int = Field(default=25, ge=1, le=200)

    # --- Authentication -------------------------------------------------------
    # Signs access tokens. The placeholder below is refused outside local and test.
    auth_secret: SecretStr = SecretStr(DEV_AUTH_SECRET)
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=365)
    # Cookie carrying the refresh token. `secure` and `samesite=none` are required
    # when the frontend is served from a different origin than the API.
    refresh_cookie_name: str = "heimdall_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_domain: str | None = None
    # Argon2id work factors. Lowered in tests so the suite stays fast.
    argon2_time_cost: int = Field(default=3, ge=1, le=20)
    argon2_memory_cost_kib: int = Field(default=65536, ge=8192, le=1048576)
    argon2_parallelism: int = Field(default=1, ge=1, le=16)

    @property
    def refresh_cookie_path(self) -> str:
        """Cookie path, scoped to the endpoints that consume the refresh token."""
        return f"{API_V1_PREFIX}/auth"

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a real list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Settings:
        """Refuse unsafe production configuration."""
        if self.environment is Environment.PRODUCTION:
            if self.debug:
                raise ValueError("debug must be disabled in production")
            if any(origin == "*" for origin in self.cors_allow_origins):
                raise ValueError("wildcard CORS origins are not allowed in production")
            if not self.cors_allow_origins:
                raise ValueError("CORS_ALLOW_ORIGINS must be set in production")

        if self.environment in (Environment.PRODUCTION, Environment.PREVIEW):
            if self.auth_secret.get_secret_value() == DEV_AUTH_SECRET:
                raise ValueError("AUTH_SECRET must be set outside local development")
            if len(self.auth_secret.get_secret_value()) < 32:
                raise ValueError("AUTH_SECRET must be at least 32 characters")
            if not self.refresh_cookie_secure:
                raise ValueError("REFRESH_COOKIE_SECURE must be true outside local development")
            if self.refresh_cookie_samesite == "none" and not self.refresh_cookie_secure:
                raise ValueError("SameSite=None cookies must also be Secure")
        return self

    @property
    def is_production(self) -> bool:
        """True when running with production guarantees."""
        return self.environment is Environment.PRODUCTION

    @property
    def migration_database_url(self) -> str:
        """URL Alembic should use, preferring the direct connection when provided."""
        return str(self.database_url_direct or self.database_url)

    def sync_database_url(self) -> str:
        """The configured database URL rewritten for a synchronous driver."""
        return str(self.database_url).replace("+asyncpg", "", 1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache. Used by tests that patch the environment."""
    get_settings.cache_clear()


def running_under_pytest() -> bool:
    """True when the process was started by pytest."""
    return "PYTEST_CURRENT_TEST" in os.environ
