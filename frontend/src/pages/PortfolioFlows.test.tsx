import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { API, errorBody, signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const PORTFOLIO_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";

const portfolio = {
  id: PORTFOLIO_ID,
  name: "Core portfolio",
  description: "Long-term holdings",
  base_currency: "USD",
  benchmark_symbol: "SPY",
  position_count: 2,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

/** One priced holding and one the provider had no price for. */
const summary = {
  portfolio_id: PORTFOLIO_ID,
  name: portfolio.name,
  base_currency: "USD",
  benchmark_symbol: "SPY",
  data_as_of: "2023-12-29",
  holdings_count: 2,
  priced_holdings_count: 1,
  unpriced_symbols: ["JNJ"],
  total_market_value: "4952.03",
  total_cost_basis: "15025.00",
  unrealized_profit_loss: "-10072.97",
  unrealized_profit_loss_percent: -0.6704,
  largest_position_weight: 1,
  sector_weights: { Technology: 1 },
  unknown_sector_weight: 0,
  holdings: [
    {
      symbol: "AAPL",
      name: "Apple Inc.",
      sector: "Technology",
      quantity: "100",
      average_cost: "150.25",
      cost_basis: "15025.00",
      latest_price: "49.52",
      latest_price_date: "2023-12-29",
      market_value: "4952.03",
      weight: 1,
      unrealized_profit_loss: "-10072.97",
    },
  ],
  disclaimer: "Educational tool.",
};

const positions = [
  {
    id: "pos-1",
    portfolio_id: PORTFOLIO_ID,
    asset: {
      id: "asset-1",
      symbol: "AAPL",
      name: "Apple Inc.",
      asset_type: "equity" as const,
      exchange: "NASDAQ",
      currency: "USD",
      sector: "Technology",
      industry: null,
    },
    quantity: "100",
    average_cost: "150.25",
    cost_basis: "15025.00",
    currency: "USD",
    purchase_date: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "pos-2",
    portfolio_id: PORTFOLIO_ID,
    asset: {
      id: "asset-2",
      symbol: "JNJ",
      name: "Johnson & Johnson",
      asset_type: "equity" as const,
      exchange: "NYSE",
      currency: "USD",
      sector: "Healthcare",
      industry: null,
    },
    quantity: "40",
    average_cost: "155.50",
    cost_basis: "6220.00",
    currency: "USD",
    purchase_date: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

function portfolioHandlers(items = [portfolio]) {
  return [
    ...signedInHandlers,
    http.get(`${API}/portfolios`, () =>
      HttpResponse.json({ items, total: items.length, limit: 50, offset: 0 }),
    ),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/positions`, () => HttpResponse.json(positions)),
  ];
}

describe("portfolio list", () => {
  it("invites a first portfolio rather than showing an error", async () => {
    server.use(...portfolioHandlers([]));
    renderApp(<AppRoutes />, { route: "/app/portfolios" });

    expect(await screen.findByText("No portfolios yet")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lists portfolios with their holding counts", async () => {
    server.use(...portfolioHandlers());
    renderApp(<AppRoutes />, { route: "/app/portfolios" });

    expect(await screen.findByText("Core portfolio")).toBeInTheDocument();
    expect(screen.getByText("holdings")).toBeInTheDocument();
  });

  it("renders a failure without claiming the list is empty", async () => {
    server.use(
      ...signedInHandlers,
      http.get(`${API}/portfolios`, () =>
        HttpResponse.json(errorBody({ code: "internal_error", message: "Server error." }), {
          status: 500,
        }),
      ),
    );
    renderApp(<AppRoutes />, { route: "/app/portfolios" });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("No portfolios yet")).not.toBeInTheDocument();
  });
});

describe("portfolio summary", () => {
  it("states how many holdings could be priced", async () => {
    server.use(...portfolioHandlers());
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    expect(await screen.findByText("1 of 2 holdings priced")).toBeInTheDocument();
  });

  it("names the holdings it could not price, and says they are not zero", async () => {
    server.use(...portfolioHandlers());
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    const notice = await screen.findByText(/No price available for JNJ/i);
    expect(notice).toHaveTextContent(/not counted as zero/i);
  });

  it("marks stale prices as stale rather than presenting them as current", async () => {
    server.use(...portfolioHandlers());
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    expect(await screen.findByText(/Prices as of/)).toHaveTextContent(/days old/);
  });

  it("formats money in the portfolio's own currency", async () => {
    server.use(...portfolioHandlers());
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}` });

    expect(await screen.findByText("$15,025.00")).toBeInTheDocument();
  });
});

describe("holdings", () => {
  it("keeps an unpriced holding in the table instead of dropping it", async () => {
    server.use(...portfolioHandlers());
    renderApp(<AppRoutes />, { route: `/app/portfolios/${PORTFOLIO_ID}/holdings` });

    const row = await screen.findByRole("rowheader", { name: /JNJ/ });
    const cells = within(row.closest("tr")!).getAllByText(/no price/i);
    expect(cells.length).toBeGreaterThan(0);
    // The absence of a price must never read as a zero value.
    expect(row.closest("tr")).not.toHaveTextContent("$0.00");
  });

  it("requires confirmation before removing a holding", async () => {
    server.use(...portfolioHandlers());
    const { user } = renderApp(<AppRoutes />, {
      route: `/app/portfolios/${PORTFOLIO_ID}/holdings`,
    });

    const row = (await screen.findByRole("rowheader", { name: /AAPL/ })).closest("tr")!;
    await user.click(within(row).getByRole("button", { name: /delete/i }));

    expect(await screen.findByRole("dialog")).toHaveTextContent(/Remove AAPL/);
    expect(screen.getByRole("button", { name: /remove holding/i })).toBeInTheDocument();
  });
});

describe("CSV import", () => {
  it("reports the exact line, column and reason for every bad row", async () => {
    server.use(
      ...portfolioHandlers(),
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/positions/import`, () =>
        HttpResponse.json(
          errorBody({
            code: "csv_validation_failed",
            message: "The uploaded file contains errors. No changes were made.",
            details: [
              { row: 2, field: "quantity", message: "quantity must be greater than zero." },
              { row: 6, field: "symbol", message: "symbol is required." },
            ],
          }),
          { status: 400 },
        ),
      ),
    );

    const { user } = renderApp(<AppRoutes />, {
      route: `/app/portfolios/${PORTFOLIO_ID}/holdings`,
    });

    await user.click(await screen.findByRole("button", { name: /import csv/i }));

    const file = new File(["symbol,quantity,average_cost\nAAPL,0,1\n"], "holdings.csv", {
      type: "text/csv",
    });
    await user.upload(screen.getByLabelText(/choose a csv file/i), file);
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    const table = await screen.findByRole("table", {
      name: /rows that could not be imported/i,
    });
    expect(within(table).getByText("2")).toBeInTheDocument();
    expect(within(table).getByText("quantity")).toBeInTheDocument();
    expect(within(table).getByText("quantity must be greater than zero.")).toBeInTheDocument();
    expect(within(table).getByText("6")).toBeInTheDocument();
    expect(within(table).getByText("symbol is required.")).toBeInTheDocument();
  });

  it("says plainly that nothing was changed", async () => {
    server.use(
      ...portfolioHandlers(),
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/positions/import`, () =>
        HttpResponse.json(
          errorBody({
            code: "csv_validation_failed",
            message: "The uploaded file contains errors. No changes were made.",
            details: [{ row: 2, field: "quantity", message: "Too small." }],
          }),
          { status: 400 },
        ),
      ),
    );

    const { user } = renderApp(<AppRoutes />, {
      route: `/app/portfolios/${PORTFOLIO_ID}/holdings`,
    });

    await user.click(await screen.findByRole("button", { name: /import csv/i }));
    await user.upload(
      screen.getByLabelText(/choose a csv file/i),
      new File(["x"], "holdings.csv", { type: "text/csv" }),
    );
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/nothing was changed/i);
  });

  it("refreshes the holdings table after a successful import", async () => {
    let imported = false;
    server.use(
      ...signedInHandlers,
      http.get(`${API}/portfolios`, () =>
        HttpResponse.json({ items: [portfolio], total: 1, limit: 50, offset: 0 }),
      ),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/positions`, () =>
        HttpResponse.json(imported ? positions : [positions[0]]),
      ),
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/positions/import`, () => {
        imported = true;
        return HttpResponse.json({
          mode: "merge",
          rows_read: 1,
          positions_created: 1,
          positions_merged: 0,
          positions_removed: 0,
          position_count: 2,
          positions,
          total_cost_basis: "21245.00",
        });
      }),
    );

    const { user } = renderApp(<AppRoutes />, {
      route: `/app/portfolios/${PORTFOLIO_ID}/holdings`,
    });

    await screen.findByRole("rowheader", { name: /AAPL/ });
    expect(screen.queryByRole("rowheader", { name: /JNJ/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /import csv/i }));
    await user.upload(
      screen.getByLabelText(/choose a csv file/i),
      new File(["x"], "holdings.csv", { type: "text/csv" }),
    );
    await user.click(screen.getByRole("button", { name: /^import$/i }));

    await screen.findByText(/Holdings created/i);
    await user.click(screen.getByRole("button", { name: /done/i }));

    // The cache must have been invalidated, not just the dialog closed.
    await waitFor(() =>
      expect(screen.getByRole("rowheader", { name: /JNJ/ })).toBeInTheDocument(),
    );
  });
});
