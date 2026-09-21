import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullPageLoader } from "@/components/FullPageLoader";

import { useAuth } from "./useAuth";

/**
 * Gate for every `/app` route.
 *
 * While the boot refresh is still in flight the status is "loading" and we
 * render the loader rather than redirecting — otherwise a signed-in user is
 * bounced to the login page for a frame on every hard refresh.
 */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageLoader label="Checking your session" />;

  if (status === "anonymous") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return <Outlet />;
}
