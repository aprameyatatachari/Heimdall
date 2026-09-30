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
  RULE_ID,
  signal,
  signalSummary,
  SIGNAL_ID,
} from "@/test/phase11";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const ROUTE = `/app/portfolios/${PORTFOLIO_ID}/signals`;

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
  holdings_count: 1,
  priced_holdings_count: 1,
  unpriced_symbols: [],
  total_market_value: "6540.60",
  total_cost_basis: "3005.00",
  unrealized_profit_loss: "3535.60",
  unrealized_profit_loss_percent: 1.1766,
  largest_position_weight: 1,
  sector_weights: { Technology: 1 },
  unknown_sector_weight: 0,
  holdings: [],
  disclaimer: "Educational tool.",
};

function handlers(signals = [signal()], rules = [alertRule()]) {
  return [
    ...signedInHandlers,
    http.get(`${API}/portfolios/${PORTFOLIO_ID}`, () => HttpResponse.json(portfolio)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/summary`, () => HttpResponse.json(summary)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/signals/summary`, () =>
      HttpResponse.json(signalSummary()),
    ),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/signals`, () =>
      HttpResponse.json({ items: signals, total: signals.length, limit: 50, offset: 0 }),
    ),
    http.get(`${API}/signals/${SIGNAL_ID}`, () => HttpResponse.json(signal())),
    http.get(`${API}/alert-rule-types`, () => HttpResponse.json(ruleCatalogue)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/alert-rules`, () => HttpResponse.json(rules)),
    http.get(`${API}/portfolios/${PORTFOLIO_ID}/monitoring-runs`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 }),
    ),
  ];
}

beforeEach(() => {
  server.use(...handlers());
});

describe("the signals screen", () => {
  it("is understandable without knowing what a Gjallarhorn is", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    // The branded term is present, but the conventional one is what carries the
    // meaning, and the explanation says which holding and which threshold.
    expect(
      await screen.findByRole("heading", { name: "High position concentration" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/AAPL represents 34.2% of this portfolio/i)).toBeInTheDocument();
    expect(screen.getAllByText(/gjallarhorn signal/i).length).toBeGreaterThan(0);
  });

  it("distinguishes the observed value from the threshold", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByRole("heading", { name: "High position concentration" });
    // Two similar numbers side by side, each labelled: the failure this prevents
    // is "34.20% / 30.00%" with nothing saying which is which.
    expect(screen.getByText("Observed")).toBeInTheDocument();
    expect(screen.getByText("Your threshold")).toBeInTheDocument();
    expect(screen.getByText("34.20%")).toBeInTheDocument();
    expect(screen.getByText("30.00%")).toBeInTheDocument();
  });

  it("communicates severity with a word and an icon, not colour alone", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    const heading = await screen.findByRole("heading", {
      name: "High position concentration",
    });
    expect(screen.getAllByText("High").length).toBeGreaterThan(0);
    // The badge ships an SVG shape as well as the word.
    const card = heading.closest(".hm-panel");
    expect(card?.querySelector("svg")).toBeTruthy();
  });

  it("counts open signals by severity", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByText(/2 open signals in total/i);
    expect(screen.getAllByText(/open signals?$/i).length).toBeGreaterThan(0);
  });

  it("lets a signal be acknowledged without marking it resolved", async () => {
    let acknowledged = false;
    const seen = signal({ acknowledged_at: "2026-02-02T09:00:00Z", status: "acknowledged" });
    server.use(
      http.post(`${API}/signals/${SIGNAL_ID}/acknowledge`, () => {
        acknowledged = true;
        return HttpResponse.json(seen);
      }),
      // The list refetches after the mutation, so it has to answer with the
      // signal as it now stands or the card would revert on screen.
      http.get(`${API}/portfolios/${PORTFOLIO_ID}/signals`, () =>
        HttpResponse.json({
          items: [acknowledged ? seen : signal()],
          total: 1,
          limit: 50,
          offset: 0,
        }),
      ),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    // Named for the signal, so it is unambiguous next to the status filter.
    await user.click(
      await screen.findByRole("button", { name: "Acknowledge High position concentration" }),
    );

    await waitFor(() => expect(acknowledged).toBe(true));
    // Acknowledging says "I have seen this", and the signal stays open.
    expect(await screen.findByText(/the condition is still present/i)).toBeInTheDocument();
  });

  it("offers no way to mark an active condition resolved", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: /details of/i }));
    const dialog = await screen.findByRole("dialog");

    // A signal resolves when its condition stops being true. A control for
    // resolving one by hand would be a control for hiding risk.
    expect(within(dialog).queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
    expect(within(dialog).getByText(/only the engine resolves a signal/i)).toBeInTheDocument();
  });

  it("shows why a signal fired, and its whole history", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: /details of/i }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/a reasonable next step/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/severity changed/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/elevated to high/i)).toBeInTheDocument();
  });

  it("confirms a dismissal and says what it does not mean", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: /details of/i }));
    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    expect(
      await screen.findByText(/does not mean the condition has cleared/i),
    ).toBeInTheDocument();
  });

  it("keeps resolved signals reachable", async () => {
    server.use(
      ...handlers([
        signal({
          id: "33333333-9999-4999-8999-333333333333",
          status: "resolved",
          resolved_at: "2026-02-02T09:00:00Z",
        }),
      ]),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Resolved" }));

    // The status chip on the card itself, not the filter button that got here.
    const heading = await screen.findByRole("heading", {
      name: "High position concentration",
    });
    const card = heading.closest(".hm-panel") as HTMLElement;
    expect(within(card).getByText("Resolved")).toBeInTheDocument();
  });

  it("never presents a signal as a prediction or a recommendation", async () => {
    renderApp(<AppRoutes />, { route: ROUTE });

    await screen.findByRole("heading", { name: "High position concentration" });
    const page = (document.body.textContent ?? "").toLowerCase();

    // Phrases, not words: the screen says "is not a prediction" and should, so
    // searching for "predict" would fail on the disclaimer that makes it safe.
    for (const claim of [
      "we recommend",
      "you should buy",
      "you should sell",
      "is likely to",
      "we expect",
      "forecast",
      "will fall",
      "will rise",
    ]) {
      expect(page, `the screen claims: ${claim}`).not.toContain(claim);
    }
    expect(page).toContain("none of them is a prediction, and none of them is advice");
  });
});

describe("alert rules", () => {
  it("shows a rule's thresholds in the unit it measures", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Show rules" }));

    const rule = await screen.findByRole("heading", { name: "Position concentration" });
    const item = rule.closest("li") as HTMLElement;
    expect(item).toHaveTextContent("share of portfolio value");
    expect(item).toHaveTextContent("0.3");
  });

  it("refuses thresholds that do not increase with severity", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Show rules" }));
    await user.click(await screen.findByRole("button", { name: /thresholds for/i }));

    const high = screen.getByLabelText(/high threshold for/i);
    await user.clear(high);
    await user.type(high, "0.1");
    await user.click(screen.getByRole("button", { name: "Save thresholds" }));

    expect(
      await screen.findByText(/the high threshold must be greater than the elevated one/i),
    ).toBeInTheDocument();
  });

  it("explains that cooldown mutes notification, not measurement", async () => {
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Show rules" }));
    await user.click(await screen.findByRole("button", { name: /thresholds for/i }));

    expect(
      screen.getByText(/never stops the rule from recording the current risk state/i),
    ).toBeInTheDocument();
  });

  it("restores the documented defaults", async () => {
    let restored: string | null = null;
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/alert-rules/defaults`, ({ request }) => {
        restored = new URL(request.url).searchParams.get("restore");
        return HttpResponse.json([alertRule()]);
      }),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: "Restore defaults" }));

    await waitFor(() => expect(restored).toBe("true"));
  });
});

describe("monitoring", () => {
  it("cannot be submitted twice while it is running", async () => {
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/monitoring-runs`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json(monitoringRun(), { status: 201 });
      }),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    const button = await screen.findByRole("button", { name: /run monitoring now/i });
    await user.click(button);

    // A second evaluation while the first is in flight would double the work and
    // race its own results.
    expect(button).toBeDisabled();
    await waitFor(() => expect(screen.getByText(/9 rules evaluated/i)).toBeInTheDocument());
  });

  it("shows which rules failed without hiding the signals the others produced", async () => {
    server.use(
      http.post(`${API}/portfolios/${PORTFOLIO_ID}/monitoring-runs`, () =>
        HttpResponse.json(
          monitoringRun({
            status: "partial",
            rules_evaluated: 9,
            rules_failed: 1,
            rule_results: [
              {
                rule_id: RULE_ID,
                rule_type: "correlation_increase",
                status: "failed",
                signals_created: 0,
                signals_updated: 0,
                signals_resolved: 0,
                skipped_reason: null,
                error: "Not enough overlapping price history.",
              },
            ],
          }),
          { status: 201 },
        ),
      ),
    );
    const { user } = renderApp(<AppRoutes />, { route: ROUTE });

    await user.click(await screen.findByRole("button", { name: /run monitoring now/i }));

    expect(await screen.findByText(/correlation increase/i)).toBeInTheDocument();
    expect(screen.getByText(/not enough overlapping price history/i)).toBeInTheDocument();
    // Not being able to check a condition is not evidence that it cleared.
    expect(screen.getByText(/is not evidence that it cleared/i)).toBeInTheDocument();
    // The signals that did come through are still on screen.
    expect(
      screen.getByRole("heading", { name: "High position concentration" }),
    ).toBeInTheDocument();
  });
});
