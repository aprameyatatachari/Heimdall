"""Shared FastAPI dependencies: settings, clock, and the request session."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clock import Clock, get_clock
from app.config import Settings, get_settings
from app.database import get_db_session


def get_app_settings(request: Request) -> Settings:
    """Return the settings this application was built with.

    Resolved from `app.state` rather than the process-wide singleton, so
    `create_app(settings)` genuinely determines the application's configuration.
    Reading the singleton here would mean a route saw different settings from the
    middleware, which is how a deployment ends up half-configured.
    """
    configured = getattr(request.app.state, "settings", None)
    return configured if isinstance(configured, Settings) else get_settings()


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]
