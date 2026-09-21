import "@testing-library/jest-dom/vitest";

import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";

import { invalidateSession } from "@/api/client";

import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

beforeEach(() => {
  // Tests exercise the landing page as a returning visitor sees it. The gate is
  // a once-per-session overlay with its own tests; leaving it on would put a
  // full-viewport plate over every other assertion.
  try {
    window.sessionStorage.setItem("heimdall.gate", "entered");
  } catch {
    // Storage is unavailable in this environment; the gate tests opt in anyway.
  }
});

afterEach(() => {
  server.resetHandlers();
  // Also abandons any refresh still in flight, so one test's pending request
  // cannot answer the next test's question.
  invalidateSession();
});

afterAll(() => server.close());

// jsdom does not implement these, and components legitimately use both.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

if (typeof window.IntersectionObserver === "undefined") {
  class NoopObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: number[] = [];
  }
  window.IntersectionObserver = NoopObserver as unknown as typeof IntersectionObserver;
}
