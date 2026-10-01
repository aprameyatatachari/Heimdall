import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { API, errorBody, signedInHandlers } from "@/test/handlers";
import { PORTFOLIO_ID, scenarioCatalogue, stressRun, STRESS_RUN_ID } from "@/test/phase11";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const ROUTE = `/app/portfolios/${PORTFOLIO_ID}/stress`;

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
  holdings_count: 2,
  priced_holdings_count: 2,
  unpriced_symbols: [],
  total_market_value: "10299.60",
  total_cost_basis: "8000.00",
  unrealized_profit_loss: "2299.60",
  unrealized_profit_loss_percent: 0.2875,
  largest_position_weight: 0.635,
  sector_weights: { Technology: 0.635, Energy: 0.365 },
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
      weight: 0.635,
      unrealized_profit_loss: "3535.60",
    },
    {
      symbol: "XOM",
      name: "Exxon Mobil",
      sector: "Energy",
      quantity: "50",
      average_cost: "80.00",
      cost_basis: "4000.00",
      latest_price: "75.18",
      latest_price_date: "2023-12-29",
      market_value: "3759.00",
      weight: 0.365,
      unrealized_profit_loss: "-241.00",
    },
  ],
  disclaimer: "Educational tool.",
};

function handlers(runs: unknown[] = []) {
  return [
    ...signedInHandlers,
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/stress-scenarios`, () => HttpResponse.json(scenarioCatalogue)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/stress-tests`, () =>
      HttpResponse.json({ items: runs, total: runs.length, limit: 20, offset: 0 }),
    ),
  ];
}

beforeEach(() => {
  server.use(...handlers());
});

describe("before a scenario runs", () => {
  it("shows what a historical scenario replays, and over what window", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText(/replays the returns observed/i)).toBeInTheDocument();
    // The catalogue's own `window` field is the same two dates unformatted, so
    // the screen shows the formatted pair rather than saying it twice.
    expect(screen.getByText("Feb 19, 2020 → Mar 23, 2020")).toBeInTheDocument();
  });

  it("states what a stress test cannot tell you before it is run", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(
      await screen.findByText(/an estimate of sensitivity, not a forecast/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no trading, rebalancing, or cash flow is modelled/i),
    ).toBeInTheDocument();
  });

  it("explains how overlapping shocks resolve, on screen", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Build a scenario" }));

    expect(
      screen.getByText(/a shock on a symbol overrides one on its sector/i),
    ).toBeInTheDocument();
  });

  it("shows the shock each holding will actually receive", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Build a scenario" }));
    // A market-wide fall, then a bigger one aimed at AAPL alone.
    await user.type(screen.getByLabelText("Price change percent"), "-10");
    await user.click(screen.getByRole("button", { name: "Add a shock" }));

    const symbolFields = screen.getAllByLabelText("Symbol");
    await user.type(symbolFields[symbolFields.length - 1] as HTMLElement, "AAPL");
    const changes = screen.getAllByLabelText("Price change percent");
    await user.type(changes[changes.length - 1] as HTMLElement, "-35");

    const preview = screen
      .getByText(/the shock each holding will receive/i)
      .closest("div") as HTMLElement;
    const rows = within(preview).getAllByRole("row");
    // AAPL takes the symbol shock, XOM falls back to the portfolio-wide one.
    const appleRow = rows.find((row) => row.textContent?.includes("AAPL"));
    const exxonRow = rows.find((row) => row.textContent?.includes("XOM"));
    expect(appleRow).toHaveTextContent("-35.00%");
    expect(appleRow).toHaveTextContent("AAPL");
    expect(exxonRow).toHaveTextContent("-10.00%");
    expect(exxonRow).toHaveTextContent("whole portfolio");
  });

  it("refuses to run two shocks at the same target", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Build a scenario" }));
    await user.type(screen.getByLabelText("Price change percent"), "-10");
    await user.click(screen.getByRole("button", { name: "Add a shock" }));

    const symbols = screen.getAllByLabelText("Symbol");
    await user.type(symbols[symbols.length - 1] as HTMLElement, "AAPL");
    let changes = screen.getAllByLabelText("Price change percent");
    await user.type(changes[changes.length - 1] as HTMLElement, "-20");

    await user.click(screen.getByRole("button", { name: "Add a shock" }));
    const moreSymbols = screen.getAllByLabelText("Symbol");
    await user.type(moreSymbols[moreSymbols.length - 1] as HTMLElement, "AAPL");
    changes = screen.getAllByLabelText("Price change percent");
    await user.type(changes[changes.length - 1] as HTMLElement, "-40");

    // The API rejects the whole scenario for this, so it is caught before the
    // request rather than after losing the run to a validation error.
    expect(await screen.findByText(/is shocked more than once/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run this scenario" })).toBeDisabled();
  });

  it("offers to fetch a historical scenario's own prices rather than refusing", async () => {
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/stress-tests`, () =>
        HttpResponse.json(
          errorBody({
            code: "scenario_data_unavailable",
            message: "No holding has stored price data covering this scenario's date range.",
          }),
          { status: 422 },
        ),
      ),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: /run this scenario/i }));

    // The dead end this replaced: "refresh market data for the scenario period
    // and try again", with nothing on screen saying which period that is.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Feb 19, 2020 to Mar 23, 2020/);
    expect(
      screen.getByRole("button", { name: /fetch prices for this period/i }),
    ).toBeInTheDocument();
  });

  it("keeps the scenario the user typed when the run fails", async () => {
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/stress-tests`, () =>
        HttpResponse.json(
          errorBody({
            code: "scenario_data_unavailable",
            message: "No price history covers this scenario window.",
          }),
          { status: 422 },
        ),
      ),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Build a scenario" }));
    await user.type(screen.getByLabelText("Price change percent"), "-15");
    await user.click(screen.getByRole("button", { name: "Run this scenario" }));

    // Custom mode has no window of its own to fetch, so the plain failure is
    // what belongs here, not an offer to fetch the catalogue's.
    expect(
      await screen.findByText(/no price history covers this scenario window/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /fetch prices for this period/i }),
    ).not.toBeInTheDocument();
    // The input survives the failure: re-typing a scenario because the server
    // said no is how people stop using a tool.
    expect(screen.getByLabelText("Price change percent")).toHaveValue("-15");
  });
});

describe("a stress-test result", () => {
  beforeEach(() => {
    server.use(
      ...handlers([
        {
          id: STRESS_RUN_ID,
          portfolio_id: PORTFOLIO_ID,
          scenario_type: "historical",
          scenario_name: "COVID-19 crash, 2020",
          status: "succeeded",
          data_as_of: "2023-12-29",
          total_impact: "-3244.94",
          total_impact_percent: "-0.26",
          created_at: "2026-02-01T11:00:00Z",
        },
      ]),
      http.get(`${API}/stress-tests/${STRESS_RUN_ID}`, () => HttpResponse.json(stressRun())),
    );
  });

  it("shows the starting value, the estimated ending value and the impact", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText("$12,480.55")).toBeInTheDocument();
    expect(screen.getByText("$9,235.61")).toBeInTheDocument();
    expect(screen.getByText("-$3,244.94")).toBeInTheDocument();
    expect(screen.getByText("-26.00%")).toBeInTheDocument();
  });

  it("gives every holding its applied return and where that return came from", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByText("$12,480.55");
    const rows = screen.getAllByRole("row");
    const apple = rows.find((row) => row.textContent?.startsWith("AAPL"));
    expect(apple).toHaveTextContent("-31.00%");
    expect(apple).toHaveTextContent("scenario return for AAPL");
  });

  it("shows each holding's share of the loss", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    const heading = await screen.findByRole("heading", {
      name: /contribution to the estimated loss/i,
    });
    const figure = heading.closest("figure") as HTMLElement;
    expect(figure).toHaveTextContent("62.49%");
  });

  it("lists holdings the scenario could not cover, rather than dropping them", async () => {
    server.use(
      http.get(`${API}/stress-tests/${STRESS_RUN_ID}`, () =>
        HttpResponse.json(stressRun({ status: "partial", excluded_symbols: ["TLT"] })),
      ),
    );
    renderApp(<AppRoutes />, { route: ROUTE });

    const alert = await screen.findByText(/some holdings are not in this estimate/i);
    expect(alert.closest("[role='alert']")).toHaveTextContent("TLT");
    expect(alert.closest("[role='alert']")).toHaveTextContent(/not counted as zero/i);
  });

  it("says so when the position impacts do not sum to the total", async () => {
    server.use(
      http.get(`${API}/stress-tests/${STRESS_RUN_ID}`, () =>
        HttpResponse.json(stressRun({ reconciles: false })),
      ),
    );
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(
      await screen.findByText(/the position impacts do not sum to the total/i),
    ).toBeInTheDocument();
  });

  it("carries the scenario's limitations with its result", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByText("$12,480.55");
    await waitFor(() =>
      expect(
        screen.getAllByText(/an estimate of sensitivity, not a forecast/i).length,
      ).toBeGreaterThan(0),
    );
  });
});
