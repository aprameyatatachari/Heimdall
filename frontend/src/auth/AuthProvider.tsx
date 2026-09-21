/**
 * Session state.
 *
 * On boot we attempt one silent refresh. The refresh cookie is HTTP-only, so
 * the only way to know whether a session exists is to ask. Until that answers,
 * status is "loading" and protected routes render nothing rather than briefly
 * flashing the login page at a signed-in user.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  invalidateSession,
  refreshAccessToken,
  setSessionExpiredHandler,
  tokenStore,
} from "@/api/client";
import type { TokenResponse, UserResponse } from "@/api/types";

import { AuthContext, type AuthContextValue, type AuthStatus } from "./context";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<UserResponse | null>(null);
  const booted = useRef(false);

  const clearSession = useCallback(() => {
    // Abandons any refresh in flight as well, so one that is mid-request cannot
    // hand a token back after the user has signed out.
    invalidateSession();
    setUser(null);
    setStatus("anonymous");
    // Everything cached belonged to the session that just ended. Leaving it in
    // place would show one user's portfolios to whoever signs in next.
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setSessionExpiredHandler(clearSession);
  }, [clearSession]);

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;

    // Deliberately not cancelled on cleanup. StrictMode runs this effect twice
    // in development; a cleanup that abandoned the first attempt would leave the
    // second early-returning on `booted`, and the session would never resolve.
    // Setting state after unmount is a no-op in React 18, so letting it finish
    // is safe.
    void (async () => {
      const token = await refreshAccessToken();
      if (!token) {
        setStatus("anonymous");
        return;
      }
      try {
        const me = await api.get<UserResponse>("/auth/me");
        setUser(me);
        setStatus("authenticated");
      } catch {
        clearSession();
      }
    })();
  }, [clearSession]);

  const adopt = useCallback((response: TokenResponse) => {
    tokenStore.set(response.access_token);
    setUser(response.user);
    setStatus("authenticated");
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      adopt(await api.post<TokenResponse>("/auth/login", { email, password }, { auth: false }));
    },
    [adopt],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      // Registration returns tokens, so a new account lands in the application
      // rather than back at a sign-in form.
      adopt(
        await api.post<TokenResponse>("/auth/register", { email, password }, { auth: false }),
      );
    },
    [adopt],
  );

  const signOut = useCallback(async () => {
    try {
      // Ask the server to revoke the refresh token before forgetting it.
      await api.post("/auth/logout");
    } catch {
      // A failed logout call must never strand the user in a signed-in shell.
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, signIn, register, signOut }),
    [status, user, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
