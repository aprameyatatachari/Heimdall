"""Tests for configuration parsing and production safety rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import DEV_AUTH_SECRET, Environment, Settings


def _settings(**overrides) -> Settings:
    base = {
        "environment": Environment.LOCAL,
        "database_url": "postgresql+asyncpg://user:pw@localhost:5432/heimdall",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_cors_origins_accept_a_comma_separated_string():
    settings = _settings(cors_allow_origins="http://a.test, https://b.test")
    assert settings.cors_allow_origins == ["http://a.test", "https://b.test"]


def test_production_rejects_debug_mode():
    with pytest.raises(ValidationError, match="debug must be disabled in production"):
        _settings(
            environment=Environment.PRODUCTION,
            debug=True,
            cors_allow_origins="https://app.test",
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="wildcard CORS origins"):
        _settings(environment=Environment.PRODUCTION, cors_allow_origins="*")


def test_production_requires_at_least_one_cors_origin():
    with pytest.raises(ValidationError, match="CORS_ALLOW_ORIGINS must be set"):
        _settings(environment=Environment.PRODUCTION, cors_allow_origins="")


def _production(**overrides) -> Settings:
    """A minimally valid production configuration."""
    base = {
        "environment": Environment.PRODUCTION,
        "cors_allow_origins": "https://app.test",
        "auth_secret": "a" * 48,
        "refresh_cookie_secure": True,
        "refresh_cookie_samesite": "none",
    }
    base.update(overrides)
    return _settings(**base)


def test_production_configuration_is_accepted_when_safe():
    assert _production().is_production is True


def test_production_refuses_the_development_auth_secret():
    with pytest.raises(ValidationError, match="AUTH_SECRET must be set"):
        _production(auth_secret=DEV_AUTH_SECRET)


def test_production_refuses_a_short_auth_secret():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        _production(auth_secret="too-short")


def test_production_requires_secure_refresh_cookies():
    with pytest.raises(ValidationError, match="REFRESH_COOKIE_SECURE"):
        _production(refresh_cookie_secure=False)


def test_preview_is_held_to_the_same_secret_rules_as_production():
    with pytest.raises(ValidationError, match="AUTH_SECRET must be set"):
        _settings(
            environment=Environment.PREVIEW,
            auth_secret=DEV_AUTH_SECRET,
            refresh_cookie_secure=True,
        )


def test_local_development_may_use_the_placeholder_secret():
    settings = _settings(environment=Environment.LOCAL)
    assert settings.auth_secret.get_secret_value() == DEV_AUTH_SECRET


def test_the_auth_secret_is_not_printed_in_a_repr():
    settings = _production()
    assert "aaaa" not in repr(settings)
    assert "a" * 48 not in str(settings.auth_secret)


def test_the_refresh_cookie_is_scoped_to_the_auth_endpoints():
    assert _settings().refresh_cookie_path == "/api/v1/auth"


def test_migration_url_prefers_the_direct_connection():
    settings = _settings(
        database_url="postgresql+asyncpg://user:pw@pooler:5432/heimdall",
        database_url_direct="postgresql+asyncpg://user:pw@direct:5432/heimdall",
    )
    assert "direct" in settings.migration_database_url


def test_migration_url_falls_back_to_the_pooled_connection():
    settings = _settings(database_url="postgresql+asyncpg://user:pw@pooler:5432/heimdall")
    assert "pooler" in settings.migration_database_url


def test_sync_database_url_drops_the_async_driver():
    settings = _settings(database_url="postgresql+asyncpg://user:pw@localhost:5432/heimdall")
    assert settings.sync_database_url().startswith("postgresql://")
