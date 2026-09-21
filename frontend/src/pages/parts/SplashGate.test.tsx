import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/app/routes";
import { renderApp } from "@/test/render";

/**
 * jsdom has no WebGL, so every test here exercises the fallback path — which is
 * the point: the gate has to open for a visitor whose browser cannot run the
 * shader, and that is the path most likely to rot unnoticed.
 */
beforeEach(() => {
  window.sessionStorage.clear();
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
});

describe("the gate", () => {
  it("meets a first arrival", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    expect(
      await screen.findByRole("button", { name: /slide up to enter/i }),
    ).toBeInTheDocument();
  });

  it("stands aside for the rest of the session", async () => {
    window.sessionStorage.setItem("heimdall.gate", "entered");
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("heading", { name: /see further/i });
    expect(
      screen.queryByRole("button", { name: /slide up to enter/i }),
    ).not.toBeInTheDocument();
  });

  it("never stands between a deep link and its page", async () => {
    renderApp(<AppRoutes />, { route: "/methodology" });

    await screen.findByRole("heading", { name: /how the numbers are produced/i });
    expect(
      screen.queryByRole("button", { name: /slide up to enter/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps the landing page underneath rather than replacing it", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    // The page is mounted the whole time: the gate is an overlay on a scroll
    // runway, not a route. Anything that needs the page can still reach it.
    expect(screen.getByRole("heading", { name: /see further/i })).toBeInTheDocument();
  });

  it("can be left with one control, by keyboard", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/" });

    const enter = await screen.findByRole("button", { name: /slide up to enter/i });
    enter.focus();
    expect(enter).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(window.scrollTo).toHaveBeenCalled();
  });

  it("names the product in Latin letters, not runes", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    // The lockup is artwork; its accessible name carries the readable word.
    expect(screen.getAllByAltText("Heimdall").length).toBeGreaterThan(0);
  });

  it("falls back to the photograph when the shader cannot run", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    await waitFor(() => {
      const plate = document.querySelector(".gate-plate");
      // No WebGL here, so the plate must declare itself static and the still
      // image must be the thing carrying the picture.
      expect(plate).toHaveAttribute("data-static", "true");
    });
    const photo = document.querySelector(".gate-photo");
    expect(photo).not.toHaveClass("opacity-0");
  });

  it("marks the photograph decorative", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    // Every word on the plate is live text above it; the image says nothing a
    // screen reader needs to hear.
    expect(document.querySelector(".gate-photo")).toHaveAttribute("alt", "");
  });

  it("publishes its progress for the page chrome to read", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    await waitFor(() => expect(document.documentElement.dataset.gate).toBe("open"));
    expect(document.documentElement.style.getPropertyValue("--gate-progress")).not.toBe("");
  });

  it("holds the page still instead of letting it slide in", async () => {
    renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    // The defect this replaced: the gate owned a scroll runway and the landing
    // page arrived in normal flow beneath it, so it slid up into view as the
    // mist cleared rather than being revealed by it. The plate is a fixed
    // overlay now and the document is locked at the top.
    expect(document.querySelector(".gate-plate")).toHaveClass("fixed");
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("gives the page back its scroll when it is done", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/" });

    const enter = await screen.findByRole("button", { name: /slide up to enter/i });
    await user.click(enter);

    // The control eases the reveal home over 1.1s, so this outlasts waitFor's
    // default deliberately rather than by accident.
    await waitFor(() => expect(document.querySelector(".gate-plate")).not.toBeInTheDocument(), {
      timeout: 3000,
    });
    // A gate that forgot to release overflow would leave the whole site frozen.
    expect(document.body.style.overflow).toBe("");
    expect(document.body.style.paddingRight).toBe("");
  });

  it("cleans up after itself when it unmounts", async () => {
    const { unmount } = renderApp(<AppRoutes />, { route: "/" });

    await screen.findByRole("button", { name: /slide up to enter/i });
    unmount();

    // A stale data-gate would leave the header permanently faded on every
    // other page.
    expect(document.documentElement.dataset.gate).toBeUndefined();
  });
});
