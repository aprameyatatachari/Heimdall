import "@testing-library/jest-dom/vitest";

import { afterAll, afterEach, beforeAll } from "vitest";

import { invalidateSession } from "@/api/client";

import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

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
