import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { API, errorBody, tokenResponse } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const PASSWORD = "correct horse battery staple";

describe("RegisterPage", () => {
  it("creates an account and lands the new user in the application", async () => {
    server.use(
      http.post(`${API}/auth/register`, () =>
        HttpResponse.json(tokenResponse(), { status: 201 }),
      ),
      http.get(`${API}/auth/me`, () => HttpResponse.json(tokenResponse().user)),
    );

    const { user } = renderApp(<AppRoutes />, { route: "/register" });
    await user.type(screen.getByLabelText(/^email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), PASSWORD);
    await user.type(screen.getByLabelText(/confirm password/i), PASSWORD);
    await user.click(screen.getByRole("button", { name: /^create account$/i }));

    expect(
      await screen.findByRole("heading", { name: /the watch is being built/i }),
    ).toBeInTheDocument();
  });

  it("enforces the backend's minimum password length before submitting", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/register" });
    await user.type(screen.getByLabelText(/^email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.click(screen.getByRole("button", { name: /^create account$/i }));

    expect(await screen.findByText("Use at least 12 characters.")).toBeInTheDocument();
  });

  it("catches a password confirmation that does not match", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/register" });
    await user.type(screen.getByLabelText(/^email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), PASSWORD);
    await user.type(screen.getByLabelText(/confirm password/i), `${PASSWORD} and more`);
    await user.click(screen.getByRole("button", { name: /^create account$/i }));

    expect(await screen.findByText("Passwords do not match.")).toBeInTheDocument();
  });

  it("attaches a server field error to the field it names", async () => {
    server.use(
      http.post(`${API}/auth/register`, () =>
        HttpResponse.json(
          errorBody({
            code: "validation_error",
            message: "Invalid.",
            details: [
              { field: "body.email", message: "That email is already in use.", code: "taken" },
            ],
          }),
          { status: 422 },
        ),
      ),
    );

    const { user } = renderApp(<AppRoutes />, { route: "/register" });
    await user.type(screen.getByLabelText(/^email/i), "taken@example.com");
    await user.type(screen.getByLabelText(/^password/i), PASSWORD);
    await user.type(screen.getByLabelText(/confirm password/i), PASSWORD);
    await user.click(screen.getByRole("button", { name: /^create account$/i }));

    expect(await screen.findByText("That email is already in use.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^email/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("collects only what the backend accepts", () => {
    // The mockups show name fields; RegisterRequest has email and password only.
    renderApp(<AppRoutes />, { route: "/register" });

    expect(screen.queryByLabelText(/first name|last name|full name/i)).not.toBeInTheDocument();
  });
});
