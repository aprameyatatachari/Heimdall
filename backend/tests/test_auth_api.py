"""Integration tests for the authentication endpoints.

These run against PostgreSQL. Each test's writes are rolled back afterwards.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_postgres

pytestmark = [pytest.mark.integration, requires_postgres]

PASSWORD = "correct horse battery staple"
REFRESH_COOKIE = "heimdall_refresh"


def _credentials(email: str | None = None) -> dict[str, str]:
    return {
        "email": email or f"user-{uuid.uuid4().hex[:12]}@example.com",
        "password": PASSWORD,
    }


async def _register(api, credentials: dict[str, str] | None = None):
    payload = credentials or _credentials()
    response = await api.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload, response


# --- Registration ------------------------------------------------------------


async def test_registration_returns_an_access_token_and_the_user(api):
    credentials, response = await _register(api)
    body = response.json()

    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_at"]
    assert body["user"]["email"] == credentials["email"]
    assert uuid.UUID(body["user"]["id"])


async def test_registration_never_returns_the_password_hash(api):
    _, response = await _register(api)

    assert "password_hash" not in response.text
    assert "argon2" not in response.text.lower()
    assert PASSWORD not in response.text


async def test_registration_sets_an_httponly_refresh_cookie(api):
    _, response = await _register(api)

    cookie_header = response.headers.get("set-cookie", "")
    assert REFRESH_COOKIE in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header
    # The refresh token must never appear in the response body.
    assert api.cookies.get(REFRESH_COOKIE) not in response.text


async def test_email_is_stored_lower_cased(api):
    credentials = _credentials("MixedCase@Example.Com")
    _, response = await _register(api, credentials)

    assert response.json()["user"]["email"] == "mixedcase@example.com"


async def test_registering_the_same_email_twice_conflicts(api):
    credentials, _ = await _register(api)

    response = await api.post("/api/v1/auth/register", json=credentials)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_registered"


async def test_registration_is_case_insensitive_for_duplicates(api):
    credentials = _credentials("Duplicate@Example.Com")
    await _register(api, credentials)

    response = await api.post(
        "/api/v1/auth/register",
        json={"email": "DUPLICATE@example.com", "password": PASSWORD},
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["short", "elevenchars", "          "],  # 5, 11, and whitespace-only
)
async def test_weak_passwords_are_rejected(api, password):
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": f"weak-{uuid.uuid4().hex[:8]}@example.com", "password": password},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_malformed_email_is_rejected_with_a_field_detail(api):
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": PASSWORD},
    )

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert any(detail["field"] == "email" for detail in details)


# --- Login -------------------------------------------------------------------


async def test_login_succeeds_with_correct_credentials(api):
    credentials, _ = await _register(api)

    response = await api.post("/api/v1/auth/login", json=credentials)

    assert response.status_code == 200
    assert response.json()["user"]["email"] == credentials["email"]


async def test_login_accepts_a_differently_cased_email(api):
    credentials = _credentials("Casing@Example.Com")
    await _register(api, credentials)

    response = await api.post(
        "/api/v1/auth/login",
        json={"email": "CASING@EXAMPLE.COM", "password": PASSWORD},
    )

    assert response.status_code == 200


async def test_login_with_a_wrong_password_is_rejected(api):
    credentials, _ = await _register(api)

    response = await api.post(
        "/api/v1/auth/login",
        json={"email": credentials["email"], "password": "definitely not the password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_for_an_unknown_account_returns_the_same_error(api):
    """The API must not reveal whether an address is registered."""
    credentials, _ = await _register(api)

    wrong_password = await api.post(
        "/api/v1/auth/login",
        json={"email": credentials["email"], "password": "definitely not the password"},
    )
    unknown_user = await api.post(
        "/api/v1/auth/login",
        json={"email": "nobody-here@example.com", "password": PASSWORD},
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"]["code"] == unknown_user.json()["error"]["code"]
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]


# --- Current user ------------------------------------------------------------


async def test_me_returns_the_authenticated_user(api):
    credentials, response = await _register(api)
    token = response.json()["access_token"]

    me = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["email"] == credentials["email"]
    assert "password_hash" not in me.text


async def test_me_without_a_token_is_rejected(api):
    response = await api.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(
    "header",
    [
        "Bearer not-a-real-token",
        "Basic dXNlcjpwYXNz",
        "Bearer ",
        "totally-wrong",
    ],
)
async def test_me_with_a_bad_authorization_header_is_rejected(api, header):
    response = await api.get("/api/v1/auth/me", headers={"Authorization": header})

    assert response.status_code == 401


async def test_me_with_another_users_token_returns_that_other_user(api):
    """Sanity check that tokens are per-user, not global."""
    _, first = await _register(api)
    _, second = await _register(api)

    first_me = await api.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {first.json()['access_token']}"},
    )
    second_me = await api.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {second.json()['access_token']}"},
    )

    assert first_me.json()["id"] != second_me.json()["id"]


# --- Refresh and logout ------------------------------------------------------


async def test_refresh_issues_a_new_access_token(api):
    _, registration = await _register(api)
    original = registration.json()["access_token"]

    response = await api.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]
    # A new token is minted; it may or may not differ textually within the same
    # second, so assert usability rather than inequality.
    me = await api.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert original


async def test_refresh_without_a_cookie_is_rejected(api):
    response = await api.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


async def test_refresh_rotates_the_cookie(api):
    await _register(api)
    before = api.cookies.get(REFRESH_COOKIE)

    await api.post("/api/v1/auth/refresh")
    after = api.cookies.get(REFRESH_COOKIE)

    assert before is not None
    assert after is not None
    assert before != after


async def test_replaying_a_rotated_refresh_token_is_rejected(api):
    await _register(api)
    stolen = api.cookies.get(REFRESH_COOKIE)

    await api.post("/api/v1/auth/refresh")

    api.cookies.clear()
    api.cookies.set(REFRESH_COOKIE, stolen)
    response = await api.post("/api/v1/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


async def test_replaying_a_rotated_token_revokes_the_whole_session_family(api):
    """Reuse suggests theft, so every active token for that user is revoked."""
    await _register(api)
    stolen = api.cookies.get(REFRESH_COOKIE)

    await api.post("/api/v1/auth/refresh")
    current = api.cookies.get(REFRESH_COOKIE)

    api.cookies.clear()
    api.cookies.set(REFRESH_COOKIE, stolen)
    await api.post("/api/v1/auth/refresh")

    api.cookies.clear()
    api.cookies.set(REFRESH_COOKIE, current)
    still_usable = await api.post("/api/v1/auth/refresh")
    assert still_usable.status_code == 401


async def test_logout_revokes_the_session(api):
    await _register(api)

    logout = await api.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["revoked"] is True

    refresh = await api.post("/api/v1/auth/refresh")
    assert refresh.status_code == 401


async def test_logout_is_idempotent(api):
    await _register(api)

    first = await api.post("/api/v1/auth/logout")
    second = await api.post("/api/v1/auth/logout")

    assert first.status_code == 200
    assert second.status_code == 200


async def test_logout_without_a_session_still_succeeds(api):
    response = await api.post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert response.json()["revoked"] is False


async def test_an_access_token_still_works_after_logout_until_it_expires(api):
    """Documented trade-off: access tokens are short-lived, not revocable."""
    _, registration = await _register(api)
    token = registration.json()["access_token"]

    await api.post("/api/v1/auth/logout")

    me = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
