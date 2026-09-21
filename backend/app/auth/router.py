"""Authentication endpoints.

Session design, and why:

* The **access token** is a short-lived signed JWT returned in the response body.
  The client keeps it in memory and sends `Authorization: Bearer <token>`. It is
  never written to `localStorage`, so a cross-site scripting bug cannot read a
  long-lived credential.
* The **refresh token** is opaque, high-entropy, and delivered only as an
  HttpOnly cookie scoped to `/api/v1/auth`. JavaScript cannot read it, and it is
  not sent with ordinary API calls. It rotates on every refresh, and replaying a
  rotated token revokes the whole family.

This works without server-side session memory, which matters because production
runs on serverless functions that are discarded between invocations.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.auth.dependencies import AuthServiceDep, CurrentUser
from app.auth.schemas import (
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.auth.service import IssuedSession
from app.common.dependencies import SettingsDep
from app.config import Settings

router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_refresh_cookie(
    response: Response,
    session: IssuedSession,
    settings: Settings,
) -> None:
    """Attach the refresh token as an HttpOnly cookie."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=session.refresh_token,
        expires=session.refresh_token_expires_at,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    """Remove the refresh cookie from the client."""
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.refresh_cookie_domain,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.refresh_cookie_samesite,
    )


def _token_response(session: IssuedSession) -> TokenResponse:
    return TokenResponse(
        access_token=session.access_token,
        expires_at=session.access_token_expires_at,
        user=UserResponse.model_validate(session.user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description="Registers a user and signs them in. Emails are stored lower-cased.",
)
async def register(
    payload: RegisterRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Register a new account."""
    session = await service.register(email=payload.email, password=payload.password)
    _set_refresh_cookie(response, session, settings)
    return _token_response(session)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in",
    description=(
        "Exchanges credentials for an access token. A failed attempt returns the "
        "same error whether or not the address is registered."
    ),
)
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Authenticate an existing account."""
    session = await service.authenticate(email=payload.email, password=payload.password)
    _set_refresh_cookie(response, session, settings)
    return _token_response(session)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate the session",
    description=(
        "Exchanges the refresh cookie for a new access token and a new refresh "
        "cookie. Reusing an already-rotated token revokes every session of that user."
    ),
)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Rotate the refresh token and issue a new access token."""
    presented = request.cookies.get(settings.refresh_cookie_name)
    session = await service.refresh(presented)
    _set_refresh_cookie(response, session, settings)
    return _token_response(session)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Sign out",
    description=(
        "Revokes the presented refresh token and clears the cookie. "
        "Idempotent: signing out twice still succeeds."
    ),
)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> LogoutResponse:
    """Revoke the current session."""
    presented = request.cookies.get(settings.refresh_cookie_name)
    revoked = await service.logout(presented)
    _clear_refresh_cookie(response, settings)
    return LogoutResponse(revoked=revoked)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Current account",
    description="Returns the authenticated user. Requires a valid access token.",
)
async def me(current_user: CurrentUser) -> UserResponse:
    """Return the authenticated user."""
    return UserResponse.model_validate(current_user)
