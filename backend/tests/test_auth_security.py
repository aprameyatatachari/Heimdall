"""Unit tests for password hashing and access tokens. No database involved."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.security import (
    TokenError,
    build_password_hasher,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    normalize_email,
    verify_password,
)

SECRET = "unit-test-secret-that-is-long-enough-to-be-realistic"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def hasher():
    # Minimum viable work factors: these tests assert behaviour, not cost.
    return build_password_hasher(time_cost=1, memory_cost_kib=8192, parallelism=1)


# --- Passwords ---------------------------------------------------------------


def test_hash_is_not_the_password(hasher):
    digest = hash_password(PASSWORD, hasher)
    assert PASSWORD not in digest
    assert digest.startswith("$argon2id$")


def test_same_password_hashes_differently_each_time(hasher):
    assert hash_password(PASSWORD, hasher) != hash_password(PASSWORD, hasher)


def test_correct_password_verifies(hasher):
    assert verify_password(PASSWORD, hash_password(PASSWORD, hasher), hasher) is True


def test_wrong_password_does_not_verify(hasher):
    assert verify_password("wrong password entirely", hash_password(PASSWORD, hasher), hasher) is (
        False
    )


def test_verification_of_a_corrupt_hash_returns_false_instead_of_raising(hasher):
    assert verify_password(PASSWORD, "not-a-hash", hasher) is False


def test_verification_is_case_sensitive(hasher):
    digest = hash_password(PASSWORD, hasher)
    assert verify_password(PASSWORD.upper(), digest, hasher) is False


# --- Email normalization -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Person@Example.com", "person@example.com"),
        ("  spaced@example.com  ", "spaced@example.com"),
        ("ALLCAPS@EXAMPLE.COM", "allcaps@example.com"),
    ],
)
def test_email_normalization(raw, expected):
    assert normalize_email(raw) == expected


# --- Access tokens -----------------------------------------------------------


def test_round_trip_preserves_the_user_id():
    user_id = uuid.uuid4()
    token, expires_at = create_access_token(user_id=user_id, secret=SECRET, ttl_minutes=15)

    claims = decode_access_token(token, secret=SECRET)

    assert claims.user_id == user_id
    assert claims.expires_at == expires_at.replace(microsecond=0)


def test_expiry_honours_the_configured_ttl():
    issued = datetime(2026, 1, 1, tzinfo=UTC)
    _, expires_at = create_access_token(
        user_id=uuid.uuid4(),
        secret=SECRET,
        ttl_minutes=30,
        now=issued,
    )
    assert expires_at == issued + timedelta(minutes=30)


def test_a_token_signed_with_another_secret_is_rejected():
    token, _ = create_access_token(user_id=uuid.uuid4(), secret=SECRET, ttl_minutes=15)

    with pytest.raises(TokenError):
        decode_access_token(token, secret="a completely different secret value")


def test_an_expired_token_is_rejected():
    token, _ = create_access_token(
        user_id=uuid.uuid4(),
        secret=SECRET,
        ttl_minutes=1,
        now=datetime.now(UTC) - timedelta(hours=2),
    )

    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_a_token_of_the_wrong_type_is_rejected():
    payload = {
        "sub": str(uuid.uuid4()),
        "typ": "refresh",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")

    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_an_unsigned_token_is_rejected():
    payload = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(payload, key="", algorithm="none")

    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_a_token_without_a_subject_is_rejected():
    payload = {
        "typ": "access",
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(payload, SECRET, algorithm="HS256")

    with pytest.raises(TokenError):
        decode_access_token(token, secret=SECRET)


def test_garbage_is_rejected():
    with pytest.raises(TokenError):
        decode_access_token("not.a.token", secret=SECRET)


# --- Refresh tokens ----------------------------------------------------------


def test_refresh_tokens_are_unique_and_long():
    tokens = {generate_refresh_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 40 for token in tokens)


def test_refresh_token_hash_is_deterministic_and_hides_the_token():
    token = generate_refresh_token()
    digest = hash_refresh_token(token)

    assert digest == hash_refresh_token(token)
    assert token not in digest
    assert len(digest) == 64


def test_different_refresh_tokens_hash_differently():
    assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
        generate_refresh_token()
    )
