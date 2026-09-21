/**
 * Default request handlers.
 *
 * Response shapes mirror the generated types, so a fixture cannot silently
 * drift from the contract: if the backend changes, `npm run api:types`
 * regenerates and these fail to compile. AGENTS.md section 8.
 */

import { http, HttpResponse } from "msw";

import type { ApiErrorBody } from "@/api/errors";
import type { TokenResponse, UserResponse } from "@/api/types";

export const API = "/api/v1";

export const testUser: UserResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "watcher@example.com",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

export function tokenResponse(overrides: Partial<TokenResponse> = {}): TokenResponse {
  return {
    access_token: "test-access-token",
    token_type: "bearer",
    expires_at: "2099-01-01T00:00:00Z",
    user: testUser,
    ...overrides,
  };
}

export function errorBody(body: Partial<ApiErrorBody> & { code: string; message: string }) {
  return { error: { details: null, request_id: "test-request", ...body } };
}

/** Signed out: the refresh cookie buys nothing and `/auth/me` is refused. */
export const handlers = [
  http.post(`${API}/auth/refresh`, () =>
    HttpResponse.json(errorBody({ code: "not_authenticated", message: "Not authenticated." }), {
      status: 401,
    }),
  ),
  http.get(`${API}/auth/me`, () =>
    HttpResponse.json(errorBody({ code: "not_authenticated", message: "Not authenticated." }), {
      status: 401,
    }),
  ),
  http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
];

/** A live session: boot refresh succeeds and `/auth/me` answers. */
export const signedInHandlers = [
  http.post(`${API}/auth/refresh`, () => HttpResponse.json(tokenResponse())),
  http.get(`${API}/auth/me`, () => HttpResponse.json(testUser)),
  http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
];
