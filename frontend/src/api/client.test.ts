import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/server";
import { API, errorBody, tokenResponse } from "@/test/handlers";

import {
  api,
  invalidateSession,
  refreshAccessToken,
  request,
  setSessionExpiredHandler,
  tokenStore,
} from "./client";
import { ApiError, NetworkError } from "./errors";

describe("request", () => {
  it("attaches the access token when one is held", async () => {
    tokenStore.set("live-token");
    let seen: string | null = null;
    server.use(
      http.get(`${API}/auth/me`, ({ request: incoming }) => {
        seen = incoming.headers.get("authorization");
        return HttpResponse.json({ ok: true });
      }),
    );

    await api.get("/auth/me");

    expect(seen).toBe("Bearer live-token");
  });

  it("sends no authorization header when auth is disabled", async () => {
    tokenStore.set("live-token");
    let seen: string | null = "unset";
    server.use(
      http.post(`${API}/auth/login`, ({ request: incoming }) => {
        seen = incoming.headers.get("authorization");
        return HttpResponse.json(tokenResponse());
      }),
    );

    await api.post("/auth/login", { email: "a@example.com" }, { auth: false });

    expect(seen).toBeNull();
  });

  it("drops empty query parameters rather than sending blanks", async () => {
    let url = "";
    server.use(
      http.get(`${API}/assets/search`, ({ request: incoming }) => {
        url = incoming.url;
        return HttpResponse.json({ items: [] });
      }),
    );

    await request("/assets/search", {
      params: { query: "AAPL", limit: undefined, cursor: "" },
    });

    expect(url).toContain("query=AAPL");
    expect(url).not.toContain("limit");
    expect(url).not.toContain("cursor");
  });

  it("raises an ApiError carrying the backend code", async () => {
    server.use(
      http.get(`${API}/portfolios`, () =>
        HttpResponse.json(errorBody({ code: "rate_limited", message: "Slow down." }), {
          status: 429,
        }),
      ),
    );

    await expect(api.get("/portfolios")).rejects.toMatchObject({
      code: "rate_limited",
      status: 429,
    });
  });

  it("distinguishes an unreachable server from a failing one", async () => {
    server.use(http.get(`${API}/portfolios`, () => HttpResponse.error()));

    await expect(api.get("/portfolios")).rejects.toBeInstanceOf(NetworkError);
  });

  it("returns undefined for a 204 rather than trying to parse a body", async () => {
    server.use(http.post(`${API}/auth/logout`, () => new HttpResponse(null, { status: 204 })));

    await expect(api.post("/auth/logout")).resolves.toBeUndefined();
  });
});

describe("401 handling", () => {
  it("refreshes once and replays the original request", async () => {
    tokenStore.set("stale-token");
    let attempts = 0;
    let refreshes = 0;

    server.use(
      http.post(`${API}/auth/refresh`, () => {
        refreshes += 1;
        return HttpResponse.json(tokenResponse({ access_token: "fresh-token" }));
      }),
      http.get(`${API}/portfolios`, ({ request: incoming }) => {
        attempts += 1;
        if (incoming.headers.get("authorization") !== "Bearer fresh-token") {
          return HttpResponse.json(
            errorBody({ code: "not_authenticated", message: "Expired." }),
            { status: 401 },
          );
        }
        return HttpResponse.json({ items: [] });
      }),
    );

    await expect(api.get("/portfolios")).resolves.toEqual({ items: [] });
    expect(refreshes).toBe(1);
    expect(attempts).toBe(2);
    expect(tokenStore.get()).toBe("fresh-token");
  });

  it("shares one refresh across concurrent failures", async () => {
    // Several requests failing at once must not each rotate the refresh token:
    // every rotation invalidates the last, which would sign the user out.
    tokenStore.set("stale-token");
    let refreshes = 0;

    server.use(
      http.post(`${API}/auth/refresh`, async () => {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return HttpResponse.json(tokenResponse({ access_token: "fresh-token" }));
      }),
      http.get(`${API}/portfolios`, ({ request: incoming }) =>
        incoming.headers.get("authorization") === "Bearer fresh-token"
          ? HttpResponse.json({ items: [] })
          : HttpResponse.json(errorBody({ code: "not_authenticated", message: "Expired." }), {
              status: 401,
            }),
      ),
    );

    await Promise.all([api.get("/portfolios"), api.get("/portfolios"), api.get("/portfolios")]);

    expect(refreshes).toBe(1);
  });

  it("clears the session when the refresh itself fails", async () => {
    tokenStore.set("stale-token");
    const expired = vi.fn();
    setSessionExpiredHandler(expired);

    server.use(
      http.post(`${API}/auth/refresh`, () =>
        HttpResponse.json(errorBody({ code: "not_authenticated", message: "No." }), {
          status: 401,
        }),
      ),
      http.get(`${API}/portfolios`, () =>
        HttpResponse.json(errorBody({ code: "not_authenticated", message: "Expired." }), {
          status: 401,
        }),
      ),
    );

    await expect(api.get("/portfolios")).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledOnce();
    expect(tokenStore.get()).toBeNull();

    setSessionExpiredHandler(() => {});
  });

  it("discards a refresh that lands after the user signed out", async () => {
    // Without the generation guard this token would be written into the store
    // after sign-out, silently putting the user back into a live session.
    server.use(
      http.post(`${API}/auth/refresh`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json(tokenResponse({ access_token: "late-token" }));
      }),
    );

    const pending = refreshAccessToken();
    invalidateSession();

    await expect(pending).resolves.toBeNull();
    expect(tokenStore.get()).toBeNull();
  });

  it("starts a fresh attempt once the previous one has settled", async () => {
    let refreshes = 0;
    server.use(
      http.post(`${API}/auth/refresh`, () => {
        refreshes += 1;
        return HttpResponse.json(tokenResponse());
      }),
    );

    await refreshAccessToken();
    await refreshAccessToken();

    expect(refreshes).toBe(2);
  });
});
