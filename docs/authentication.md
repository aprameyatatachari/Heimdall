# Authentication

Heimdall uses **short-lived signed access tokens plus rotating opaque refresh
tokens**. This page explains the choice, the flow, and its limitations.

## Why this scheme

Production runs on serverless functions with no persistent process, so any
design that keeps session state in memory is out. Three options were considered:

| Option | Why not chosen |
| --- | --- |
| Server-side sessions in a store | Adds Redis or a session table read on every request, for no benefit over a signed token. |
| Long-lived JWT only | Cannot be revoked. A stolen token stays valid until it expires, and logout becomes a lie. |
| **Short access token + rotating refresh token** | **Chosen.** One database row per session gives real logout and theft detection, while ordinary requests need no session lookup. |

## The tokens

### Access token

* Format: JWT, `HS256`, signed with `AUTH_SECRET`.
* Claims: `sub` (user id), `typ: "access"`, `iat`, `exp`, `jti`.
* Lifetime: `ACCESS_TOKEN_TTL_MINUTES`, default 15 minutes.
* Transport: `Authorization: Bearer <token>`.
* Storage: the client keeps it **in memory only**. It must not be written to
  `localStorage` or `sessionStorage`, so a cross-site scripting bug cannot read a
  reusable credential.
* Not revocable. This is the deliberate trade-off that keeps ordinary requests
  free of a database lookup, and it is why the lifetime is short.

### Refresh token

* Format: 256 bits from `secrets.token_urlsafe`. Opaque — it carries no claims.
* Lifetime: `REFRESH_TOKEN_TTL_DAYS`, default 14 days.
* Transport: an `HttpOnly` cookie named by `REFRESH_COOKIE_NAME`, scoped to
  `Path=/api/v1/auth`. It is therefore not attached to ordinary API calls, and
  browser JavaScript cannot read it.
* Storage: only the **SHA-256 digest** is stored in `refresh_tokens`. A database
  leak does not yield usable session credentials. A plain digest is appropriate
  because the token already has full entropy and is not guessable, so
  key-stretching would add cost without adding security.
* Rotated on every use: the old row is marked revoked and linked to its
  replacement through `replaced_by_id`.

## Flow

```text
POST /auth/register ─┐
POST /auth/login    ─┴─► 201/200  body: access token + user
                              Set-Cookie: heimdall_refresh (HttpOnly)

GET  /auth/me           Authorization: Bearer <access token>

POST /auth/refresh      Cookie: heimdall_refresh
                        ─► new access token + new refresh cookie
                           old refresh token is revoked

POST /auth/logout       Cookie: heimdall_refresh
                        ─► refresh token revoked, cookie cleared
```

## Reuse detection

Presenting a refresh token that has already been rotated or revoked is treated as
a likely theft: Heimdall revokes **every** active refresh token of that user and
returns `401 invalid_refresh_token`. Both the legitimate holder and the attacker
are forced to sign in again, which is the correct outcome when one of them has a
copy of the other's token.

## Error responses

Credential failures are deliberately indistinguishable:

| Situation | Status | Code |
| --- | --- | --- |
| Wrong password | 401 | `invalid_credentials` |
| Unknown email | 401 | `invalid_credentials` |
| Missing `Authorization` header | 401 | `not_authenticated` |
| Expired, forged, or wrong-type access token | 401 | `invalid_access_token` |
| Missing, unknown, expired, revoked, or replayed refresh token | 401 | `invalid_refresh_token` |
| Email already registered | 409 | `email_already_registered` |

A login attempt against an unknown address still performs a password hash, so
response timing does not reveal whether an account exists.

## Password storage

* Algorithm: **Argon2id** (`argon2-cffi`).
* Defaults: `time_cost=3`, `memory_cost=64 MiB`, `parallelism=1`, 32-byte hash,
  16-byte salt.
* Minimum password length: 12 characters. Maximum: 128.
* Hashes are upgraded transparently on the next successful login when the
  configured work factors increase.
* Passwords and hashes are never logged; `app/common/logging.py` redacts the
  known key names, and no code path logs the raw values.

## Ownership authorization

Every private resource is fetched with the owner's id as part of the query
predicate, not checked after loading:

```python
select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id)
```

A portfolio belonging to someone else and a portfolio that does not exist both
return the same `404 portfolio_not_found` with the same message, so the API
cannot be used to enumerate other users' data.

## Cookie configuration

| Deployment | `REFRESH_COOKIE_SECURE` | `REFRESH_COOKIE_SAMESITE` |
| --- | --- | --- |
| Local (`http://localhost`) | `false` | `lax` |
| Same-origin production | `true` | `lax` |
| Frontend on a different origin | `true` | `none` |

Startup fails in preview and production when `SECURE` is false, or when
`SameSite=None` is combined with a non-secure cookie.

## Known limitations

* **Access tokens cannot be revoked.** A signed-out user's access token keeps
  working until it expires, at most `ACCESS_TOKEN_TTL_MINUTES`. Revoking them
  would require a per-request lookup, which this design avoids on purpose.
* **No rate limiting yet.** Login and registration are not throttled. Rate
  limiting arrives in Phase 7.
* **No email verification, password reset, or multi-factor authentication.**
  None is required by the current scope.
* **Single signing key.** Key rotation would invalidate every outstanding access
  token; there is no key-id header yet.
* **Expired refresh tokens are not pruned automatically.** A cleanup helper
  exists (`RefreshTokenRepository.delete_expired`) but is not scheduled.
