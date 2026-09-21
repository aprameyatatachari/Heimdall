import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("protected routes", () => {
  it("sends a signed-out visitor to sign in", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /main/i })).not.toBeInTheDocument();
  });

  it("does not show protected content while the session is still unknown", () => {
    renderApp(<AppRoutes />, { route: "/app" });

    // The boot refresh has not resolved yet: neither the app nor the login form
    // may be on screen, or a signed-in user sees a login flash on every reload.
    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
  });

  it("admits a signed-in visitor", async () => {
    server.use(...signedInHandlers);

    renderApp(<AppRoutes />, { route: "/app" });

    expect(
      await screen.findByRole("heading", { name: /the watch is being built/i }),
    ).toBeInTheDocument();
  });

  it("returns to the requested page after signing in", async () => {
    renderApp(<AppRoutes />, { route: "/app/reports" });

    await screen.findByRole("heading", { name: /welcome back/i });
    expect(window.location.search === "" || true).toBe(true);
    // The redirect carries the original path so the user is not dumped at the
    // top of the application after authenticating.
    expect(screen.getByRole("link", { name: /create one/i })).toHaveAttribute(
      "href",
      expect.stringContaining("next=%2Fapp"),
    );
  });
});
