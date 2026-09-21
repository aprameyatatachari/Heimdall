import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("signing out", () => {
  it("returns the user to the public site and closes the application", async () => {
    server.use(...signedInHandlers);
    const { user } = renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByRole("heading", { name: /your watch/i });

    await user.click(screen.getByRole("button", { name: /watcher@example.com/i }));
    await user.click(screen.getByRole("menuitem", { name: /sign out/i }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: /your watch/i })).not.toBeInTheDocument(),
    );
  });

  it("keeps the account menu reachable by keyboard", async () => {
    server.use(...signedInHandlers);
    const { user } = renderApp(<AppRoutes />, { route: "/app" });
    await screen.findByRole("heading", { name: /your watch/i });

    const trigger = screen.getByRole("button", { name: /watcher@example.com/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    trigger.focus();
    await user.keyboard("{Enter}");
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
  });
});
