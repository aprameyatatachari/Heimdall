/**
 * Signal values, in the unit the rule measures.
 *
 * Every rule type reports its own unit, and the same number means something
 * different under each: 0.34 is a third of the portfolio under
 * `percent_of_portfolio_value`, and a third of the baseline volatility under
 * `ratio_to_baseline`. Rendering both as "0.34" would make a concentration
 * signal and a volatility signal look like the same observation.
 *
 * An unrecognised unit renders the raw number and names the unit beside it,
 * rather than guessing at a format that might be wrong by a factor of a hundred.
 */

import { formatPercent, UNAVAILABLE } from "./format";

export interface UnitOptions {
  locale?: string;
}

function numeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatSignalValue(
  value: string | number | null | undefined,
  unit: string,
  { locale }: UnitOptions = {},
): string {
  const parsed = numeric(value);
  if (parsed === null) return UNAVAILABLE;

  switch (unit) {
    case "percent_of_portfolio_value":
    case "percent_decline_from_peak":
      return formatPercent(parsed, { locale, digits: 2 });
    case "ratio_to_baseline":
      return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(parsed)}×`;
    case "correlation_coefficient":
      return new Intl.NumberFormat(locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(parsed);
    case "expected_trading_days":
      return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(parsed)} trading ${parsed === 1 ? "day" : "days"}`;
    case "count":
      return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(parsed);
    default:
      return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(parsed);
  }
}

/** What the unit measures, said plainly beside the figure. */
export function unitDescription(unit: string): string {
  switch (unit) {
    case "percent_of_portfolio_value":
      return "share of portfolio value";
    case "percent_decline_from_peak":
      return "decline from the highest value reached";
    case "ratio_to_baseline":
      return "compared with the longer-run baseline";
    case "correlation_coefficient":
      return "correlation coefficient, -1 to 1";
    case "expected_trading_days":
      return "trading days behind";
    case "count":
      return "number of holdings";
    default:
      return unit.replace(/_/g, " ");
  }
}

/** The nine rule types, in conventional language beside the branded term. */
export const RULE_LABELS: Record<string, string> = {
  position_concentration: "Position concentration",
  sector_concentration: "Sector concentration",
  volatility_increase: "Volatility increase",
  portfolio_drawdown: "Portfolio drawdown",
  var_threshold: "Value at Risk threshold",
  correlation_increase: "Correlation increase",
  stress_loss: "Stress-test loss",
  stale_market_data: "Stale market data",
  missing_data: "Missing data",
};

export function ruleLabel(ruleType: string): string {
  return RULE_LABELS[ruleType] ?? ruleType.replace(/_/g, " ");
}
