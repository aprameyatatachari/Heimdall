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

/**
 * Requests a portfolio screen makes on its own, without being asked.
 *
 * Opening a portfolio reads the newest prices and asks which signals are open,
 * and the analysis and stress screens check price coverage for the window on
 * screen. None of that is what most tests are about, so each answers quietly
 * here — a refresh that changed nothing, no open signals, and a window that is
 * fully covered. They sit in the server's base handlers,
 * which are the lowest priority, so a test that cares registers its own.
 */
const backgroundHandlers = [
  http.post(`${API}/portfolios/:portfolioId/market-data/refresh`, ({ params }) =>
    HttpResponse.json({
      portfolio_id: String(params["portfolioId"]),
      data_as_of: "2023-12-29",
      source: "fixture",
      requested_start: "2023-12-22",
      requested_end: "2023-12-29",
      fetched_at: "2026-02-01T10:00:00Z",
      assets_refreshed: 0,
      bars_written: 0,
      results: [],
      failures: [],
      monitoring: null,
    }),
  ),
  http.get(`${API}/portfolios/:portfolioId/signals/summary`, ({ params }) =>
    HttpResponse.json({
      portfolio_id: String(params["portfolioId"]),
      total_open: 0,
      by_severity: { informational: 0, elevated: 0, high: 0, critical: 0 },
      disclaimer: "Educational tool.",
    }),
  ),
  http.get(`${API}/portfolios/:portfolioId/signals`, () =>
    HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
  ),
  http.get(`${API}/portfolios/:portfolioId/market-data/coverage`, ({ params, request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      portfolio_id: String(params["portfolioId"]),
      start: url.searchParams.get("start") ?? "2022-01-03",
      end: url.searchParams.get("end") ?? "2023-12-29",
      source: "fixture",
      complete: true,
      holdings: [],
    });
  }),
];

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
  ...backgroundHandlers,
];

/** A live session: boot refresh succeeds and `/auth/me` answers. */
export const signedInHandlers = [
  http.post(`${API}/auth/refresh`, () => HttpResponse.json(tokenResponse())),
  http.get(`${API}/auth/me`, () => HttpResponse.json(testUser)),
  http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
];

/**
 * An empty portfolio list.
 *
 * Kept out of `signedInHandlers` deliberately: msw resolves with the first
 * matching handler, so a shared `/portfolios` would shadow the one a test
 * registers for itself. Tests that only need to land on `/app` add this.
 */
export const noPortfoliosHandler = http.get(`${API}/portfolios`, () =>
  HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
);
