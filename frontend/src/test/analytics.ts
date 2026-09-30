/**
 * Analysis-run fixtures.
 *
 * Typed as the generated `AnalysisRunResponse`, so a backend contract change
 * makes these fail to compile rather than letting a test keep passing against a
 * shape the API no longer returns. AGENTS.md section 8.
 *
 * The numbers are the shape of real ones — a value path that falls and recovers,
 * drawdowns that are zero at each new peak, risk shares that sum to one — because
 * a fixture of round numbers hides exactly the display bugs these tests exist to
 * catch.
 */

import type { RiskResult } from "@/api/analytics";
import type { AnalysisRunResponse, AnalysisRunSummary } from "@/api/types";

export const RUN_ID = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb";
export const OLDER_RUN_ID = "cccccccc-3333-4333-8333-cccccccccccc";

export const WINDOW = {
  start: "2022-01-03",
  end: "2023-12-29",
  observations: 30,
  frequency: "daily",
};

export const FIXED_WEIGHT_NOTE =
  "Portfolio returns are reconstructed by applying today's weights to each " +
  "asset's historical returns. This does not reproduce what the portfolio " +
  "actually held over the period.";

export function result(
  metric: string,
  value: string | null,
  unit: RiskResult["unit"],
  metadata: Record<string, unknown> = {},
  unavailableReason: string | null = null,
): RiskResult {
  return {
    metric,
    value,
    unit,
    metadata: { ...WINDOW, ...metadata },
    unavailable_reason: unavailableReason,
  };
}

/** A value path that dips 12% and recovers, with drawdowns to match. */
export function valuePoints(count = 30): {
  date: string;
  value: number;
  drawdown: number;
}[] {
  const points: { date: string; value: number; drawdown: number }[] = [];
  let peak = 0;
  for (let index = 0; index < count; index += 1) {
    const day = new Date(Date.UTC(2022, 0, 3) + index * 86_400_000);
    // A shallow arc: down to roughly -12% by the middle, back above the start.
    const value = Number((10_000 * (1 + 0.004 * index - 0.0015 * (index % 17))).toFixed(2));
    peak = Math.max(peak, value);
    points.push({
      date: day.toISOString().slice(0, 10),
      value,
      drawdown: Number((value / peak - 1).toFixed(6)),
    });
  }
  return points;
}

export function analysisRun(overrides: Partial<AnalysisRunResponse> = {}): AnalysisRunResponse {
  const points = valuePoints();
  const last = points[points.length - 1];

  return {
    id: RUN_ID,
    portfolio_id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
    analysis_type: "risk_summary",
    status: "succeeded",
    parameters: {
      start: WINDOW.start,
      end: WINDOW.end,
      confidence: 0.95,
      var_method: "historical",
      frequency: "daily",
      annual_risk_free_rate: 0.045,
      benchmark_symbol: "SPY",
      minimum_observations: 30,
      recent_volatility_window: 20,
      periods_per_year: 252,
    },
    data_as_of: "2023-12-29",
    notes: [
      "All figures are estimates derived from historical data and the stated model assumptions. They are not predictions.",
      FIXED_WEIGHT_NOTE,
    ],
    error_message: null,
    created_at: "2026-02-01T10:00:00Z",
    completed_at: "2026-02-01T10:00:04Z",
    results: [
      result("portfolio_value", "12480.55", "currency", {
        currency: "USD",
        scope: "portfolio",
      }),
      result("total_cost_basis", "10000.00", "currency", { currency: "USD" }),
      result("unrealized_profit_loss", "2480.55", "currency", { currency: "USD" }),
      result("holdings_count", "3", "count", { priced: 3 }),
      result("analysis_observations", "30", "count", {
        symbols: ["AAPL", "SPY", "TLT"],
        first_date: "2022-01-04",
        last_date: "2023-12-29",
        dates_excluded_for_non_overlap: 0,
      }),
      result("total_return", "0.2481", "ratio", { annualized: false }),
      result("annualized_return", "0.1183", "ratio", {
        annualized: true,
        periods_per_year: 252,
      }),
      result("volatility_daily", "0.0094", "ratio", { annualized: false }),
      result("volatility_annualized", "0.1492", "ratio", {
        annualized: true,
        periods_per_year: 252,
      }),
      result("portfolio_volatility_from_covariance", "0.1488", "ratio", { annualized: true }),
      result("sharpe_ratio", "0.4926", "ratio", {
        annualized: true,
        annual_risk_free_rate: 0.045,
      }),
      result("max_drawdown", "-0.1204", "ratio", {
        peak_value: 11_800.4,
        trough_value: 10_379.1,
        peak_date: "2022-06-14",
        trough_date: "2022-10-12",
        assumption: FIXED_WEIGHT_NOTE,
      }),
      result("current_drawdown", "-0.0042", "ratio", { assumption: FIXED_WEIGHT_NOTE }),
      result("portfolio_value_series", String(last?.value ?? 0), "currency", {
        currency: "USD",
        starting_value: points[0]?.value ?? 0,
        annualized: false,
        assumption: FIXED_WEIGHT_NOTE,
        points,
      }),
      result("rolling_volatility", "0.1731", "ratio", {
        annualized: true,
        window: 20,
        window_unit: "daily",
        as_of: "2023-12-29",
        assumption:
          "Each point is the volatility of the 20 daily returns ending on that date, annualized. Partial windows are not shown.",
        points: points.slice(19).map((point, index) => ({
          date: point.date,
          value: Number((0.14 + 0.002 * index).toFixed(6)),
        })),
      }),
      result("value_at_risk_historical", "184.22", "currency", {
        confidence: 0.95,
        currency: "USD",
        method: "historical",
        horizon: "1 period",
        assumption:
          "An estimate of a loss exceeded 5% of the time over one period. Not a maximum possible loss.",
      }),
      result("value_at_risk_parametric", "191.08", "currency", {
        confidence: 0.95,
        currency: "USD",
        method: "parametric",
        distribution: "normal",
      }),
      result("expected_shortfall", "243.71", "currency", {
        confidence: 0.95,
        currency: "USD",
        method: "historical",
      }),
      result("benchmark_beta", "0.8742", "ratio", { benchmark_symbol: "SPY" }),
      result("benchmark_correlation", "0.9124", "ratio", { benchmark_symbol: "SPY" }),
      result("benchmark_annualized_return", "0.0964", "ratio", {
        benchmark_symbol: "SPY",
        annualized: true,
      }),
      result("benchmark_alpha_annualized", "0.0221", "ratio", {
        benchmark_symbol: "SPY",
        annualized: true,
      }),
      result("tracking_error", "0.0612", "ratio", {
        benchmark_symbol: "SPY",
        annualized: true,
      }),
      result(
        "information_ratio",
        null,
        "ratio",
        { benchmark_symbol: "SPY" },
        "Tracking error is zero, so an information ratio is undefined.",
      ),
      result("benchmark_comparison_series", "0.2016", "ratio", {
        benchmark_symbol: "SPY",
        indexed_to: 100,
        points: points.map((point, index) => ({
          date: point.date,
          portfolio: Number(((point.value / (points[0]?.value ?? 1)) * 100).toFixed(4)),
          benchmark: Number((100 + index * 0.62).toFixed(4)),
        })),
      }),
      result("average_pairwise_correlation", "0.4133", "ratio", {
        excludes_diagonal: true,
        symbols: ["AAPL", "SPY", "TLT"],
        matrix: [
          [1, 0.78, -0.12],
          [0.78, 1, -0.31],
          [-0.12, -0.31, 1],
        ],
      }),
      result("largest_position_weight", "0.5241", "ratio", { symbol: "AAPL" }),
      result("largest_sector_weight", "0.5241", "ratio", {
        sector: "Technology",
        sector_weights: { Technology: 0.5241, "Broad market": 0.3012, Bonds: 0.1747 },
        unknown_sector_weight: 0,
      }),
      result("risk_contribution", "0.1488", "ratio", {
        annualized: true,
        reconciles_to_portfolio_volatility: true,
        discrepancy: 2.2e-16,
        assets: [
          {
            symbol: "AAPL",
            weight: 0.5241,
            marginal_contribution: 0.1904,
            component_contribution: 0.0998,
            share_of_risk: 0.6707,
          },
          {
            symbol: "SPY",
            weight: 0.3012,
            marginal_contribution: 0.1402,
            component_contribution: 0.0422,
            share_of_risk: 0.2836,
          },
          {
            symbol: "TLT",
            weight: 0.1747,
            marginal_contribution: 0.038,
            component_contribution: 0.0068,
            share_of_risk: 0.0457,
          },
        ],
      }),
    ],
    ...overrides,
  };
}

export function runSummary(overrides: Partial<AnalysisRunSummary> = {}): AnalysisRunSummary {
  return {
    id: RUN_ID,
    portfolio_id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
    analysis_type: "risk_summary",
    status: "succeeded",
    data_as_of: "2023-12-29",
    created_at: "2026-02-01T10:00:00Z",
    completed_at: "2026-02-01T10:00:04Z",
    result_count: 27,
    ...overrides,
  };
}
