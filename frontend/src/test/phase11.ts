/**
 * Fixtures for stress tests, signals and reports.
 *
 * Typed against the generated schema, so a backend contract change breaks these
 * at compile time rather than leaving tests passing against a shape the API no
 * longer returns.
 */

import type { AlertRuleCatalogue } from "@/api/signals";
import type {
  AlertRuleResponse,
  MonitoringRunResponse,
  ReportResponse,
  SignalSummaryResponse,
  StressTestRunResponse,
  WarningSignalResponse,
} from "@/api/types";

export const PORTFOLIO_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
export const STRESS_RUN_ID = "dddddddd-4444-4444-8444-dddddddddddd";
export const SIGNAL_ID = "eeeeeeee-5555-4555-8555-eeeeeeeeeeee";
export const RULE_ID = "ffffffff-6666-4666-8666-ffffffffffff";
export const REPORT_ID = "99999999-7777-4777-8777-999999999999";

const DISCLAIMER =
  "Heimdall is an educational portfolio-analysis tool. Its calculations are estimates " +
  "based on historical data and model assumptions and do not constitute financial advice " +
  "or guarantee future results.";

export const scenarioCatalogue = {
  scenario_type: "historical",
  items: [
    {
      key: "covid_19_crash_2020",
      name: "COVID-19 crash, 2020",
      description:
        "Replays the returns observed between the pre-pandemic peak and the March 2020 trough.",
      start: "2020-02-19",
      end: "2020-03-23",
      window: "19 Feb 2020 to 23 Mar 2020",
    },
    {
      key: "rate_shock_2022",
      name: "Rate shock, 2022",
      description: "Replays the 2022 repricing as policy rates rose.",
      start: "2022-01-03",
      end: "2022-10-14",
      window: "3 Jan 2022 to 14 Oct 2022",
    },
  ],
  limitations: [
    "A stress test applies price changes to the portfolio's current holdings. It is an estimate of sensitivity, not a forecast.",
    "Quantities are held fixed. No trading, rebalancing, or cash flow is modelled.",
    "Holdings with no price data in the scenario window are excluded from the estimate and listed separately.",
  ],
};

export function stressRun(
  overrides: Partial<StressTestRunResponse> = {},
): StressTestRunResponse {
  return {
    id: STRESS_RUN_ID,
    portfolio_id: PORTFOLIO_ID,
    scenario_type: "historical",
    scenario_name: "COVID-19 crash, 2020",
    scenario_definition: { key: "covid_19_crash_2020" },
    status: "succeeded",
    data_as_of: "2023-12-29",
    currency: "USD",
    starting_value: "12480.55",
    ending_value: "9235.61",
    total_impact: "-3244.94",
    total_impact_percent: "-0.26",
    positions: [
      {
        symbol: "AAPL",
        sector: "Technology",
        starting_value: "6540.60",
        applied_return: "-0.31",
        return_source: "scenario return for AAPL",
        ending_value: "4513.01",
        impact: "-2027.59",
        impact_percent: "-0.31",
        contribution_to_loss: "0.6249",
      },
      {
        symbol: "SPY",
        sector: "Broad market",
        starting_value: "3759.00",
        applied_return: "-0.24",
        return_source: "scenario return for SPY",
        ending_value: "2856.84",
        impact: "-902.16",
        impact_percent: "-0.24",
        contribution_to_loss: "0.2781",
      },
      {
        symbol: "TLT",
        sector: "Bonds",
        starting_value: "2180.95",
        applied_return: "-0.1444",
        return_source: "scenario return for TLT",
        ending_value: "1865.76",
        impact: "-315.19",
        impact_percent: "-0.1444",
        contribution_to_loss: "0.0971",
      },
    ],
    excluded_symbols: [],
    reconciles: true,
    limitations: scenarioCatalogue.limitations,
    disclaimer: DISCLAIMER,
    created_at: "2026-02-01T11:00:00Z",
    completed_at: "2026-02-01T11:00:02Z",
    ...overrides,
  };
}

export function signalSummary(
  overrides: Partial<SignalSummaryResponse> = {},
): SignalSummaryResponse {
  return {
    portfolio_id: PORTFOLIO_ID,
    total_open: 2,
    by_severity: { informational: 0, elevated: 1, high: 1, critical: 0 },
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}

export function signal(overrides: Partial<WarningSignalResponse> = {}): WarningSignalResponse {
  return {
    id: SIGNAL_ID,
    portfolio_id: PORTFOLIO_ID,
    alert_rule_id: RULE_ID,
    monitoring_run_id: null,
    signal_type: "position_concentration",
    severity: "high",
    severity_icon: "alert-triangle",
    status: "active",
    title: "High position concentration",
    explanation:
      "AAPL represents 34.2% of this portfolio, exceeding your 30% high-severity threshold.",
    suggested_action:
      "Review whether this concentration is intended, and consider what a large fall in AAPL alone would do to the portfolio.",
    metric_name: "largest_position_weight",
    observed_value: "0.342",
    threshold_value: "0.3",
    unit: "percent_of_portfolio_value",
    analysis_period: "As at 2023-12-29",
    data_as_of: "2023-12-29",
    context: { symbol: "AAPL", sector: "Technology" },
    limitations: [
      "Concentration is measured on stored prices. A holding with no price is excluded from the weights.",
    ],
    first_triggered_at: "2026-01-20T09:00:00Z",
    last_triggered_at: "2026-02-01T09:00:00Z",
    acknowledged_at: null,
    resolved_at: null,
    dismissed_at: null,
    created_at: "2026-01-20T09:00:00Z",
    events: [
      {
        event_type: "created",
        from_severity: null,
        to_severity: "elevated",
        from_status: null,
        to_status: "active",
        observed_value: "0.271",
        note: null,
        occurred_at: "2026-01-20T09:00:00Z",
      },
      {
        event_type: "severity_changed",
        from_severity: "elevated",
        to_severity: "high",
        from_status: null,
        to_status: null,
        observed_value: "0.342",
        note: null,
        occurred_at: "2026-02-01T09:00:00Z",
      },
    ],
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}

export function alertRule(overrides: Partial<AlertRuleResponse> = {}): AlertRuleResponse {
  return {
    id: RULE_ID,
    portfolio_id: PORTFOLIO_ID,
    rule_type: "position_concentration",
    name: "Position concentration",
    description: "Raises a signal when one holding grows beyond a share of the portfolio.",
    enabled: true,
    parameters: {},
    severity_configuration: { elevated: 0.2, high: 0.3, critical: 0.4 },
    cooldown_hours: 24,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export const ruleCatalogue: AlertRuleCatalogue = {
  items: [
    {
      rule_type: "position_concentration",
      name: "Position concentration",
      description: "Raises a signal when one holding grows beyond a share of the portfolio.",
      unit: "percent_of_portfolio_value",
      default_severity_configuration: { elevated: 0.2, high: 0.3, critical: 0.4 },
      default_cooldown_hours: 24,
      default_parameters: {},
    },
  ],
  disclaimer: DISCLAIMER,
};

export function monitoringRun(
  overrides: Partial<MonitoringRunResponse> = {},
): MonitoringRunResponse {
  return {
    id: "12121212-8888-4888-8888-121212121212",
    portfolio_id: PORTFOLIO_ID,
    trigger_type: "manual",
    status: "succeeded",
    data_as_of: "2023-12-29",
    rules_evaluated: 9,
    rules_failed: 0,
    signals_created: 1,
    signals_updated: 1,
    signals_resolved: 0,
    error_summary: null,
    rule_results: [],
    started_at: "2026-02-01T12:00:00Z",
    completed_at: "2026-02-01T12:00:03Z",
    ...overrides,
  };
}

export function report(overrides: Partial<ReportResponse> = {}): ReportResponse {
  return {
    id: REPORT_ID,
    portfolio_id: PORTFOLIO_ID,
    analysis_run_id: "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb",
    title: "Portfolio risk report",
    format: "pdf",
    status: "succeeded",
    error_message: null,
    inputs: { include_stress_tests: true, include_signals: true },
    size_bytes: 184_320,
    filename: "heimdall-report.pdf",
    download_url: "/api/v1/reports/99999999-7777-4777-8777-999999999999/download",
    created_at: "2026-02-01T13:00:00Z",
    completed_at: "2026-02-01T13:00:05Z",
    ...overrides,
  };
}
