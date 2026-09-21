import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { API, errorBody, tokenResponse } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

async function fillAndSubmit(
  user: ReturnType<typeof renderApp>["user"],
  email: string,
  password: string,
) {
  await user.type(screen.getByLabelText(/email/i), email);
  await user.type(screen.getByLabelText(/^password/i), password);
  await user.click(screen.getByRole("button", { name: /^sign in$/i }));
}

describe("LoginPage", () => {
  it("signs a user in and lands them in the application", async () => {
    server.use(
      http.post(`${API}/auth/login`, () => HttpResponse.json(tokenResponse())),
      http.get(`${API}/auth/me`, () => HttpResponse.json(tokenResponse().user)),
    );

    const { user } = renderApp(<AppRoutes />, { route: "/login" });
    await fillAndSubmit(user, "watcher@example.com", "correct horse battery staple");

    expect(await screen.findByRole("heading", { name: /your watch/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText("watcher@example.com").length).toBeGreaterThan(0),
    );
  });

  it("does not reveal whether an email is registered", async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json(
          errorBody({ code: "invalid_credentials", message: "Invalid credentials." }),
          { status: 401 },
        ),
      ),
    );

    const { user } = renderApp(<AppRoutes />, { route: "/login" });
    await fillAndSubmit(user, "stranger@example.com", "whatever this is");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Email or password is incorrect.");
    // The message must not distinguish a missing account from a wrong password.
    expect(alert).not.toHaveTextContent(/no account|not registered|unknown user/i);
  });

  it("surfaces a rate limit as its own message", async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json(
          errorBody({ code: "rate_limited", message: "Too many attempts. Try again in 60s." }),
          { status: 429 },
        ),
      ),
    );

    const { user } = renderApp(<AppRoutes />, { route: "/login" });
    await fillAndSubmit(user, "watcher@example.com", "correct horse battery staple");

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many attempts/i);
  });

  it("validates before sending anything to the server", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/login" });
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
  });

  it("marks an invalid field for assistive technology", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/login" });
    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() =>
      expect(screen.getByLabelText(/email/i)).toHaveAttribute("aria-invalid", "true"),
    );
    expect(screen.getByLabelText(/email/i)).toHaveAccessibleDescription(
      "Enter a valid email address.",
    );
  });

  it("keeps the submit button disabled while the request is in flight", async () => {
    server.use(
      http.post(`${API}/auth/login`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json(tokenResponse());
      }),
      http.get(`${API}/auth/me`, () => HttpResponse.json(tokenResponse().user)),
    );

    const { user } = renderApp(<AppRoutes />, { route: "/login" });
    await fillAndSubmit(user, "watcher@example.com", "correct horse battery staple");

    expect(await screen.findByRole("button", { name: /signing in/i })).toBeDisabled();
  });
});
