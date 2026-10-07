/**
 * The metric catalogue.
 *
 * The backend returns a flat list of metrics, each with a unit and a bag of
 * metadata. This module is the single place that says, for every metric Heimdall
 * can produce: what to call it, how to render its value, whether it is
 * annualized, what it means, and which of its metadata belong on screen.
 *
 * Three rules from AGENTS.md and DESIGN.md section 6.3 are enforced here rather
 * than at each call site:
 *
 * 1. The unit is always visible. `display` decides the formatter, and a ratio is
 *    never rendered as though it were a currency amount or the reverse.
 * 2. Annualized and daily figures are never rendered the same way. Every
 *    descriptor declares a `basis`, and the label carries it.
 * 3. A metric that could not be computed renders its reason, never a zero. That
 *    is why `formatResult` returns null rather than a fallback string.
 *
 * Metric metadata arrives as `unknown`, because it is JSON the backend composes
 * per metric. Every reader below validates before returning, so a missing or
 * misshapen field degrades to "unavailable" instead of putting `NaN` on screen.
 */

import type { RiskResult } from "@/api/analytics";
import type { AnalysisRunResponse } from "@/api/types";

import { formatDate, formatMoney, formatPercent } from "./format";

/* -------------------------------------------------------------------------- */
/* Metadata readers                                                            */
/* -------------------------------------------------------------------------- */

type Metadata = Record<string, unknown>;

function metadataOf(result: RiskResult | undefined): Metadata {
  const meta = result?.metadata;
  return meta && typeof meta === "object" ? (meta as Metadata) : {};
}

function readNumber(meta: Metadata, key: string): number | null {
  const value = meta[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readString(meta: Metadata, key: string): string | null {
  const value = meta[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function readBoolean(meta: Metadata, key: string): boolean | null {
  const value = meta[key];
  return typeof value === "boolean" ? value : null;
}

function readRecords(meta: Metadata, key: string): Metadata[] {
  const value = meta[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Metadata => typeof item === "object" && item !== null);
}

/* -------------------------------------------------------------------------- */
/* Series                                                                      */
/* -------------------------------------------------------------------------- */

/** One point of the reconstructed value path, with its drawdown at that date. */
export interface ValuePoint {
  date: string;
  value: number | null;
  drawdown: number | null;
}

export function readValueSeries(result: RiskResult | undefined): ValuePoint[] {
  return readRecords(metadataOf(result), "points").flatMap((point) => {
    const date = readString(point, "date");
    if (!date) return [];
    return [
      { date, value: readNumber(point, "value"), drawdown: readNumber(point, "drawdown") },
    ];
  });
}

/** Portfolio and benchmark, both indexed to the same starting level. */
export interface ComparisonPoint {
  date: string;
  portfolio: number | null;
  benchmark: number | null;
}

export function readComparisonSeries(result: RiskResult | undefined): ComparisonPoint[] {
  return readRecords(metadataOf(result), "points").flatMap((point) => {
    const date = readString(point, "date");
    if (!date) return [];
    return [
      {
        date,
        portfolio: readNumber(point, "portfolio"),
        benchmark: readNumber(point, "benchmark"),
      },
    ];
  });
}

/** One rolling-window measurement. */
export interface RollingPoint {
  date: string;
  value: number | null;
}

export function readRollingSeries(result: RiskResult | undefined): RollingPoint[] {
  return readRecords(metadataOf(result), "points").flatMap((point) => {
    const date = readString(point, "date");
    if (!date) return [];
    return [{ date, value: readNumber(point, "value") }];
  });
}

/** One holding's contribution to portfolio volatility. */
export interface RiskAsset {
  symbol: string;
  weight: number | null;
  marginal: number | null;
  component: number | null;
  share: number | null;
}

export function readRiskAssets(result: RiskResult | undefined): RiskAsset[] {
  return readRecords(metadataOf(result), "assets").flatMap((asset) => {
    const symbol = readString(asset, "symbol");
    if (!symbol) return [];
    return [
      {
        symbol,
        weight: readNumber(asset, "weight"),
        marginal: readNumber(asset, "marginal_contribution"),
        component: readNumber(asset, "component_contribution"),
        share: readNumber(asset, "share_of_risk"),
      },
    ];
  });
}

/** A holding the run left out of its statistics, and how little history it had. */
export interface ExcludedHolding {
  symbol: string;
  priceObservations: number | null;
  /** Its share of the portfolio's value. Null when it could not be weighed. */
  weight: number | null;
}

/** Holdings excluded for too little price history, from `analysis_observations`. */
export function readExcludedHoldings(result: RiskResult | undefined): ExcludedHolding[] {
  return readRecords(metadataOf(result), "excluded_holdings").flatMap((holding) => {
    const symbol = readString(holding, "symbol");
    if (!symbol) return [];
    return [
      {
        symbol,
        priceObservations: readNumber(holding, "price_observations"),
        weight: readNumber(holding, "weight"),
      },
    ];
  });
}

/** One holding's own sensitivity to the benchmark. */
export interface AssetBeta {
  symbol: string;
  beta: number | null;
  weight: number | null;
}

export function readAssetBetas(result: RiskResult | undefined): AssetBeta[] {
  return readRecords(metadataOf(result), "assets").flatMap((asset) => {
    const symbol = readString(asset, "symbol");
    if (!symbol) return [];
    return [{ symbol, beta: readNumber(asset, "beta"), weight: readNumber(asset, "weight") }];
  });
}

export interface CorrelationMatrix {
  symbols: string[];
  /** Row-major, `null` where a pair could not be measured. */
  cells: (number | null)[][];
}

export function readCorrelationMatrix(
  result: RiskResult | undefined,
): CorrelationMatrix | null {
  const meta = metadataOf(result);
  const symbols = meta["symbols"];
  const matrix = meta["matrix"];
  if (!Array.isArray(symbols) || !Array.isArray(matrix)) return null;

  const names = symbols.filter((item): item is string => typeof item === "string");
  if (names.length === 0 || matrix.length !== names.length) return null;

  const cells = matrix.map((row) =>
    names.map((_, column) => {
      const cell = Array.isArray(row) ? row[column] : null;
      return typeof cell === "number" && Number.isFinite(cell) ? cell : null;
    }),
  );
  return { symbols: names, cells };
}

export interface SectorWeight {
  sector: string;
  weight: number;
}

export function readSectorWeights(result: RiskResult | undefined): SectorWeight[] {
  const weights = metadataOf(result)["sector_weights"];
  if (!weights || typeof weights !== "object") return [];
  return Object.entries(weights as Metadata)
    .flatMap(([sector, value]) =>
      typeof value === "number" && Number.isFinite(value) ? [{ sector, weight: value }] : [],
    )
    .sort((first, second) => second.weight - first.weight);
}

/**
 * One number or string out of a metric's metadata.
 *
 * Exported so a chart can read the fields that belong to it — a window length, a
 * benchmark symbol, an unknown-sector share — without every caller writing its
 * own validation of untyped JSON.
 */
export function metricMetaNumber(result: RiskResult | undefined, key: string): number | null {
  return readNumber(metadataOf(result), key);
}

export function metricMetaBoolean(result: RiskResult | undefined, key: string): boolean | null {
  return readBoolean(metadataOf(result), key);
}

export function metricMetaString(result: RiskResult | undefined, key: string): string | null {
  return readString(metadataOf(result), key);
}

/** The assumption the backend attached to a metric, if it attached one. */
export function metricAssumption(result: RiskResult | undefined): string | null {
  return readString(metadataOf(result), "assumption");
}

/** The resolved parameters a run was executed with. */
export interface RunParameters {
  start: string | null;
  end: string | null;
  confidence: number | null;
  varMethod: string | null;
  frequency: string | null;
  annualRiskFreeRate: number | null;
  benchmarkSymbol: string | null;
  minimumObservations: number | null;
}

/**
 * What a run was asked to compute.
 *
 * The backend persists the fully resolved request, which is what makes a failed
 * run retryable with the same parameters and a stored run explainable a month
 * later. Read defensively: these are values from the network, not from here.
 */
export function runParameters(run: AnalysisRunResponse | undefined): RunParameters {
  const meta: Metadata =
    run?.parameters && typeof run.parameters === "object" ? (run.parameters as Metadata) : {};
  return {
    start: readString(meta, "start"),
    end: readString(meta, "end"),
    confidence: readNumber(meta, "confidence"),
    varMethod: readString(meta, "var_method"),
    frequency: readString(meta, "frequency"),
    annualRiskFreeRate: readNumber(meta, "annual_risk_free_rate"),
    benchmarkSymbol: readString(meta, "benchmark_symbol"),
    minimumObservations: readNumber(meta, "minimum_observations"),
  };
}

export interface MetricWindow {
  start: string | null;
  end: string | null;
  observations: number | null;
}

/**
 * The analysis window a metric was computed over.
 *
 * Read from the metric rather than from the run, because a metric computed over
 * a shorter effective window than the one requested says so in its own metadata,
 * and the tile must show the period the number actually describes.
 */
export function metricWindow(result: RiskResult | undefined): MetricWindow {
  const meta = metadataOf(result);
  return {
    start: readString(meta, "start"),
    end: readString(meta, "end"),
    observations: readNumber(meta, "observations"),
  };
}

/** The sign of a metric's value, for tone. Returns "flat" when there is none. */
export function resultSign(result: RiskResult | undefined): "positive" | "negative" | "flat" {
  const raw = result?.value;
  if (raw === null || raw === undefined || raw === "") return "flat";
  const numeric = Number(raw);
  if (!Number.isFinite(numeric) || numeric === 0) return "flat";
  return numeric > 0 ? "positive" : "negative";
}

/* -------------------------------------------------------------------------- */
/* Descriptors                                                                 */
/* -------------------------------------------------------------------------- */

export type MetricDisplay = "money" | "percent" | "number" | "count";

/**
 * What the figure describes in time.
 *
 * `annualized` and `daily` are never rendered identically, and neither is ever
 * rendered bare: the word travels with the number. DESIGN.md section 6.3.
 */
export type MetricBasis = "annualized" | "daily" | "period" | "point-in-time";

export interface MetricDescriptor {
  label: string;
  display: MetricDisplay;
  basis: MetricBasis;
  /** Plain language, no advice, no prediction. Shown in the tile's disclosure. */
  definition: string;
  /** A line under the value, drawn from the metric's own metadata. */
  caption?: (result: RiskResult) => string | undefined;
  /** Print an explicit `+` on gains, so the sign never depends on colour. */
  signed?: boolean;
  /** Colour by sign. Only where gain and loss are the point of the figure. */
  tone?: boolean;
}

const BASIS_SUFFIX: Record<MetricBasis, string> = {
  annualized: " (annualized)",
  daily: " (daily)",
  period: " (period)",
  "point-in-time": "",
};

const BASIS_WORD: Record<MetricBasis, string> = {
  annualized: "annualized",
  daily: "per trading day",
  period: "over the selected period",
  "point-in-time": "as at the analysis date",
};

/** The label as it appears on a tile, carrying its own basis. */
export function metricLabel(descriptor: MetricDescriptor): string {
  return `${descriptor.label}${BASIS_SUFFIX[descriptor.basis]}`;
}

export function basisWord(descriptor: MetricDescriptor): string {
  return BASIS_WORD[descriptor.basis];
}

const VAR_CAPTION = (result: RiskResult): string => {
  const confidence = readNumber(metadataOf(result), "confidence");
  const level = confidence === null ? "the stated" : formatPercent(confidence, { digits: 0 });
  return `Estimate at ${level} confidence — not a maximum possible loss`;
};

const BENCHMARK_CAPTION = (result: RiskResult): string | undefined => {
  const symbol = readString(metadataOf(result), "benchmark_symbol");
  return symbol ? `Versus ${symbol}` : undefined;
};

/**
 * Every metric the backend can return.
 *
 * There is no bare "alpha": the backend computes `benchmark_alpha_annualized`,
 * and it is labelled as such. DESIGN.md section 11.
 */
export const METRICS: Record<string, MetricDescriptor> = {
  portfolio_value: {
    label: "Market value",
    display: "money",
    basis: "point-in-time",
    definition:
      "Every holding valued at its newest stored price. A holding with no stored price is left out of this total rather than counted as zero.",
  },
  total_cost_basis: {
    label: "Cost basis",
    display: "money",
    basis: "point-in-time",
    definition: "Quantity multiplied by average cost, summed across the holdings.",
  },
  unrealized_profit_loss: {
    signed: true,
    tone: true,
    label: "Unrealized profit / loss",
    display: "money",
    basis: "point-in-time",
    definition:
      "Market value minus cost basis. It excludes dividends, fees and taxes, and nothing in it is realised until a position is sold.",
  },
  holdings_count: {
    label: "Holdings",
    display: "count",
    basis: "point-in-time",
    definition: "How many positions the portfolio holds.",
    caption: (result) => {
      const priced = readNumber(metadataOf(result), "priced");
      return priced === null ? undefined : `${priced} with a stored price`;
    },
  },
  analysis_observations: {
    label: "Observations",
    display: "count",
    basis: "period",
    definition:
      "How many return periods the analysis used. Dates where any holding lacked a price are excluded, so a return is never computed across a gap.",
    caption: (result) => {
      const meta = metadataOf(result);
      const first = readString(meta, "first_date");
      const last = readString(meta, "last_date");
      if (!first || !last) return undefined;
      return `${formatDate(first)} → ${formatDate(last)}`;
    },
  },
  total_return: {
    tone: true,
    label: "Total return",
    display: "percent",
    basis: "period",
    definition:
      "The compounded return of the reconstructed portfolio across the whole window. It is not annualized.",
  },
  annualized_return: {
    tone: true,
    label: "Return",
    display: "percent",
    basis: "annualized",
    definition:
      "The total return expressed as a constant yearly rate. A window shorter than a year is extrapolated, which magnifies whatever happened inside it.",
  },
  volatility_daily: {
    label: "Volatility",
    display: "percent",
    basis: "daily",
    definition:
      "The standard deviation of daily returns: how far a typical day fell from the average day.",
  },
  volatility_annualized: {
    label: "Volatility",
    display: "percent",
    basis: "annualized",
    definition:
      "Daily volatility scaled by the square root of 252 trading days. This is the figure usually quoted as volatility.",
  },
  portfolio_volatility_from_covariance: {
    label: "Volatility from covariance",
    display: "percent",
    basis: "annualized",
    definition:
      "Portfolio volatility computed from the covariance matrix and today's weights. It is the total that the per-holding risk contributions add up to.",
  },
  rolling_volatility: {
    label: "Rolling volatility",
    display: "percent",
    basis: "annualized",
    definition:
      "Volatility measured over the most recent window rather than the whole period, which shows whether variability has been rising or falling.",
    caption: (result) => {
      const meta = metadataOf(result);
      const window = readNumber(meta, "window");
      const asOf = readString(meta, "as_of");
      if (window === null) return undefined;
      return asOf
        ? `${window}-period window ending ${formatDate(asOf)}`
        : `${window}-period window`;
    },
  },
  sharpe_ratio: {
    label: "Sharpe ratio",
    display: "number",
    basis: "annualized",
    definition:
      "Return above the risk-free rate divided by volatility. A ratio rather than a percentage: it says how much variability came with each unit of excess return.",
    caption: (result) => {
      const rate = readNumber(metadataOf(result), "annual_risk_free_rate");
      return rate === null
        ? undefined
        : `Risk-free rate ${formatPercent(rate, { digits: 2 })} a year`;
    },
  },
  sortino_ratio: {
    label: "Sortino ratio",
    display: "number",
    basis: "annualized",
    definition:
      "Return above the risk-free rate divided by downside volatility. Like the Sharpe ratio, except that swings upward are not counted as risk — only the periods that fell short.",
    caption: (result) => {
      const rate = readNumber(metadataOf(result), "annual_risk_free_rate");
      return rate === null
        ? undefined
        : `Risk-free rate ${formatPercent(rate, { digits: 2 })} a year`;
    },
  },
  downside_deviation: {
    label: "Downside deviation",
    display: "percent",
    basis: "annualized",
    definition:
      "The volatility of only the periods that fell short of the risk-free rate, averaged over every period. It cannot exceed ordinary volatility, and the gap between the two is how much of the variability was upward.",
  },
  calmar_ratio: {
    label: "Calmar ratio",
    display: "number",
    basis: "period",
    definition:
      "Annualized return divided by the size of the maximum drawdown: how much return came with each unit of the worst fall. Undefined for a window with no drawdown.",
  },
  skewness: {
    label: "Skewness",
    display: "number",
    basis: "period",
    definition:
      "Whether the return distribution leans. Negative means the left tail is the longer one — the large moves, when they came, were mostly losses. Zero is symmetric.",
  },
  excess_kurtosis: {
    label: "Excess kurtosis",
    display: "number",
    basis: "period",
    definition:
      "How heavy the tails are against a normal curve, which scores zero. Above zero, extreme periods were more common than a normal model expects, which is exactly when parametric Value at Risk understates the loss.",
  },
  best_period_return: {
    label: "Largest single gain",
    display: "percent",
    basis: "period",
    definition: "The largest one-period gain in the window, and the date it happened.",
    signed: true,
    tone: true,
    caption: (result) => {
      const date = readString(metadataOf(result), "date");
      return date ? `On ${formatDate(date)}` : undefined;
    },
  },
  worst_period_return: {
    label: "Largest single loss",
    display: "percent",
    basis: "period",
    definition:
      "The largest one-period loss in the window, and the date it happened. An average hides this; a holder remembers it.",
    signed: true,
    tone: true,
    caption: (result) => {
      const date = readString(metadataOf(result), "date");
      return date ? `On ${formatDate(date)}` : undefined;
    },
  },
  max_drawdown: {
    label: "Maximum drawdown",
    display: "percent",
    basis: "period",
    definition:
      "The largest fall from a peak to a later trough inside the window. It is always zero or negative.",
    caption: (result) => {
      const meta = metadataOf(result);
      const peak = readString(meta, "peak_date");
      const trough = readString(meta, "trough_date");
      if (!peak || !trough) return undefined;
      return `Peak ${formatDate(peak)} → trough ${formatDate(trough)}`;
    },
  },
  current_drawdown: {
    label: "Current drawdown",
    display: "percent",
    basis: "point-in-time",
    definition:
      "How far below its highest point the reconstructed portfolio ended the window. Zero means it ended at a new high.",
  },
  value_at_risk_historical: {
    label: "Value at Risk, historical",
    display: "money",
    basis: "daily",
    definition:
      "The loss exceeded on the worst few days of the observed history, at the chosen confidence, over one period. It estimates a threshold, not a worst case: larger losses are possible and have happened.",
    caption: VAR_CAPTION,
  },
  value_at_risk_parametric: {
    label: "Value at Risk, parametric",
    display: "money",
    basis: "daily",
    definition:
      "The same threshold estimated from a normal distribution fitted to the returns. Real returns have fatter tails than a normal curve, so this figure tends to understate extreme losses.",
    caption: VAR_CAPTION,
  },
  expected_shortfall: {
    label: "Expected shortfall",
    display: "money",
    basis: "daily",
    definition:
      "The average loss on the days when the Value-at-Risk threshold was breached. It describes how bad the bad days were, not how bad they could get.",
    caption: VAR_CAPTION,
  },
  benchmark_beta: {
    label: "Beta",
    display: "number",
    basis: "period",
    definition:
      "How far the portfolio moved for each unit the benchmark moved. A beta of 1 moved with it, above 1 amplified it, below 1 damped it.",
    caption: BENCHMARK_CAPTION,
  },
  benchmark_correlation: {
    label: "Correlation with benchmark",
    display: "number",
    basis: "period",
    definition:
      "How closely the two series moved together, from -1 to 1. It says nothing about magnitude — that is beta.",
    caption: BENCHMARK_CAPTION,
  },
  benchmark_annualized_return: {
    label: "Benchmark return",
    display: "percent",
    basis: "annualized",
    definition: "The benchmark's own return over the same window, as a yearly rate.",
    caption: BENCHMARK_CAPTION,
  },
  benchmark_alpha_annualized: {
    tone: true,
    label: "Alpha versus benchmark",
    display: "percent",
    basis: "annualized",
    definition:
      "Jensen's alpha: the return left once the part beta alone would explain is accounted for. Measured against the configured benchmark, over this window only.",
    caption: BENCHMARK_CAPTION,
  },
  tracking_error: {
    label: "Tracking error",
    display: "percent",
    basis: "annualized",
    definition:
      "The volatility of the difference between the portfolio's returns and the benchmark's: how tightly one followed the other.",
    caption: BENCHMARK_CAPTION,
  },
  information_ratio: {
    label: "Information ratio",
    display: "number",
    basis: "annualized",
    definition:
      "Return in excess of the benchmark divided by tracking error. Undefined when tracking error is zero.",
    caption: BENCHMARK_CAPTION,
  },
  treynor_ratio: {
    label: "Treynor ratio",
    display: "percent",
    basis: "annualized",
    definition:
      "Return above the risk-free rate divided by beta: the excess return earned for each unit of market risk taken, rather than for each unit of total volatility as Sharpe measures.",
    caption: BENCHMARK_CAPTION,
  },
  upside_capture: {
    label: "Upside capture",
    display: "number",
    basis: "period",
    definition:
      "The portfolio's compounded return over the periods the benchmark rose, as a multiple of the benchmark's. 1.10 gained 10% more than the benchmark when it was rising.",
    caption: BENCHMARK_CAPTION,
  },
  downside_capture: {
    label: "Downside capture",
    display: "number",
    basis: "period",
    definition:
      "The same over the periods the benchmark fell. 0.80 lost 20% less than the benchmark when it was falling; above 1 lost more.",
    caption: BENCHMARK_CAPTION,
  },
  benchmark_comparison_series: {
    label: "Benchmark total return",
    display: "percent",
    basis: "period",
    definition: "The benchmark's compounded return across the whole window.",
    caption: BENCHMARK_CAPTION,
  },
  average_pairwise_correlation: {
    label: "Average pairwise correlation",
    display: "number",
    basis: "period",
    definition:
      "The mean correlation across every pair of holdings, excluding each holding with itself. Higher means the holdings tended to move together, so they diversified each other less.",
  },
  largest_position_weight: {
    label: "Largest position",
    display: "percent",
    basis: "point-in-time",
    definition: "The biggest single holding as a share of portfolio value.",
    caption: (result) => readString(metadataOf(result), "symbol") ?? undefined,
  },
  largest_sector_weight: {
    label: "Largest sector",
    display: "percent",
    basis: "point-in-time",
    definition: "The biggest sector as a share of portfolio value.",
    caption: (result) => readString(metadataOf(result), "sector") ?? undefined,
  },
  risk_contribution: {
    label: "Risk attributed",
    display: "percent",
    basis: "annualized",
    definition:
      "The sum of every holding's contribution to portfolio volatility. It should equal portfolio volatility exactly; that it does is what makes the per-holding shares meaningful.",
    caption: (result) => {
      const reconciles = readBoolean(metadataOf(result), "reconciles_to_portfolio_volatility");
      if (reconciles === null) return undefined;
      return reconciles
        ? "Reconciles with portfolio volatility"
        : "Does not reconcile with portfolio volatility";
    },
  },
  portfolio_value_series: {
    label: "Value at the end of the window",
    display: "money",
    basis: "point-in-time",
    definition:
      "Where the reconstructed value path finished. The path applies today's weights to historical returns, so it approximates the portfolio's history rather than recording it.",
  },
};

/** Tiles in the order the dashboard shows them, grouped by what they describe. */
export interface TileGroup {
  title: string;
  blurb?: string;
  metrics: string[];
}

export const TILE_GROUPS: TileGroup[] = [
  {
    title: "Position",
    metrics: [
      "portfolio_value",
      "total_cost_basis",
      "unrealized_profit_loss",
      "holdings_count",
    ],
  },
  {
    title: "Performance",
    blurb: "Reconstructed by applying today's weights to each holding's own history.",
    metrics: ["total_return", "annualized_return", "analysis_observations"],
  },
  {
    title: "Risk",
    metrics: [
      "volatility_daily",
      "volatility_annualized",
      "rolling_volatility",
      "downside_deviation",
      "sharpe_ratio",
      "sortino_ratio",
      "calmar_ratio",
      "max_drawdown",
      "current_drawdown",
    ],
  },
  {
    title: "Shape of returns",
    blurb:
      "What the averages leave out: whether the distribution leans, how heavy its tails are, and its single best and worst periods.",
    metrics: ["skewness", "excess_kurtosis", "best_period_return", "worst_period_return"],
  },
  {
    title: "Tail risk",
    blurb:
      "Loss thresholds estimated over one trading day. None of these is a maximum possible loss.",
    metrics: ["value_at_risk_historical", "value_at_risk_parametric", "expected_shortfall"],
  },
  {
    title: "Benchmark",
    metrics: [
      "benchmark_beta",
      "benchmark_correlation",
      "benchmark_annualized_return",
      "benchmark_alpha_annualized",
      "tracking_error",
      "information_ratio",
      "treynor_ratio",
      "upside_capture",
      "downside_capture",
    ],
  },
  {
    title: "Concentration",
    metrics: [
      "largest_position_weight",
      "largest_sector_weight",
      "average_pairwise_correlation",
      "portfolio_volatility_from_covariance",
    ],
  },
];

/* -------------------------------------------------------------------------- */
/* Values                                                                      */
/* -------------------------------------------------------------------------- */

/** Every metric in a run, by name. A run never repeats a metric. */
export function indexResults(run: AnalysisRunResponse | undefined): Record<string, RiskResult> {
  const index: Record<string, RiskResult> = {};
  for (const result of run?.results ?? []) index[result.metric] = result;
  return index;
}

export interface FormatContext {
  currency: string;
  locale?: string;
}

/**
 * A metric's value, formatted for its unit.
 *
 * Returns null when there is no value, so the caller renders the backend's own
 * reason rather than a zero or a bare dash. Monetary values stay decimal strings
 * the whole way through; ratios are parsed, because a ratio is not money and
 * cannot lose meaningful precision at the width it is displayed.
 */
export function formatResult(
  result: RiskResult | undefined,
  descriptor: MetricDescriptor,
  { currency, locale }: FormatContext,
): string | null {
  const raw = result?.value;
  if (raw === null || raw === undefined || raw === "") return null;

  if (descriptor.display === "money") {
    return formatMoney(raw, currency, { locale, signed: descriptor.signed });
  }

  const numeric = Number(raw);
  if (!Number.isFinite(numeric)) return null;

  if (descriptor.display === "percent") {
    return formatPercent(numeric, { locale, digits: 2, signed: descriptor.signed });
  }
  if (descriptor.display === "count") {
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(numeric);
  }
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric);
}

/**
 * Why a metric has no value.
 *
 * A metric absent from the run is distinguished from one the run attempted and
 * could not compute: "this run did not produce it" and "there was not enough
 * data" are different facts, and collapsing them hides which one happened.
 */
export function unavailableReason(result: RiskResult | undefined): string {
  if (!result) return "not produced by this run";
  return result.unavailable_reason ?? "unavailable";
}

/** Metrics the run reported as unavailable, for the partial-run summary. */
export function unavailableResults(run: AnalysisRunResponse | undefined): RiskResult[] {
  return (run?.results ?? []).filter((result) => result.value === null);
}
