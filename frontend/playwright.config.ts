import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration.
 *
 * These tests run against a **real backend and a real database** — that is the
 * point of having them next to a unit suite that mocks the network. They prove
 * the journey works across the actual contract, which is the thing a deployment
 * can break without a single unit test noticing.
 *
 * The dev server is used rather than a preview of `dist`, because its proxy puts
 * the API on the same origin, which is how the deployed site is arranged. Testing
 * against a different origin arrangement than production would leave the cookie
 * behaviour untested exactly where it matters.
 *
 * The backend is expected to be running already, and `webServer` starts only the
 * frontend: the API needs migrations applied against a database this file has no
 * business creating. docs/deployment.md and the CI workflow both show the order.
 */
const BASE_URL = process.env["E2E_BASE_URL"] ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  // One worker: the journey registers an account and mutates it throughout, and
  // parallel copies would race each other through the same database.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env["CI"]),
  retries: process.env["CI"] ? 1 : 0,
  // Generous, because the journey fetches real prices from a real provider:
  // a scenario's own window has to be fetched before it can be replayed, and a
  // third party answers when it answers.
  timeout: 240_000,
  expect: { timeout: 15_000 },
  reporter: process.env["CI"] ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env["E2E_BASE_URL"]
    ? undefined
    : {
        command: "npm run dev",
        url: BASE_URL,
        reuseExistingServer: !process.env["CI"],
        timeout: 120_000,
      },
});
