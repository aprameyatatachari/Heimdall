/**
 * The HTTP client.
 *
 * The access token lives in memory only — never localStorage or sessionStorage,
 * both of which are readable by any injected script. The refresh token is an
 * HTTP-only cookie the browser manages; we only ever ask for it to be sent.
 * See AGENTS.md section 5.
 */

import { ApiError, NetworkError, toApiError } from "./errors";

export const API_PREFIX = "/api/v1";

/* -------------------------------------------------------------------------- */
/* Access token store                                                          */
/* -------------------------------------------------------------------------- */

let accessToken: string | null = null;
const listeners = new Set<(token: string | null) => void>();

export const tokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string | null): void {
    accessToken = token;
    for (const listener of listeners) listener(token);
  },
  subscribe(listener: (token: string | null) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

/* -------------------------------------------------------------------------- */
/* Session expiry                                                              */
/* -------------------------------------------------------------------------- */

type ExpiryHandler = () => void;
let onSessionExpired: ExpiryHandler = () => {};

/** Registered once by the auth provider, so a dead session clears the cache. */
export function setSessionExpiredHandler(handler: ExpiryHandler): void {
  onSessionExpired = handler;
}

/* -------------------------------------------------------------------------- */
/* Refresh, single-flight                                                      */
/* -------------------------------------------------------------------------- */

let inFlightRefresh: Promise<string | null> | null = null;

/**
 * Bumped whenever the session is deliberately ended.
 *
 * A refresh already in flight when a user signs out must not write its result
 * into the token store afterwards — that would silently re-authenticate them.
 * Each attempt records the generation it began in and discards its own result
 * if the session moved on underneath it.
 */
let sessionGeneration = 0;

/** End the current session and abandon any refresh in flight. */
export function invalidateSession(): void {
  sessionGeneration += 1;
  inFlightRefresh = null;
  tokenStore.set(null);
}

/**
 * Exchange the refresh cookie for a new access token.
 *
 * Concurrent callers share one request. Firing several would rotate the token
 * repeatedly and each rotation would invalidate the previous one, signing the
 * user out in the middle of a working session.
 */
export function refreshAccessToken(): Promise<string | null> {
  const generation = sessionGeneration;
  inFlightRefresh ??= (async () => {
    try {
      const response = await fetch(`${API_PREFIX}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return null;
      const body = (await response.json()) as { access_token?: string };
      const token = body.access_token ?? null;
      if (generation !== sessionGeneration) return null;
      tokenStore.set(token);
      return token;
    } catch {
      return null;
    } finally {
      // Callers already awaiting hold the promise itself, so clearing the slot
      // here only affects callers arriving after this attempt settled — who
      // should get a fresh attempt, not this one's stale answer.
      if (generation === sessionGeneration) inFlightRefresh = null;
    }
  })();
  return inFlightRefresh;
}

/* -------------------------------------------------------------------------- */
/* Request                                                                     */
/* -------------------------------------------------------------------------- */

export interface RequestOptions extends Omit<RequestInit, "body"> {
  /** Parsed as JSON. Use `formData` for uploads. */
  json?: unknown;
  formData?: FormData;
  /** Attach the access token. Default true. */
  auth?: boolean;
  /** Query parameters; undefined and null entries are dropped. */
  params?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = path.startsWith("http") ? path : `${API_PREFIX}${path}`;
  if (!params) return url;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${url}?${query}` : url;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const { json, formData, auth = true, params, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  finalHeaders.set("Accept", "application/json");
  if (json !== undefined) finalHeaders.set("Content-Type", "application/json");

  const token = auth ? tokenStore.get() : null;
  if (token) finalHeaders.set("Authorization", `Bearer ${token}`);

  let body: BodyInit | undefined;
  if (formData) body = formData;
  else if (json !== undefined) body = JSON.stringify(json);

  try {
    return await fetch(buildUrl(path, params), {
      ...rest,
      headers: finalHeaders,
      body,
      credentials: "include",
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }
}

/**
 * Perform a request, refreshing once on a 401 and replaying the original call.
 *
 * A second 401 after a successful refresh means the session is genuinely over;
 * the expiry handler clears cached data so one user's portfolios can never be
 * shown to whoever signs in next.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);

  if (response.status === 401 && options.auth !== false) {
    const token = await refreshAccessToken();
    if (token) {
      response = await send(path, options);
    }
    if (response.status === 401) {
      invalidateSession();
      onSessionExpired();
      throw await toApiError(response);
    }
  }

  if (!response.ok) throw await toApiError(response);

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined as T;
  return (await response.json()) as T;
}

/** Fetch binary content (a generated report) through the authenticated client. */
export async function requestBlob(
  path: string,
  options: RequestOptions = {},
): Promise<{ blob: Blob; filename: string | null }> {
  let response = await send(path, { ...options, headers: { Accept: "application/pdf" } });

  if (response.status === 401) {
    const token = await refreshAccessToken();
    if (token)
      response = await send(path, { ...options, headers: { Accept: "application/pdf" } });
    if (response.status === 401) {
      invalidateSession();
      onSessionExpired();
      throw await toApiError(response);
    }
  }
  if (!response.ok) throw await toApiError(response);

  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", json }),
  patch: <T>(path: string, json?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", json }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};

export { ApiError, NetworkError };
