import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { API, signedInHandlers } from "@/test/handlers";
import {
  alertRule,
  monitoringRun,
  PORTFOLIO_ID,
  ruleCatalogue,
  signal,
  signalSummary,
} from "@/test/phase11";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const HOLDINGS = `/app/portfolios/${PORTFOLIO_ID}/holdings`;
const SIGNALS = `/app/portfolios/${PORTFOLIO_ID}/signals`;

const portfolio = {
  id: PORTFOLIO_ID,
  name: "Core portfolio",
  description: null,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  position_count: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const summary = {
  portfolio_id: PORTFOLIO_ID,
  name: portfolio.name,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  data_as_of: "2026-01-30",
  prices_fetched_at: "2026-02-01T10:15:42Z",
  holdings_count: 1,
  priced_holdings_count: 1,
  unpriced_symbols: [],
  total_market_value: "2400.00",
  total_cost_basis: "2000.00",
  unrealized_profit_loss: "400.00",
  unrealized_profit_loss_percent: 0.2,
  largest_position_weight: 1,
  sector_weights: { Technology: 1 },
  unknown_sector_weight: 0,
  holdings: [],
  disclaimer: "Educational tool.",
};

const refreshed = {
  portfolio_id: PORTFOLIO_ID,
  data_as_of: "2026-01-30",
  source: "yahoo",
  requested_start: "2026-01-25",
  requested_end: "2026-02-01",
  fetched_at: "2026-02-01T10:15:42Z",
  assets_refreshed: 1,
  bars_written: 1,
  results: [],
  failures: [],
  monitoring: {
    run_id: "12121212-8888-4888-8888-121212121212",
    status: "succeeded",
    checked_at: "2026-02-01T10:15:43Z",
    rules_evaluated: 9,
    rules_failed: 0,
    signals_created: 0,
    signals_updated: 1,
    signals_resolved: 0,
  },
};

const existing = signal();
const arrived = signal({
  id: "99999999-9999-4999-8999-999999999999",
  severity: "critical",
  severity_icon: "alert-octagon",
  title: "Stress-test loss above threshold",
  signal_type: "stress_loss",
});

/** Every refresh the page makes, and what the signals endpoint answers with. */
let refreshes: URLSearchParams[] = [];
let active = [existing];

beforeEach(() => {
  refreshes = [];
  active = [existing];
  server.use(
    ...signedInHandlers,
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/positions`, () => HttpResponse.json([])),
    http.post(`${API}/portfolios/${PORTFOLIO_ID}/market-data/refresh`, ({ request }) => {
      refreshes.push(new URL(request.url).searchParams);
      return HttpResponse.json(refreshed);
    }),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/signals/summary`, () =>
      HttpResponse.json(
        signalSummary({
          total_open: active.length,
          by_severity: {
            informational: 0,
            elevated: 0,
            high: 1,
            critical: active.length - 1,
          },
        }),
      ),
    ),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/signals`, () =>
      HttpResponse.json({ items: active, total: active.length, limit: 50, offset: 0 }),
    ),
    http.get(`${API}/alert-rule-types`, () => HttpResponse.json(ruleCatalogue)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/alert-rules`, () =>
      HttpResponse.json([alertRule()]),
    ),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/monitoring-runs`, () =>
      HttpResponse.json({
        items: [
          monitoringRun({
            trigger_type: "market_data_refresh",
            started_at: "2026-02-01T10:15:42Z",
            completed_at: "2026-02-01T10:15:43Z",
          }),
        ],
        total: 1,
        limit: 10,
        offset: 0,
      }),
    ),
  );
});

function tab(name: RegExp) {
  return within(screen.getByRole("navigation", { name: "Portfolio sections" })).getByRole(
    "link",
    { name },
  );
}

describe("live signals", () => {
  it("evaluates the rules against the prices read when the page opens", async () => {
    renderApp(<AppRoutes />, { route: HOLDINGS });

    await waitFor(() => expect(refreshes).toHaveLength(1));
    // A warning computed from older prices than the ones on screen would
    // describe a portfolio the reader is no longer looking at.
    expect(refreshes[0]?.get("monitor")).toBe("true");
    expect(refreshes[0]?.get("quick")).toBe("true");
  });

  it("checks again from the refresh button", async () => {
    const { user } = renderApp(<AppRoutes />, { route: HOLDINGS });

    await screen.findByText(/prices fetched/i);
    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => expect(refreshes).toHaveLength(2));
    expect(refreshes[1]?.get("monitor")).toBe("true");
  });

  it("counts the open signals on the tab that leads to them", async () => {
    renderApp(<AppRoutes />, { route: HOLDINGS });

    // Visible from every tab, so a reader on the holdings table still knows.
    expect(await screen.findByRole("link", { name: /signals\s*1 open/i })).toBeInTheDocument();
  });

  it("shows no count when nothing is open", async () => {
    active = [];
    renderApp(<AppRoutes />, { route: HOLDINGS });

    await screen.findByText(/prices fetched/i);
    expect(tab(/^signals$/i)).toBeInTheDocument();
  });

  it("says nothing about a signal that was already there", async () => {
    renderApp(<AppRoutes />, { route: HOLDINGS });

    await screen.findByRole("link", { name: /signals\s*1 open/i });
    // Already open when the page loaded, and already counted on the tab.
    expect(screen.queryByText(/new gjallarhorn signal/i)).not.toBeInTheDocument();
  });

  it("announces a signal that appears while the portfolio is open", async () => {
    const { user } = renderApp(<AppRoutes />, { route: HOLDINGS });
    await screen.findByRole("link", { name: /signals\s*1 open/i });

    active = [existing, arrived];
    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    const heading = await screen.findByText("New Gjallarhorn signal");
    const notice = heading.closest("[role='status']") as HTMLElement;
    expect(notice).toHaveTextContent("Stress-test loss above threshold");
    // Severity as a word, not only a colour.
    expect(notice).toHaveTextContent("Critical");
    // Polite: it describes an observed condition, not an emergency.
    expect(notice).toHaveAttribute("aria-live", "polite");
    expect(notice).toHaveTextContent(/not a prediction/i);
    // And the count moves with it.
    expect(await screen.findByRole("link", { name: /signals\s*2 open/i })).toBeInTheDocument();
  });

  it("keeps the notice until it is dismissed", async () => {
    const { user } = renderApp(<AppRoutes />, { route: HOLDINGS });
    await screen.findByRole("link", { name: /signals\s*1 open/i });
    active = [existing, arrived];
    await user.click(screen.getByRole("button", { name: "Refresh now" }));
    const heading = await screen.findByText("New Gjallarhorn signal");

    // A notice that removed itself is one a reader who looked away never saw.
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(heading).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() =>
      expect(screen.queryByText("New Gjallarhorn signal")).not.toBeInTheDocument(),
    );
  });

  it("leads from the notice to the signals", async () => {
    const { user } = renderApp(<AppRoutes />, { route: HOLDINGS });
    await screen.findByRole("link", { name: /signals\s*1 open/i });
    active = [existing, arrived];
    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    await user.click(await screen.findByRole("link", { name: "View signal" }));

    expect(await screen.findByRole("heading", { name: /gjallarhorn signals/i })).toBeVisible();
    expect(screen.queryByText("New Gjallarhorn signal")).not.toBeInTheDocument();
  });

  it("says when the rules were last checked, to the second", async () => {
    renderApp(<AppRoutes />, { route: SIGNALS });

    const status = await screen.findByText(/last checked/i);
    expect(status.textContent).toMatch(/\d{1,2}:\d{2}:43/);
    expect(status).toHaveTextContent("9 rules evaluated");
  });

  it("says what makes a check happen, and how fresh the quotes are", async () => {
    renderApp(<AppRoutes />, { route: SIGNALS });

    expect(await screen.findByText(/every five minutes while it stays open/i)).toBeVisible();
    expect(screen.getByText(/trail the exchange by about fifteen minutes/i)).toBeVisible();
  });

  it("names what started each check in the history", async () => {
    renderApp(<AppRoutes />, { route: SIGNALS });

    const history = (await screen.findByRole("heading", { name: "Monitoring history" }))
      .parentElement as HTMLElement;
    expect(within(history).getByText("After a price refresh")).toBeInTheDocument();
  });
});
