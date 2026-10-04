import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/routes";
import { rememberPortfolio } from "@/lib/lastPortfolio";
import { analysisRun, RUN_ID, runSummary } from "@/test/analytics";
import { API, signedInHandlers } from "@/test/handlers";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const MAIN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const SIDE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const US = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

function portfolio(id: string, name: string, currency: string, positions: number) {
  return {
    id,
    name,
    description: null,
    base_currency: currency,
    benchmark_symbol: null,
    position_count: positions,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };
}

function holding(symbol: string, marketValue: string | null, costBasis: string) {
  return {
    symbol,
    name: symbol,
    sector: "Technology",
    quantity: "10",
    average_cost: "100.00",
    cost_basis: costBasis,
    latest_price: marketValue === null ? null : "120.00",
    latest_price_date: marketValue === null ? null : "2026-10-01",
    latest_price_fetched_at: null,
    market_value: marketValue,
    weight: marketValue === null ? null : 0.5,
    unrealized_profit_loss: null,
  };
}

function summary(
  id: string,
  currency: string,
  holdings: ReturnType<typeof holding>[],
  totals: { value: string; cost: string; profit: string; percent: number },
) {
  return {
    portfolio_id: id,
    name: id,
    base_currency: currency,
    benchmark_symbol: null,
    data_as_of: "2026-10-01",
    prices_fetched_at: "2026-10-04T08:00:00Z",
    holdings_count: holdings.length,
    priced_holdings_count: holdings.filter((item) => item.market_value !== null).length,
    unpriced_symbols: holdings
      .filter((item) => item.market_value === null)
      .map((item) => item.symbol),
    total_market_value: totals.value,
    total_cost_basis: totals.cost,
    unrealized_profit_loss: totals.profit,
    unrealized_profit_loss_percent: totals.percent,
    largest_position_weight: 0.6,
    sector_weights: { Technology: 1 },
    unknown_sector_weight: 0,
    holdings,
    disclaimer: "Educational tool.",
  };
}

const portfolios = [
  portfolio(MAIN, "Main", "INR", 2),
  portfolio(SIDE, "Side", "INR", 2),
  portfolio(US, "Overseas", "USD", 1),
];

const summaries: Record<string, ReturnType<typeof summary>> = {
  [MAIN]: summary(
    MAIN,
    "INR",
    [holding("TCS.NS", "6000.00", "5000.00"), holding("INFY.NS", "4000.00", "5000.00")],
    { value: "10000.00", cost: "10000.00", profit: "0.00", percent: 0 },
  ),
  [SIDE]: summary(
    SIDE,
    "INR",
    [holding("TCS.NS", "3000.00", "2000.00"), holding("ITC.NS", null, "1000.00")],
    { value: "3000.00", cost: "2000.00", profit: "1000.00", percent: 0.5 },
  ),
  [US]: summary(US, "USD", [holding("AAPL", "2400.00", "2000.00")], {
    value: "2400.00",
    cost: "2000.00",
    profit: "400.00",
    percent: 0.2,
  }),
};

function returnHistory(
  id: string,
  days: number,
  points: [string, number][],
  extra: Record<string, unknown> = {},
) {
  return {
    portfolio_id: id,
    base_currency: id === US ? "USD" : "INR",
    unit: "ratio",
    annualized: false,
    requested_days: days,
    data_as_of: points.at(-1)?.[0] ?? null,
    start: points[0]?.[0] ?? null,
    end: points.at(-1)?.[0] ?? null,
    observations: Math.max(points.length - 1, 0),
    cumulative_return: points.at(-1)?.[1] ?? null,
    symbols: ["TCS.NS"],
    excluded_symbols: [],
    points: points.map(([date, value]) => ({ date, cumulative_return: value })),
    unavailable_reason: points.length === 0 ? "No holding has a stored price." : null,
    assumption: "Portfolio returns are reconstructed by applying today's weights.",
    disclaimer: "Educational tool.",
    ...extra,
  };
}

/** The `days` each return-history request asked for, in order. */
let historyRequests: number[] = [];

beforeEach(() => {
  window.localStorage.clear();
  historyRequests = [];
  server.use(
    ...signedInHandlers,
    http.get(`${API}/portfolios`, () =>
      HttpResponse.json({ items: portfolios, total: 3, limit: 50, offset: 0 }),
    ),
    http.get(`${API}/portfolios/:id/summary`, ({ params }) =>
      HttpResponse.json(summaries[String(params["id"])]),
    ),
    http.get(`${API}/portfolios/:id/return-history`, ({ params, request }) => {
      const days = Number(new URL(request.url).searchParams.get("days"));
      const id = String(params["id"]);
      if (id === MAIN) historyRequests.push(days);
      if (id === MAIN) {
        return HttpResponse.json(
          returnHistory(id, days, [
            ["2026-09-28", 0],
            ["2026-09-29", 0.012],
            ["2026-10-01", 0.0345],
          ]),
        );
      }
      if (id === US) {
        return HttpResponse.json(
          returnHistory(
            id,
            days,
            [
              ["2026-09-28", 0],
              ["2026-09-30", -0.02],
              ["2026-10-02", -0.0512],
            ],
            { excluded_symbols: ["MSFT"] },
          ),
        );
      }
      return HttpResponse.json(returnHistory(id, days, []));
    }),
    http.get(`${API}/portfolios/:id/signals/summary`, ({ params }) =>
      HttpResponse.json({
        portfolio_id: String(params["id"]),
        total_open: params["id"] === MAIN ? 3 : 0,
        by_severity: { informational: 0, elevated: 2, high: 1, critical: 0 },
        disclaimer: "Educational tool.",
      }),
    ),
    http.get(`${API}/portfolios/:id`, ({ params }) =>
      HttpResponse.json(portfolios.find((item) => item.id === params["id"])),
    ),
    http.get(`${API}/portfolios/:id/analysis-runs`, () =>
      HttpResponse.json({ items: [runSummary()], total: 1, limit: 20, offset: 0 }),
    ),
    http.get(`${API}/analysis-runs/${RUN_ID}`, () => HttpResponse.json(analysisRun())),
  );
});

function mainNav() {
  return within(screen.getAllByRole("navigation", { name: "Main" })[0] as HTMLElement);
}

describe("the home page", () => {
  it("shows each portfolio's figures without opening it", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    const card = (await screen.findByText("Side")).closest("a") as HTMLElement;
    await waitFor(() => expect(card).toHaveTextContent("₹3,000.00"));
    expect(card).toHaveTextContent("+₹1,000.00");
    expect(card).toHaveTextContent("+50.00%");
    expect(card).toHaveTextContent("No open signals");
    // An unpriced holding is said to be excluded, not valued at nothing.
    expect(card).toHaveTextContent(/1 unpriced, excluded from the value/);
  });

  it("counts a portfolio's open signals on its card", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    const card = (await screen.findByText("Main")).closest("a") as HTMLElement;
    await waitFor(() => expect(card).toHaveTextContent("3 open signals"));
  });

  it("no longer lists the sections the navigation already has", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByText("Main");
    expect(screen.queryByText(/what you can do with one/i)).not.toBeInTheDocument();
  });

  it("adds a holding together across the portfolios that hold it", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    const heading = await screen.findByRole("heading", {
      name: "Holdings across your INR portfolios",
    });
    const figure = heading.closest("figure") as HTMLElement;
    // 6,000 in Main and 3,000 in Side.
    const row = within(figure).getByText("TCS.NS").closest("li") as HTMLElement;
    expect(row).toHaveTextContent("₹9,000.00");
    expect(row).toHaveTextContent("69.2%");
  });

  it("totals each currency on its own and says why", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    expect(await screen.findByText("Total held · INR")).toBeInTheDocument();
    expect(screen.getByText("Total held · USD")).toBeInTheDocument();
    expect(screen.getByText("₹13,000.00")).toBeInTheDocument();
    // Rupees and dollars are never one number.
    expect(screen.getByText(/not converted or added together/i)).toBeInTheDocument();
  });

  it("names a holding it could not price instead of counting it as zero", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    expect(await screen.findByText(/no price for ITC\.NS/i)).toHaveTextContent(
      /excluded from these totals, not counted as zero/i,
    );
  });

  it("offers the same numbers as a table", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/app" });

    const heading = await screen.findByRole("heading", {
      name: "Holdings across your INR portfolios",
    });
    const figure = heading.closest("figure") as HTMLElement;
    await user.click(within(figure).getByRole("button", { name: "View as table" }));

    const table = within(figure).getByRole("table");
    expect(within(table).getByText("TCS.NS — TCS.NS").closest("tr")).toHaveTextContent("2");
  });
});

describe("the main navigation", () => {
  it("opens a section for the first portfolio when none has been opened", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/app" });

    await user.click(await screen.findByRole("link", { name: "Analytics" }));

    // Not back at the home page: analytics belongs to a portfolio, so one is chosen.
    expect(await screen.findByRole("heading", { name: "Main", level: 1 })).toBeInTheDocument();
    expect(mainNav().getByRole("link", { name: "Analytics" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("opens a section for the portfolio last looked at", async () => {
    rememberPortfolio(SIDE);
    renderApp(<AppRoutes />, { route: "/app/analytics" });

    expect(await screen.findByRole("heading", { name: "Side", level: 1 })).toBeInTheDocument();
  });

  it("stays inside the portfolio being read", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${SIDE}` });

    await screen.findByRole("heading", { name: "Side", level: 1 });
    expect(mainNav().getByRole("link", { name: "Analytics" })).toHaveAttribute(
      "href",
      `/app/portfolios/${SIDE}/analytics`,
    );
  });

  it("marks exactly one item as the page being read", async () => {
    renderApp(<AppRoutes />, { route: `/app/portfolios/${SIDE}` });

    await screen.findByRole("heading", { name: "Side", level: 1 });
    const current = mainNav()
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Portfolios"]);
    // In gold, the colour a link takes on hover.
    expect(current[0]).toHaveClass("text-gold");
  });

  it("marks nothing on the home page", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByText("Main");
    expect(
      mainNav()
        .getAllByRole("link")
        .some((link) => link.hasAttribute("aria-current")),
    ).toBe(false);
  });

  it("goes to the portfolio list when there is no portfolio to open", async () => {
    server.use(
      http.get(`${API}/portfolios`, () =>
        HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 }),
      ),
    );
    renderApp(<AppRoutes />, { route: "/app/stress" });

    expect(
      await screen.findByRole("button", { name: /create your first portfolio/i }),
    ).toBeInTheDocument();
  });
});

describe("returns over time", () => {
  function frame() {
    return screen
      .getByRole("heading", { name: "Returns over time" })
      .closest("figure") as HTMLElement;
  }

  it("draws a line per portfolio, as returns and not as amounts", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByRole("heading", { name: "Returns over time" });
    // Percentages, so rupee and dollar portfolios share one axis honestly.
    await waitFor(() =>
      expect(screen.getByRole("group", { name: "Period" }).parentElement).toHaveTextContent(
        "+3.45%",
      ),
    );
    expect(screen.getByRole("group", { name: "Period" }).parentElement).toHaveTextContent(
      "-5.12%",
    );
    expect(frame()).toHaveTextContent(/not annualized/i);
  });

  it("says the lines are a reconstruction, every time", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByRole("heading", { name: "Returns over time" });
    expect(frame()).toHaveTextContent(/today.s weights are applied/i);
    expect(frame()).toHaveTextContent(/not what was actually held/i);
  });

  it("names a portfolio it could not draw instead of drawing it flat", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByRole("heading", { name: "Returns over time" });
    await waitFor(() => expect(frame()).toHaveTextContent(/Side is not drawn/));
    expect(frame()).toHaveTextContent("No holding has a stored price.");
  });

  it("names a holding left out of a line", async () => {
    renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByRole("heading", { name: "Returns over time" });
    await waitFor(() => expect(frame()).toHaveTextContent(/Overseas: MSFT left out/));
  });

  it("asks for a year by default and for the period chosen", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/app" });

    await waitFor(() => expect(historyRequests).toEqual([365]));
    const month = await screen.findByRole("button", { name: "Last one month" });
    await user.click(month);

    await waitFor(() => expect(historyRequests).toEqual([365, 30]));
    expect(month).toHaveAttribute("aria-pressed", "true");
  });

  it("gives the same numbers as a table, without inventing values", async () => {
    const { user } = renderApp(<AppRoutes />, { route: "/app" });

    await screen.findByRole("heading", { name: "Returns over time" });
    await waitFor(() => expect(frame()).toHaveTextContent(/Overseas: MSFT/));
    await user.click(within(frame()).getByRole("button", { name: "View as table" }));

    const table = within(frame()).getByRole("table");
    const row = (date: string) => within(table).getByText(date).closest("tr") as HTMLElement;
    // Main has no point on the 30th: its return is what it was on the 29th.
    expect(row("Sep 30, 2026")).toHaveTextContent("+1.20%");
    expect(row("Sep 30, 2026")).toHaveTextContent("-2.00%");
    // Main's prices stop on the 1st, so on the 2nd it has no value, not a flat one.
    expect(row("Oct 2, 2026")).toHaveTextContent("—");
  });
});
