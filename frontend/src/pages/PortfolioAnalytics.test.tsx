import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { analysisRun, OLDER_RUN_ID, RUN_ID, runSummary, valuePoints } from "@/test/analytics";
import { API, signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const PORTFOLIO_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
const ROUTE = `/app/portfolios/${PORTFOLIO_ID}/analytics`;

const portfolio = {
  id: PORTFOLIO_ID,
  name: "Core portfolio",
  description: null,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  position_count: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const summary = {
  portfolio_id: PORTFOLIO_ID,
  name: portfolio.name,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  data_as_of: "2023-12-29",
  holdings_count: 3,
  priced_holdings_count: 2,
  unpriced_symbols: ["TLT"],
  total_market_value: "12480.55",
  total_cost_basis: "10000.00",
  unrealized_profit_loss: "2480.55",
  unrealized_profit_loss_percent: 0.2481,
  largest_position_weight: 0.5241,
  sector_weights: { Technology: 0.5241, "Broad market": 0.3012 },
  unknown_sector_weight: 0,
  holdings: [
    {
      symbol: "AAPL",
      name: "Apple Inc.",
      sector: "Technology",
      quantity: "20",
      average_cost: "150.25",
      cost_basis: "3005.00",
      latest_price: "327.03",
      latest_price_date: "2023-12-29",
      market_value: "6540.60",
      weight: 0.5241,
      unrealized_profit_loss: "3535.60",
    },
    {
      symbol: "SPY",
      name: "SPDR S&P 500 ETF",
      sector: "Broad market",
      quantity: "10",
      average_cost: "300.00",
      cost_basis: "3000.00",
      latest_price: "375.90",
      latest_price_date: "2023-12-29",
      market_value: "3759.00",
      weight: 0.3012,
      unrealized_profit_loss: "759.00",
    },
    {
      // No stored price: it must still appear, with its reason, never as zero.
      symbol: "TLT",
      name: "iShares 20+ Year Treasury",
      sector: "Bonds",
      quantity: "15",
      average_cost: "100.00",
      cost_basis: "1500.00",
      latest_price: null,
      latest_price_date: null,
      market_value: null,
      weight: null,
      unrealized_profit_loss: null,
    },
  ],
  disclaimer: "Educational tool.",
};

function baseHandlers(runs = [runSummary()]) {
  return [
    ...signedInHandlers,
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/analysis-runs`, () =>
      HttpResponse.json({ items: runs, total: runs.length, limit: 20, offset: 0 }),
    ),
  ];
}

beforeEach(() => {
  server.use(...baseHandlers());
  server.use(
    http.get(`${API}/analysis-runs/${RUN_ID}`, () => HttpResponse.json(analysisRun())),
  );
});

/** The dashboard has loaded when the run's own window is on screen. */
async function waitForDashboard() {
  await screen.findByText("2022-01-03 → 2023-12-29");
}

describe("the analytics dashboard", () => {
  it("shows the newest stored run", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    // A figure from the run, formatted as the portfolio's own currency. The
    // portfolio header above the tabs shows the same amount, hence "all".
    expect(screen.getAllByText("$12,480.55").length).toBeGreaterThan(0);
    expect(screen.getByText("Sharpe ratio (annualized)")).toBeInTheDocument();
  });

  it("never renders a daily figure the same way as an annualized one", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    // Both volatilities are present, and neither label is bare: a reader cannot
    // mistake 0.94% a day for 14.92% a year.
    expect(screen.getByText("Volatility (daily)")).toBeInTheDocument();
    expect(screen.getByText("Volatility (annualized)")).toBeInTheDocument();
    expect(screen.getByText("0.94%")).toBeInTheDocument();
    expect(screen.getByText("14.92%")).toBeInTheDocument();
  });

  it("keeps the Value-at-Risk caveat beside the number", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    const tiles = screen.getAllByText(/not a maximum possible loss/i);
    // Historical VaR, parametric VaR and expected shortfall all carry it.
    expect(tiles).toHaveLength(3);
    expect(tiles[0]).toHaveTextContent("95% confidence");
  });

  it("shows why a metric is unavailable instead of showing a zero", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    // Twice over: once in the partial-run summary at the top of the screen, once
    // on the tile itself.
    const reasons = screen.getAllByText(/tracking error is zero, so an information ratio/i);
    const tile = reasons[reasons.length - 1]?.closest(".hm-panel") ?? null;
    expect(tile).not.toBeNull();
    // The unavailable tile must not present any number at all.
    expect(tile?.textContent).not.toMatch(/\d\.\d\d/);
  });

  it("states the fixed-weight reconstruction rather than paraphrasing it away", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    // In the run's own assumptions, and again on the charts it applies to.
    expect(
      screen.getAllByText(/applying today's weights to each asset's historical returns/i)
        .length,
    ).toBeGreaterThan(0);
  });

  it("shows a partial run's results and lists what failed above them", async () => {
    server.use(
      http.get(`${API}/analysis-runs/${RUN_ID}`, () =>
        HttpResponse.json(analysisRun({ status: "partial" })),
      ),
    );
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/some metrics could not be computed/i);
    expect(alert).toHaveTextContent(/information ratio/i);
    // A partial run is not an error page: the metrics that did compute are here.
    expect(screen.getByText("14.92%")).toBeInTheDocument();
  });

  it("keeps a failed run's parameters so it can be tried again", async () => {
    server.use(
      http.get(`${API}/analysis-runs/${RUN_ID}`, () =>
        HttpResponse.json(
          analysisRun({
            status: "failed",
            error_message: "No price history is stored for this window.",
            results: [],
          }),
        ),
      ),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No price history is stored for this window.");

    await user.click(screen.getByRole("button", { name: /review the parameters/i }));

    // The window, confidence and rate the run used, not the form's defaults.
    expect(await screen.findByLabelText("Window start")).toHaveValue("2022-01-03");
    expect(screen.getByLabelText("Window end")).toHaveValue("2023-12-29");
    expect(screen.getByLabelText("Confidence")).toHaveValue("0.95");
    expect(screen.getByLabelText("Risk-free rate")).toHaveValue("4.5");
  });

  it("runs a new analysis with the parameters on screen", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/analysis-runs`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(analysisRun({ id: OLDER_RUN_ID }), { status: 201 });
      }),
      http.get(`${API}/analysis-runs/${OLDER_RUN_ID}`, () =>
        HttpResponse.json(analysisRun({ id: OLDER_RUN_ID })),
      ),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    await user.click(screen.getByRole("button", { name: "New analysis" }));
    await user.selectOptions(await screen.findByLabelText("Confidence"), "0.99");
    await user.click(screen.getByRole("button", { name: "Run analysis" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      start: "2022-01-03",
      end: "2023-12-29",
      confidence: 0.99,
      var_method: "historical",
      frequency: "daily",
      annual_risk_free_rate: 0.045,
    });
  });

  it("invites a first analysis when the portfolio has never been analysed", async () => {
    server.use(...baseHandlers([]));
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText("No analysis yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /choose a window/i }));
    expect(await screen.findByLabelText("Window start")).toBeInTheDocument();
  });

  it("carries the disclaimer exactly once", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    // The shell's footer carries it on every screen. Repeating it on the
    // dashboard would make it furniture, which is how a disclaimer stops being
    // read at all. DESIGN.md section 6.7.
    expect(screen.getAllByText(/educational portfolio-analysis tool/i)).toHaveLength(1);
  });
});

describe("the dashboard charts", () => {
  it("titles every chart and states its units", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    for (const [title, units] of [
      ["Portfolio value over time", /reconstructed value in USD/i],
      ["Portfolio versus benchmark", /indexed to 100/i],
      ["Drawdown", /percent below the running peak/i],
      ["Rolling volatility", /annualized volatility of the 20 periods/i],
      ["Allocation by holding", /share of priced portfolio value/i],
      ["Correlation between holdings", /correlation coefficient/i],
      ["Risk contribution by holding", /share of portfolio volatility/i],
    ] as const) {
      const heading = screen.getByRole("heading", { name: title });
      const figure = heading.closest("figure");
      expect(figure, `${title} is missing its frame`).not.toBeNull();
      expect(figure).toHaveTextContent(units);
    }
  });

  it("exposes the same numbers as a table", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    const figure = screen
      .getByRole("heading", { name: "Portfolio value over time" })
      .closest("figure");
    expect(figure).not.toBeNull();
    const frame = within(figure as HTMLElement);

    await user.click(frame.getByRole("button", { name: "View as table" }));

    const table = frame.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Date" })).toBeInTheDocument();
    expect(
      within(table).getByRole("columnheader", { name: /value \(USD\)/i }),
    ).toBeInTheDocument();
    // Every point the chart drew, and the first of them by date.
    const points = valuePoints();
    expect(table).toHaveTextContent("Jan 3, 2022");
    // A header row plus one row per point.
    expect(within(table).getAllByRole("row")).toHaveLength(points.length + 1);
  });

  it("gives the correlation matrix real row and column headers", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    const figure = screen
      .getByRole("heading", { name: "Correlation between holdings" })
      .closest("figure");
    const matrix = within(figure as HTMLElement).getByRole("table");

    expect(within(matrix).getByRole("columnheader", { name: "AAPL" })).toBeInTheDocument();
    expect(within(matrix).getByRole("rowheader", { name: "TLT" })).toBeInTheDocument();
    // A negative correlation reads as a negative number, not only as a colour.
    expect(matrix).toHaveTextContent("-0.31");
  });

  it("keeps an unpriced holding visible in the allocation chart", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    const figure = screen
      .getByRole("heading", { name: "Allocation by holding" })
      .closest("figure");
    const frame = within(figure as HTMLElement);

    expect(frame.getByText("TLT")).toBeInTheDocument();
    expect(frame.getByText(/no price available/i)).toBeInTheDocument();
  });

  it("says what it cannot draw instead of drawing an empty axis", async () => {
    server.use(
      http.get(`${API}/analysis-runs/${RUN_ID}`, () =>
        HttpResponse.json(
          analysisRun({
            status: "partial",
            results: analysisRun()
              .results.filter((item) => item.metric !== "rolling_volatility")
              .concat([
                {
                  metric: "rolling_volatility",
                  value: null,
                  unit: "ratio",
                  metadata: { window: 20 },
                  unavailable_reason:
                    "Rolling volatility needs at least 20 observations; 12 are available.",
                },
              ]),
          }),
        ),
      ),
    );
    renderApp(<AppRoutes />, { route: ROUTE });

    await waitForDashboard();
    const figure = screen
      .getByRole("heading", { name: "Rolling volatility" })
      .closest("figure");
    expect(figure).toHaveTextContent(/needs at least 20 observations; 12 are available/i);
    // Nothing offers a table of numbers that do not exist.
    expect(
      within(figure as HTMLElement).queryByRole("button", { name: "View as table" }),
    ).not.toBeInTheDocument();
  });
});
