import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { createQueryClient } from "@/app/queryClient";
import { AppRoutes } from "@/app/routes";
import { signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

import { AuthProvider } from "./AuthProvider";

describe("AuthProvider", () => {
  it("resolves the session under StrictMode's double-invoked effects", async () => {
    // StrictMode runs effects twice in development. A boot attempt abandoned by
    // the first cleanup would leave the second early-returning, and the session
    // would hang on "Checking your session" forever.
    server.use(...signedInHandlers);

    render(
      <StrictMode>
        <QueryClientProvider client={createQueryClient()}>
          <MemoryRouter initialEntries={["/app"]}>
            <AuthProvider>
              <AppRoutes />
            </AuthProvider>
          </MemoryRouter>
        </QueryClientProvider>
      </StrictMode>,
    );

    expect(await screen.findByRole("heading", { name: /your watch/i })).toBeInTheDocument();
  });

  it("carries a deep link's destination through to sign-in", async () => {
    // A visitor asking for a page inside the application must come back to it
    // after authenticating, not be dropped at the top.
    renderApp(<AppRoutes />, { route: "/app/reports" });

    await screen.findByRole("heading", { name: /welcome back/i });
    expect(screen.getByRole("link", { name: /create one/i })).toHaveAttribute(
      "href",
      expect.stringContaining("next=%2Fapp%2Freports"),
    );
  });
});
