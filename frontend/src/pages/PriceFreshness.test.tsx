import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { analysisRun, result, RUN_ID, runSummary } from "@/test/analytics";
import { API, signedInHandlers } from "@/test/handlers";
import { PORTFOLIO_ID, scenarioCatalogue } from "@/test/phase11";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const portfolio = {
  id: PORTFOLIO_ID,
  name: "Core portfolio",
  description: null,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  position_count: 2,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const FETCHED = "2026-02-01T10:15:42Z";

const holding = (symbol: string, fetchedAt: string | null) => ({
  symbol,
  name: symbol,
  sector: "Technology",
  quantity: "10",
  average_cost: "100.00",
  cost_basis: "1000.00",
  latest_price: "120.00",
  latest_price_date: "2026-01-30",
  latest_price_fetched_at: fetchedAt,
  market_value: "1200.00",
  weight: 0.5,
  unrealized_profit_loss: "200.00",
});

const summary = {
  portfolio_id: PORTFOLIO_ID,
  name: portfolio.name,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  data_as_of: "2026-01-30",
  prices_fetched_at: FETCHED,
  holdings_count: 2,
  priced_holdings_count: 2,
  unpriced_symbols: [],
  total_market_value: "2400.00",
  total_cost_basis: "2000.00",
  unrealized_profit_loss: "400.00",
  unrealized_profit_loss_percent: 0.2,
  largest_position_weight: 0.5,
  sector_weights: { Technology: 1 },
  unknown_sector_weight: 0,
  holdings: [holding("AAPL", FETCHED), holding("MSFT", "2026-02-01T10:15:44Z")],
  disclaimer: "Educational tool.",
};

const position = (id: string, symbol: string) => ({
  id,
  portfolio_id: PORTFOLIO_ID,
  asset: {
    id: `asset-${symbol}`,
    symbol,
    name: symbol,
    asset_type: "equity" as const,
    exchange: "NASDAQ",
    currency: "USD",
    sector: "Technology",
    industry: null,
  },
  quantity: "10",
  average_cost: "100.00",
  cost_basis: "1000.00",
  currency: "USD",
  purchase_date: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

/** Every refresh request the page makes, in order. */
let refreshes: URLSearchParams[] = [];

const refreshed = {
  portfolio_id: PORTFOLIO_ID,
  data_as_of: "2026-01-30",
  source: "yahoo",
  requested_start: "2026-01-25",
  requested_end: "2026-02-01",
  fetched_at: FETCHED,
  assets_refreshed: 2,
  bars_written: 2,
  results: [],
  failures: [],
};

beforeEach(() => {
  refreshes = [];
  server.use(
    ...signedInHandlers,
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/positions`, () =>
      HttpResponse.json([position("pos-1", "AAPL"), position("pos-2", "MSFT")]),
    ),
    http.post(`${API}/portfolios/${PORTFOLIO_ID}/market-data/refresh`, ({ request }) => {
      refreshes.push(new URL(request.url).searchParams);
      return HttpResponse.json(refreshed);
    }),
  );
});

describe("price freshness", () => {
  it("reads the newest prices when the page opens, without being asked", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    // A live provider revises today's bar all session. A page that waited for a
    // button would be presenting this morning's price as current.
    await waitFor(() => expect(refreshes).toHaveLength(1));
    expect(refreshes[0]?.get("quick")).toBe("true");
  });

  it("does not refresh twice for one page load", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    await screen.findByText(/prices fetched/i);
    // The refresh invalidates the summary, which re-renders the control. That
    // re-render must not be mistaken for another page load.
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(refreshes).toHaveLength(1);
  });

  it("refreshes every holding from one button, with no dialog", async () => {
    const { user } = renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    await screen.findByText(/prices fetched/i);
    await user.click(screen.getByRole("button", { name: "Refresh now" }));

    await waitFor(() => expect(refreshes).toHaveLength(2));
    expect(refreshes[1]?.get("quick")).toBe("true");
    // One click is the whole interaction: no window to choose, nothing to confirm.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("says when the prices were fetched, to the second", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    const status = await screen.findByText(/prices fetched/i);
    // "10:15" could be fifty-nine seconds old or one.
    expect(status.textContent).toMatch(/\d{1,2}:\d{2}:42/);
  });

  it("shows when each holding's own price was fetched", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/holdings` });

    const apple = await screen.findByRole("rowheader", { name: /AAPL/ });
    const microsoft = screen.getByRole("rowheader", { name: /MSFT/ });

    // Two holdings fetched two seconds apart read differently, which is the
    // whole reason for showing seconds.
    expect(within(apple.closest("tr") as HTMLElement).getByText(/fetched/).textContent).toMatch(
      /:42/,
    );
    expect(
      within(microsoft.closest("tr") as HTMLElement).getByText(/fetched/).textContent,
    ).toMatch(/:44/);
  });

  it("keeps the last prices on screen and says so when a refresh fails", async () => {
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/market-data/refresh`, () =>
        HttpResponse.json(
          {
            error: {
              code: "market_data_unavailable",
              message: "The market-data provider could not be reached.",
              details: null,
              request_id: "test",
            },
          },
          { status: 503 },
        ),
      ),
    );
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    expect(await screen.findByText(/prices could not be refreshed/i)).toBeInTheDocument();
    // The figures stay, and are described as what they are: the last good fetch.
    expect(screen.getByText(/from the last successful fetch/i)).toBeInTheDocument();
    expect(screen.getByText("$2,400.00")).toBeInTheDocument();
  });

  it("names the holdings a refresh could not reach", async () => {
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/market-data/refresh`, () =>
        HttpResponse.json({
          ...refreshed,
          failures: [{ symbol: "MSFT", message: "Yahoo Finance did not respond in time." }],
        }),
      ),
    );
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    expect(await screen.findByText(/not refreshed: MSFT/i)).toBeInTheDocument();
  });
});

describe("missing prices are flagged before anything is drawn", () => {
  const uncovered = {
    portfolio_id: PORTFOLIO_ID,
    start: "2020-02-19",
    end: "2020-03-23",
    source: "yahoo",
    complete: false,
    holdings: [
      {
        symbol: "AAPL",
        status: "full",
        first_date: "2020-02-19",
        last_date: "2020-03-23",
        observations: 24,
        expected_observations: 24,
        message: null,
      },
      {
        symbol: "MSFT",
        status: "none",
        first_date: null,
        last_date: null,
        observations: 0,
        expected_observations: 24,
        message: "No prices are stored for MSFT in this period.",
      },
    ],
  };

  it("warns on the stress screen before a historical scenario is run", async () => {
    server.use(
      http.get(`${API}/stress-scenarios`, () => HttpResponse.json(scenarioCatalogue)),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/stress-tests`, () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/market-data/coverage`, () =>
        HttpResponse.json(uncovered),
      ),
    );
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/stress` });

    // Nothing has been run. The warning is there anyway, which is the point: a
    // scenario over this window would chart AAPL alone and look complete.
    const warning = await screen.findByText(/some holdings have no prices for this period/i);
    const alert = warning.closest("[role='alert']") as HTMLElement;
    expect(alert).toHaveTextContent("MSFT");
    expect(alert).toHaveTextContent(/no prices stored in this period/i);
    expect(alert).not.toHaveTextContent("AAPL");
    expect(
      within(alert).getByRole("button", { name: /fetch prices for this period/i }),
    ).toBeInTheDocument();
  });

  it("fetches exactly the missing window when asked", async () => {
    server.use(
      http.get(`${API}/stress-scenarios`, () => HttpResponse.json(scenarioCatalogue)),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/stress-tests`, () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/market-data/coverage`, () =>
        HttpResponse.json(uncovered),
      ),
    );
    const { user } = renderApp(<AppRoutes />, {
      route: `/app/portfolios/${PORTFOLIO_ID}/stress`,
    });

    await user.click(
      await screen.findByRole("button", { name: /fetch prices for this period/i }),
    );

    await waitFor(() =>
      expect(refreshes.some((params) => params.get("start") === "2020-02-19")).toBe(true),
    );
    const request = refreshes.find((params) => params.get("start") === "2020-02-19");
    expect(request?.get("end")).toBe("2020-03-23");
  });

  it("warns in the analysis parameters for the window being chosen", async () => {
    server.use(
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/analysis-runs`, () =>
        HttpResponse.json({ items: [runSummary()], total: 1, limit: 20, offset: 0 }),
      ),
      http.get(`${API}/analysis-runs/${RUN_ID}`, () => HttpResponse.json(analysisRun())),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/market-data/coverage`, () =>
        HttpResponse.json({
          ...uncovered,
          start: "2022-01-03",
          end: "2023-12-29",
          holdings: uncovered.holdings.map((item) =>
            item.symbol === "MSFT"
              ? {
                  ...item,
                  status: "partial",
                  first_date: "2023-06-01",
                  last_date: "2023-12-29",
                  observations: 150,
                }
              : item,
          ),
        }),
      ),
    );
    const { user } = renderApp(<AppRoutes />, {
      route: `/app/portfolios/${PORTFOLIO_ID}/analytics`,
    });

    await user.click(await screen.findByRole("button", { name: "New analysis" }));

    const warning = await screen.findByText(/some holdings have no prices for this period/i);
    // A holding whose prices start late is said to start late, with the dates.
    expect(warning.closest("[role='alert']")).toHaveTextContent(/prices only from Jun 1, 2023/);
    // An analysis fetches its own window, so there is nothing to press first.
    const notice = warning.closest("[role='alert']") as HTMLElement;
    expect(notice).toHaveTextContent(/running the analysis fetches them first/i);
    expect(
      within(notice).queryByRole("button", { name: /fetch prices for this period/i }),
    ).not.toBeInTheDocument();
  });

  it("says nothing when every holding is covered", async () => {
    server.use(
      http.get(`${API}/stress-scenarios`, () => HttpResponse.json(scenarioCatalogue)),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/stress-tests`, () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    );
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/stress` });

    await screen.findByRole("button", { name: /run this scenario/i });
    expect(screen.queryByText(/no prices for this period/i)).not.toBeInTheDocument();
  });
});

describe("the added measures", () => {
  const withExtras = () =>
    analysisRun({
      results: [
        ...analysisRun().results.filter((item) => item.metric !== "benchmark_beta"),
        result("sortino_ratio", "0.7134", "ratio", { annual_risk_free_rate: 0.045 }),
        result("downside_deviation", "0.0981", "ratio", { annualized: true }),
        result("calmar_ratio", "0.9826", "ratio"),
        result("skewness", "-0.3712", "ratio"),
        result("excess_kurtosis", "2.4410", "ratio"),
        result("worst_period_return", "-0.0431", "ratio", { date: "2022-06-13" }),
        result("treynor_ratio", "0.0841", "ratio", { benchmark_symbol: "SPY" }),
        result("upside_capture", "1.1200", "ratio", { benchmark_symbol: "SPY" }),
        result("benchmark_beta", "0.8742", "ratio", {
          benchmark_symbol: "SPY",
          assets: [
            { symbol: "AAPL", beta: 1.21, weight: 0.6 },
            { symbol: "TLT", beta: -0.24, weight: 0.4 },
          ],
        }),
      ],
    });

  beforeEach(() => {
    server.use(
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/analysis-runs`, () =>
        HttpResponse.json({ items: [runSummary()], total: 1, limit: 20, offset: 0 }),
      ),
      http.get(`${API}/analysis-runs/${RUN_ID}`, () => HttpResponse.json(withExtras())),
    );
  });

  it("shows a ratio as a number and a deviation as a percentage", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/analytics` });

    expect(await screen.findByText("Sortino ratio (annualized)")).toBeInTheDocument();
    // A Sortino of 0.71 is not 71%; a downside deviation of 0.0981 is 9.81%.
    expect(screen.getByText("0.71")).toBeInTheDocument();
    expect(screen.getByText("9.81%")).toBeInTheDocument();
    expect(screen.getByText("Excess kurtosis (period)")).toBeInTheDocument();
  });

  it("dates the largest single loss", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/analytics` });

    const label = await screen.findByText("Largest single loss (period)");
    const tile = label.closest(".hm-panel") as HTMLElement;
    expect(tile).toHaveTextContent("-4.31%");
    expect(tile).toHaveTextContent("On Jun 13, 2022");
  });

  it("breaks beta down by holding", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/analytics` });

    const heading = await screen.findByRole("heading", { name: "Beta by holding" });
    const figure = heading.closest("figure") as HTMLElement;
    expect(figure).toHaveTextContent("AAPL");
    expect(figure).toHaveTextContent("1.21");
    // A negative beta reads as negative, not as a short bar.
    expect(figure).toHaveTextContent("-0.24");
  });

  it("explains the absence of beta when the run had no benchmark", async () => {
    server.use(
      http.get(`${API}/analysis-runs/${RUN_ID}`, () =>
        HttpResponse.json(
          analysisRun({
            results: analysisRun().results.filter(
              (item) =>
                !item.metric.startsWith("benchmark_") &&
                !["tracking_error", "information_ratio"].includes(item.metric),
            ),
          }),
        ),
      ),
    );
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/analytics` });

    // An absent section reads as "this tool has no beta" unless it says why.
    expect(await screen.findByText(/this run had none/i)).toBeInTheDocument();
    expect(screen.queryByText("Beta (period)")).not.toBeInTheDocument();
  });
});
