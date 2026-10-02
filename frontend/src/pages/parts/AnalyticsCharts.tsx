import type { RiskResult } from "@/api/analytics";
import type { HoldingSummary } from "@/api/portfolios";
import { BarChart } from "@/components/charts/BarChart";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart } from "@/components/charts/LineChart";
import {
  formatDate,
  formatMoney,
  formatMoneyAxis,
  formatPercent,
  formatShortDate,
  UNAVAILABLE,
} from "@/lib/format";
import {
  metricAssumption,
  metricMetaBoolean,
  metricMetaNumber,
  metricMetaString,
  readAssetBetas,
  readComparisonSeries,
  readCorrelationMatrix,
  readRiskAssets,
  readRollingSeries,
  readSectorWeights,
  readValueSeries,
  unavailableReason,
} from "@/lib/metrics";

/**
 * The dashboard's charts.
 *
 * Every one of them draws the numbers the stored run holds — none recomputes
 * anything. A chart that disagreed with the tile beside it would be worse than
 * no chart, so the arithmetic stays where it is checked: in the backend.
 *
 * Each chart states what it cannot show. An empty series renders the run's own
 * reason for the metric being unavailable, never an empty axis and never a flat
 * line at zero. AGENTS.md section 7.2.
 */

const SERIES_PORTFOLIO = "var(--color-series-1)";
const SERIES_BENCHMARK = "var(--color-series-2)";
const SERIES_DRAWDOWN = "var(--color-negative)";
const SERIES_VOLATILITY = "var(--color-horizon-1)";

interface ChartProps {
  result: RiskResult | undefined;
  currency: string;
  locale?: string;
}

/* -------------------------------------------------------------------------- */
/* Value and drawdown                                                          */
/* -------------------------------------------------------------------------- */

export function ValueChart({ result, currency, locale }: ChartProps) {
  const points = readValueSeries(result);
  const assumption = metricAssumption(result);

  return (
    <ChartFrame
      title="Portfolio value over time"
      units={`Reconstructed value in ${currency}, by date`}
      legend={[{ label: "Portfolio value", color: SERIES_PORTFOLIO }]}
      empty={points.length === 0 ? unavailableReason(result) : undefined}
      caption={
        assumption ??
        "Reconstructed by applying today's weights to each holding's historical returns."
      }
      table={{
        columns: ["Date", `Value (${currency})`, "Drawdown"],
        rows: points.map((point) => [
          formatDate(point.date, { locale }),
          // Full precision here, not the axis's compact form: a table is where
          // someone checks a figure, and "$17.3K" is not a figure anyone can
          // check. The backend already rounds the series to the cent, so fixing
          // the scale only removes floating-point dust.
          point.value === null
            ? UNAVAILABLE
            : formatMoney(point.value.toFixed(2), currency, { locale }),
          point.drawdown === null
            ? UNAVAILABLE
            : formatPercent(point.drawdown, { locale, digits: 2 }),
        ]),
      }}
    >
      <LineChart
        labels={points.map((point) => point.date)}
        series={[
          {
            label: "Portfolio value",
            color: SERIES_PORTFOLIO,
            values: points.map((point) => point.value),
          },
        ]}
        formatValue={(value) => formatMoneyAxis(value, currency, { locale })}
        formatLabel={(label) => formatShortDate(label, { locale })}
        ariaLabel={`Portfolio value in ${currency} over the analysis window`}
      />
    </ChartFrame>
  );
}

export function DrawdownChart({ result, locale }: ChartProps) {
  const points = readValueSeries(result);
  const drawdowns = points.map((point) => point.drawdown);

  return (
    <ChartFrame
      title="Drawdown"
      units="Percent below the running peak"
      legend={[{ label: "Drawdown", color: SERIES_DRAWDOWN }]}
      empty={points.length === 0 ? unavailableReason(result) : undefined}
      caption="Measured from the highest value reached so far within the window, so it is zero whenever the portfolio is at a new high."
      table={{
        columns: ["Date", "Drawdown"],
        rows: points.map((point) => [
          formatDate(point.date, { locale }),
          point.drawdown === null
            ? UNAVAILABLE
            : formatPercent(point.drawdown, { locale, digits: 2 }),
        ]),
      }}
    >
      <LineChart
        labels={points.map((point) => point.date)}
        series={[{ label: "Drawdown", color: SERIES_DRAWDOWN, values: drawdowns, fill: true }]}
        formatValue={(value) => formatPercent(value, { locale, digits: 1 })}
        formatLabel={(label) => formatShortDate(label, { locale })}
        baseline={0}
        includeBaseline
        height={200}
        ariaLabel="Portfolio drawdown from its running peak over the analysis window"
      />
    </ChartFrame>
  );
}

/* -------------------------------------------------------------------------- */
/* Benchmark                                                                   */
/* -------------------------------------------------------------------------- */

export function ComparisonChart({ result, locale }: ChartProps) {
  const points = readComparisonSeries(result);
  const symbol = metricMetaString(result, "benchmark_symbol") ?? "Benchmark";
  const indexedTo = metricMetaNumber(result, "indexed_to") ?? 100;

  return (
    <ChartFrame
      title="Portfolio versus benchmark"
      units={`Both indexed to ${indexedTo} on the first common date`}
      legend={[
        { label: "Portfolio", color: SERIES_PORTFOLIO },
        { label: symbol, color: SERIES_BENCHMARK },
      ]}
      empty={points.length === 0 ? unavailableReason(result) : undefined}
      caption={
        metricAssumption(result) ??
        "Indexing compares growth rather than levels: the two series have no common scale otherwise."
      }
      table={{
        columns: ["Date", "Portfolio", symbol],
        rows: points.map((point) => [
          formatDate(point.date, { locale }),
          point.portfolio === null ? UNAVAILABLE : point.portfolio.toFixed(2),
          point.benchmark === null ? UNAVAILABLE : point.benchmark.toFixed(2),
        ]),
      }}
    >
      <LineChart
        labels={points.map((point) => point.date)}
        series={[
          {
            label: "Portfolio",
            color: SERIES_PORTFOLIO,
            values: points.map((point) => point.portfolio),
          },
          {
            label: symbol,
            color: SERIES_BENCHMARK,
            values: points.map((point) => point.benchmark),
          },
        ]}
        formatValue={(value) => value.toFixed(1)}
        formatLabel={(label) => formatShortDate(label, { locale })}
        ariaLabel={`Portfolio growth against ${symbol}, both indexed to ${indexedTo}`}
      />
    </ChartFrame>
  );
}

/* -------------------------------------------------------------------------- */
/* Rolling volatility                                                          */
/* -------------------------------------------------------------------------- */

export function RollingVolatilityChart({ result, locale }: ChartProps) {
  const points = readRollingSeries(result);
  const window = metricMetaNumber(result, "window");

  return (
    <ChartFrame
      title="Rolling volatility"
      units={
        window === null
          ? "Annualized volatility by window"
          : `Annualized volatility of the ${window} periods ending on each date`
      }
      legend={[{ label: "Rolling volatility (annualized)", color: SERIES_VOLATILITY }]}
      empty={points.length === 0 ? unavailableReason(result) : undefined}
      caption={
        metricAssumption(result) ??
        "Partial windows are not drawn: a window with fewer observations than the rest is not comparable with them."
      }
      table={{
        columns: ["Window ending", "Volatility (annualized)"],
        rows: points.map((point) => [
          formatDate(point.date, { locale }),
          point.value === null
            ? UNAVAILABLE
            : formatPercent(point.value, { locale, digits: 2 }),
        ]),
      }}
    >
      <LineChart
        labels={points.map((point) => point.date)}
        series={[
          {
            label: "Rolling volatility",
            color: SERIES_VOLATILITY,
            values: points.map((point) => point.value),
          },
        ]}
        formatValue={(value) => formatPercent(value, { locale, digits: 1 })}
        formatLabel={(label) => formatShortDate(label, { locale })}
        height={200}
        ariaLabel="Annualized volatility of the portfolio measured over a rolling window"
      />
    </ChartFrame>
  );
}

/* -------------------------------------------------------------------------- */
/* Allocation                                                                  */
/* -------------------------------------------------------------------------- */

export function AllocationChart({
  holdings,
  currency,
  dataAsOf,
  locale,
}: {
  holdings: HoldingSummary[];
  currency: string;
  dataAsOf: string | null | undefined;
  locale?: string;
}) {
  // Weighted holdings first, then the unpriced ones, which are shown rather than
  // dropped: a holding missing from an allocation chart reads as a holding the
  // portfolio does not have.
  const ordered = [...holdings].sort((first, second) => {
    if (first.weight === null) return 1;
    if (second.weight === null) return -1;
    return second.weight - first.weight;
  });

  return (
    <ChartFrame
      title="Allocation by holding"
      units="Share of priced portfolio value"
      empty={ordered.length === 0 ? "This portfolio has no holdings yet." : undefined}
      caption={
        <>
          Current weights
          {dataAsOf ? ` as of ${formatDate(dataAsOf, { locale })}` : ""}. These are the weights
          the analysis applies to historical returns. A holding with no stored price has no
          weight and is excluded from the total, not counted as zero.
        </>
      }
      table={{
        columns: ["Holding", "Weight", `Market value (${currency})`],
        rows: ordered.map((holding) => [
          holding.symbol,
          holding.weight === null
            ? UNAVAILABLE
            : formatPercent(holding.weight, { locale, digits: 2 }),
          formatMoney(holding.market_value, currency, { locale }),
        ]),
      }}
    >
      <BarChart
        data={ordered.map((holding) => ({
          label: holding.symbol,
          value: holding.weight,
          reason: "no price available",
        }))}
        formatValue={(value) => formatPercent(value, { locale, digits: 2 })}
        secondary={(datum) => {
          const holding = ordered.find((item) => item.symbol === datum.label);
          return holding ? formatMoney(holding.market_value, currency, { locale }) : undefined;
        }}
        ariaLabel="Share of portfolio value by holding"
      />
    </ChartFrame>
  );
}

export function SectorChart({ result, locale }: ChartProps) {
  const sectors = readSectorWeights(result);
  const unknown = metricMetaNumber(result, "unknown_sector_weight");

  return (
    <ChartFrame
      title="Allocation by sector"
      units="Share of priced portfolio value"
      empty={sectors.length === 0 ? unavailableReason(result) : undefined}
      caption={
        unknown !== null && unknown > 0 ? (
          <>
            {formatPercent(unknown, { locale, digits: 2 })} of value sits in holdings whose
            sector is unknown, so sector exposure is incomplete.
          </>
        ) : (
          "Sectors come from the market-data source's own classification."
        )
      }
      table={{
        columns: ["Sector", "Weight"],
        rows: sectors.map((entry) => [
          entry.sector,
          formatPercent(entry.weight, { locale, digits: 2 }),
        ]),
      }}
    >
      <BarChart
        data={sectors.map((entry, index) => ({
          label: entry.sector,
          value: entry.weight,
          color: `var(--color-series-${(index % 8) + 1})`,
        }))}
        formatValue={(value) => formatPercent(value, { locale, digits: 2 })}
        ariaLabel="Share of portfolio value by sector"
      />
    </ChartFrame>
  );
}

/* -------------------------------------------------------------------------- */
/* Correlation and risk attribution                                            */
/* -------------------------------------------------------------------------- */

export function CorrelationChart({ result, locale }: ChartProps) {
  const matrix = readCorrelationMatrix(result);

  return (
    <ChartFrame
      title="Correlation between holdings"
      units="Correlation coefficient, -1 to 1, over the analysis window"
      empty={matrix === null ? unavailableReason(result) : undefined}
      caption="1 means the pair moved together, 0 that they moved independently, -1 that they moved oppositely. Correlation says nothing about the size of the moves."
    >
      <Heatmap
        symbols={matrix?.symbols ?? []}
        cells={matrix?.cells ?? []}
        formatValue={(value) =>
          new Intl.NumberFormat(locale, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          }).format(value)
        }
        ariaLabel="Correlation between each pair of holdings over the analysis window"
      />
    </ChartFrame>
  );
}

export function RiskContributionChart({ result, locale }: ChartProps) {
  const assets = readRiskAssets(result);
  const reconciles = metricMetaBoolean(result, "reconciles_to_portfolio_volatility");

  return (
    <ChartFrame
      title="Risk contribution by holding"
      units="Share of portfolio volatility"
      empty={assets.length === 0 ? unavailableReason(result) : undefined}
      caption={
        <>
          Each holding's share of portfolio volatility, which accounts for how it moves with the
          others rather than only its own weight.{" "}
          {reconciles === false
            ? "These contributions do not sum to portfolio volatility, so treat the individual shares with caution."
            : "The contributions sum exactly to portfolio volatility, which is what makes the shares comparable."}
        </>
      }
      table={{
        columns: ["Holding", "Weight", "Share of risk", "Contribution (annualized)"],
        rows: assets.map((asset) => [
          asset.symbol,
          asset.weight === null
            ? UNAVAILABLE
            : formatPercent(asset.weight, { locale, digits: 2 }),
          asset.share === null
            ? UNAVAILABLE
            : formatPercent(asset.share, { locale, digits: 2 }),
          asset.component === null
            ? UNAVAILABLE
            : formatPercent(asset.component, { locale, digits: 2 }),
        ]),
      }}
    >
      <BarChart
        data={assets.map((asset) => ({ label: asset.symbol, value: asset.share }))}
        formatValue={(value) => formatPercent(value, { locale, digits: 2 })}
        secondary={(datum) => {
          const asset = assets.find((item) => item.symbol === datum.label);
          return asset?.weight === null || asset?.weight === undefined
            ? undefined
            : `weight ${formatPercent(asset.weight, { locale, digits: 1 })}`;
        }}
        ariaLabel="Share of portfolio volatility contributed by each holding"
      />
    </ChartFrame>
  );
}

/* -------------------------------------------------------------------------- */
/* Beta by holding                                                             */
/* -------------------------------------------------------------------------- */

export function BetaChart({ result, locale }: ChartProps) {
  const assets = [...readAssetBetas(result)].sort(
    (first, second) => (second.beta ?? 0) - (first.beta ?? 0),
  );
  const symbol = metricMetaString(result, "benchmark_symbol") ?? "the benchmark";
  const number = (value: number) =>
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);

  return (
    <ChartFrame
      title="Beta by holding"
      units={`Sensitivity to ${symbol}, where 1.00 moves with it`}
      empty={assets.length === 0 ? unavailableReason(result) : undefined}
      caption={
        <>
          Each holding's own beta against {symbol}. The portfolio's beta is these, weighted by
          how much of the portfolio each one is — so one high-beta holding at a large weight can
          set the figure on its own. A negative beta moved against the benchmark.
        </>
      }
      table={{
        columns: ["Holding", "Beta", "Weight", "Contribution to portfolio beta"],
        rows: assets.map((asset) => [
          asset.symbol,
          asset.beta === null ? UNAVAILABLE : number(asset.beta),
          asset.weight === null
            ? UNAVAILABLE
            : formatPercent(asset.weight, { locale, digits: 2 }),
          asset.beta === null || asset.weight === null
            ? UNAVAILABLE
            : number(asset.beta * asset.weight),
        ]),
      }}
    >
      <BarChart
        data={assets.map((asset) => ({
          label: asset.symbol,
          value: asset.beta,
          color: (asset.beta ?? 0) < 0 ? "var(--color-series-2)" : "var(--color-series-1)",
        }))}
        formatValue={number}
        secondary={(datum) => {
          const asset = assets.find((item) => item.symbol === datum.label);
          return asset?.weight === null || asset?.weight === undefined
            ? undefined
            : `weight ${formatPercent(asset.weight, { locale, digits: 1 })}`;
        }}
        ariaLabel={`Beta of each holding against ${symbol}`}
      />
    </ChartFrame>
  );
}
