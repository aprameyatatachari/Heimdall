import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "@/auth/RequireAuth";
import { AppHomePage } from "@/pages/AppHomePage";
import { LandingPage } from "@/pages/LandingPage";
import { LimitationsPage } from "@/pages/LimitationsPage";
import { LoginPage } from "@/pages/LoginPage";
import { MethodologyPage } from "@/pages/MethodologyPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { AppShell } from "@/pages/parts/AppShell";

/**
 * The route table, separate from the router itself so tests can mount it inside
 * a MemoryRouter at any starting path.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/methodology" element={<MethodologyPage />} />
      <Route path="/limitations" element={<LimitationsPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Every `/app` path sits inside the guard, including ones no screen
          serves yet, so a deep link redirects to sign-in carrying where the
          visitor was actually going rather than dropping them at the top. */}
      <Route element={<RequireAuth />}>
        <Route path="/app" element={<AppShell />}>
          <Route index element={<AppHomePage />} />
          {/* Phases 9 to 11 mount their screens here. */}
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
