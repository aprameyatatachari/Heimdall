import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/app/routes";
import { API, errorBody, signedInHandlers } from "@/test/handlers";
import { PORTFOLIO_ID, report, REPORT_ID } from "@/test/phase11";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const ROUTE = `/app/portfolios/${PORTFOLIO_ID}/reports`;

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
  holdings_count: 0,
  priced_holdings_count: 0,
  unpriced_symbols: [],
  total_market_value: "0.00",
  total_cost_basis: "0.00",
  unrealized_profit_loss: "0.00",
  unrealized_profit_loss_percent: null,
  largest_position_weight: null,
  sector_weights: {},
  unknown_sector_weight: 0,
  holdings: [],
  disclaimer: "Educational tool.",
};

function handlers(reports: unknown[] = []) {
  return [
    ...signedInHandlers,
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/analysis-runs`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
    ),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/reports`, () =>
      HttpResponse.json({ items: reports, total: reports.length, limit: 20, offset: 0 }),
    ),
  ];
}

beforeEach(() => {
  server.use(...handlers());
});

describe("reports", () => {
  it("offers only the format the backend produces", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByRole("heading", { name: /generate a report/i });
    // PDF only, and no scheduling: the backend has neither an Excel writer nor a
    // scheduling endpoint, and an option that does nothing is worse than none.
    expect(screen.queryByText(/excel/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/schedule/i)).not.toBeInTheDocument();
  });

  it("sends the options the user chose", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/reports`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(report({ status: "pending" }), { status: 201 });
      }),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.type(await screen.findByLabelText("Title"), "Quarterly review");
    await user.click(screen.getByLabelText(/gjallarhorn early warning signals/i));
    await user.click(screen.getByRole("button", { name: "Generate report" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      title: "Quarterly review",
      include_stress_tests: true,
      include_signals: false,
    });
  });

  it("shows a report that is still being generated as pending", async () => {
    server.use(...handlers([report({ status: "pending", size_bytes: null, filename: null })]));
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText("Pending")).toBeInTheDocument();
    expect(screen.getByText(/still being generated/i)).toBeInTheDocument();
    // Nothing to download yet, so nothing offers to.
    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
  });

  it("shows why a report failed, and offers to try again", async () => {
    server.use(
      ...handlers([
        report({
          status: "failed",
          error_message: "The analysis run has no results to report.",
          size_bytes: null,
        }),
      ]),
    );
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/the analysis run has no results to report/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("downloads through the authenticated client rather than a shareable link", async () => {
    let authorization: string | null = null;
    server.use(
      ...handlers([report()]),
      http.get(`${API}/reports/${REPORT_ID}/download`, ({ request }) => {
        authorization = request.headers.get("authorization");
        return new HttpResponse(new Blob(["%PDF-1.7"]), {
          headers: {
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="heimdall-report.pdf"',
          },
        });
      }),
    );

    // jsdom implements neither, and the component legitimately uses both.
    const createObjectURL = vi.fn(() => "blob:test");
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL;

    const { user } = renderApp(<AppRoutes />, { route: ROUTE });
    await user.click(await screen.findByRole("button", { name: /download/i }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    // The file is fetched with the session's token, never opened as a URL that
    // could be copied out of the address bar and shared.
    expect(authorization).toMatch(/^Bearer /);
    // And the handle to it is released rather than pinning the file in memory.
    expect(revokeObjectURL).toHaveBeenCalled();
  });

  it("renders another user's report as not found, never as forbidden", async () => {
    // Passed first: msw resolves with the earliest matching handler, so an
    // override placed after the defaults would never be reached.
    server.use(
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/reports`, () =>
        HttpResponse.json(
          errorBody({ code: "report_not_found", message: "Report not found." }),
          {
            status: 404,
          },
        ),
      ),
      ...handlers(),
    );
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText("Not found")).toBeInTheDocument();
    expect(screen.queryByText(/forbidden|permission|not allowed/i)).not.toBeInTheDocument();
  });

  it("invites a first report rather than showing an error", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    expect(await screen.findByText("No reports yet")).toBeInTheDocument();
  });

  it("carries the disclaimer", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByRole("heading", { name: /generate a report/i });
    expect(screen.getAllByText(/educational portfolio-analysis tool/i).length).toBeGreaterThan(
      0,
    );
  });
});
