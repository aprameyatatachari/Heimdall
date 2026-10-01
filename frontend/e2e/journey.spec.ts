import { expect, test, type Page } from "@playwright/test";

/**
 * The primary user journey, end to end.
 *
 * One test, deliberately: this is a journey, not a set of independent checks,
 * and each step depends on the state the previous one created. Splitting it
 * would either re-run the whole setup per step or leave the steps coupled
 * through shared state, and the second is worse than a long test.
 *
 * It runs against a real API and a real database. Every assertion is on
 * something a user would see — a figure on a tile, a row in a table, a
 * disclosure that opens — rather than on an internal call, so it fails for the
 * same reasons a person would notice.
 */

const PASSWORD = "a long enough passphrase for heimdall";
const WINDOW = { start: "2022-01-03", end: "2023-12-29" };

function uniqueEmail(): string {
  return `journey-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

/** The splash gate is once per session and would sit over every other step. */
async function skipGate(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      window.sessionStorage.setItem("heimdall.gate", "entered");
    } catch {
      // Storage unavailable; the gate's own control still dismisses it.
    }
  });
}

/** The portfolio's own tabs. The shell's main nav repeats these names. */
function tab(page: Page, name: string) {
  return page
    .getByRole("navigation", { name: "Portfolio sections" })
    .getByRole("link", { name });
}

test("a new visitor can register, build a portfolio, analyse it and report on it", async ({
  page,
}) => {
  const email = uniqueEmail();
  await skipGate(page);

  await test.step("registers and lands inside the application", async () => {
    await page.goto("/register");
    await page.getByLabel(/^Email/).fill(email);
    await page.getByLabel(/^Password/).fill(PASSWORD);
    await page.getByLabel(/^Confirm password/).fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();

    // Registration returns tokens directly, so a new user lands in the app
    // rather than back at a login form.
    await expect(page).toHaveURL(/\/app/, { timeout: 30_000 });
  });

  await test.step("creates a portfolio", async () => {
    await page.goto("/app/portfolios");
    // A brand-new account has an empty list, which invites the first one.
    await page.getByRole("button", { name: /create your first portfolio/i }).click();

    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/^Name/).fill("Journey portfolio");
    await dialog.getByLabel(/^Benchmark symbol/).fill("SPY");
    await dialog.getByRole("button", { name: "Create portfolio" }).click();

    await expect(page.getByRole("heading", { name: "Journey portfolio" })).toBeVisible({
      timeout: 30_000,
    });
  });

  await test.step("adds holdings", async () => {
    await tab(page, "Holdings").click();

    for (const [symbol, quantity, cost] of [
      ["AAPL", "20", "150.25"],
      ["SPY", "10", "300.00"],
    ]) {
      // Two of these while the table is empty: the toolbar action and the
      // empty state's invitation. Either opens the same dialog.
      await page.getByRole("button", { name: "Add holding" }).first().click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel(/^Symbol/).fill(symbol as string);
      await dialog.getByLabel(/^Quantity/).fill(quantity as string);
      await dialog.getByLabel(/^Average cost/).fill(cost as string);
      await dialog.getByRole("button", { name: "Add holding" }).click();
      await expect(dialog).toBeHidden({ timeout: 30_000 });
    }

    // The symbol is the row's header, not a plain cell: it is what names the
    // row, and a screen reader repeats it for every figure in it.
    await expect(page.getByRole("rowheader", { name: /AAPL/ })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: /SPY/ })).toBeVisible();
  });

  await test.step("fetches prices, and says when they are from", async () => {
    await page.getByRole("button", { name: /refresh prices/i }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/^From/).fill(WINDOW.start);
    await dialog.getByLabel(/^To/).fill(WINDOW.end);
    await dialog.getByRole("button", { name: "Fetch prices" }).click();
    await expect(dialog.getByText(/price bars written|already up to date/i)).toBeVisible({
      timeout: 120_000,
    });
    // The dialog has a corner dismiss and a footer button, both named Close.
    await dialog.getByRole("button", { name: "Close" }).last().click();

    // The as-of date is always on screen; a figure from 2023 on a 2026 screen
    // must never be presented as current.
    await expect(page.getByText(/prices as of/i).first()).toBeVisible({ timeout: 60_000 });
  });

  await test.step("runs an analysis and reads the metrics", async () => {
    await tab(page, "Analytics").click();
    await page.getByRole("button", { name: /choose a window/i }).click();
    await page.getByLabel("Window start").fill(WINDOW.start);
    await page.getByLabel("Window end").fill(WINDOW.end);
    await page.getByRole("button", { name: /run analysis/i }).click();

    // Both volatilities, each labelled with its own basis: the rule that daily
    // and annualized figures can never be confused.
    await expect(page.getByText("Volatility (annualized)").first()).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByText("Volatility (daily)").first()).toBeVisible();

    // Value at Risk always carries its caveat.
    await expect(page.getByText(/not a maximum possible loss/i).first()).toBeVisible();

    // And every chart offers the numbers behind it.
    const valueChart = page.locator("figure", { hasText: "Portfolio value over time" });
    await valueChart.getByRole("button", { name: "View as table" }).click();
    await expect(valueChart.getByRole("table")).toBeVisible();
  });

  await test.step("stress tests it, and sees the assumptions first", async () => {
    await tab(page, "Stress test").click();

    await expect(page.getByText(/an estimate of sensitivity, not a forecast/i)).toBeVisible();

    // Chosen rather than left on the first entry: the committed fixtures do not
    // reach back to 2008, so the catalogue's oldest scenario has no prices for
    // these holdings and would correctly refuse to run.
    await page
      .getByLabel("Scenario", { exact: true })
      .selectOption({ label: "COVID-19 crash" });
    await page.getByRole("button", { name: /run this scenario/i }).click();

    await expect(page.getByText("Estimated impact", { exact: false }).first()).toBeVisible({
      timeout: 90_000,
    });
    await expect(page.getByText(/every holding the scenario covers/i)).toBeVisible();
  });

  await test.step("sees its early warnings in plain language", async () => {
    await tab(page, "Signals").click();
    await page.getByRole("button", { name: /add any missing rules/i }).click();
    await page.getByRole("button", { name: /run monitoring now/i }).click();

    await expect(page.getByText(/rules evaluated/i).first()).toBeVisible({ timeout: 90_000 });
    // Never framed as a forecast, on any screen.
    await expect(
      page.getByText(/none of them is a prediction, and none of them is advice/i),
    ).toBeVisible();
  });

  await test.step("generates a report", async () => {
    await tab(page, "Reports").click();
    await page.getByRole("button", { name: /generate report/i }).click();

    await expect(page.getByText("READY", { exact: false }).first()).toBeVisible({
      timeout: 120_000,
    });

    // The download is an authenticated fetch, not a public link.
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: /^download/i }).click();
    expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  });

  await test.step("signs out, and the session does not survive it", async () => {
    await page
      .getByRole("button", { name: new RegExp(email.split("@")[0] ?? "", "i") })
      .click();
    await page.getByRole("menuitem", { name: /sign out/i }).click();

    await expect(page).toHaveURL(/\/login/, { timeout: 30_000 });

    // A deep link now returns to sign-in carrying where the visitor was going.
    await page.goto("/app/portfolios");
    await expect(page).toHaveURL(/\/login\?next=/, { timeout: 30_000 });
  });
});

test("a deep link into the application is never met by the splash gate", async ({ page }) => {
  // The gate belongs to the front door. Someone following a link to a specific
  // page should land on it, not on a plate they have to dismiss first.
  await page.goto("/methodology");

  await expect(
    page.getByRole("heading", { name: /how the numbers are produced/i }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /slide up to enter/i })).toBeHidden();
});
