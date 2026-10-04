import { useState } from "react";

import type { PortfolioResponse } from "@/api/types";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { useReturnHistories, type PortfolioReturnHistory } from "@/hooks/useReturnHistories";
import { cx } from "@/lib/cx";
import { formatDate, formatPercent, formatShortDate } from "@/lib/format";

const PERIODS = [
  { days: 30, label: "1M", name: "one month" },
  { days: 90, label: "3M", name: "three months" },
  { days: 180, label: "6M", name: "six months" },
  { days: 365, label: "1Y", name: "one year" },
  { days: 1095, label: "3Y", name: "three years" },
] as const;

const DEFAULT_DAYS = 365;

/** Below this many days an axis label needs the day, not only the month. */
const SHORT_PERIOD_DAYS = 90;

/**
 * One value per label for a portfolio, on an axis shared with the others.
 *
 * Portfolios in different markets do not trade on the same days. On a date
 * inside a portfolio's own range where it has no point, its cumulative return is
 * what it was at its previous point, because nothing changed while its market
 * was closed. Outside its own range it has no value at all, and none is drawn:
 * a line extended flat past its last price would say the portfolio stood still.
 */
function alignTo(labels: string[], history: PortfolioReturnHistory["history"]) {
  const points = history?.points ?? [];
  const first = points[0]?.date;
  const last = points[points.length - 1]?.date;
  const byDate = new Map(points.map((point) => [point.date, point.cumulative_return]));

  let previous: number | null = null;
  return labels.map((label) => {
    if (!first || !last || label < first || label > last) return null;
    const value = byDate.get(label);
    if (value !== undefined) previous = value;
    return previous;
  });
}

/**
 * How each portfolio's return has moved, on one chart.
 *
 * Returns rather than values, so portfolios of different sizes and in different
 * currencies share an axis honestly: a percentage has no currency. Each line
 * starts at zero on the first date it has and is not annualized.
 *
 * The lines are a reconstruction, and the caption says so every time: today's
 * weights applied to each holding's past returns, not a record of what was held.
 * A portfolio with no series is named with its reason instead of being drawn
 * flat at zero.
 */
export function ReturnsOverTime({ portfolios }: { portfolios: PortfolioResponse[] }) {
  const [days, setDays] = useState<number>(DEFAULT_DAYS);
  const histories = useReturnHistories(portfolios, days);

  const drawn = histories.filter((item) => (item.history?.points.length ?? 0) > 1);
  const pending = histories.some((item) => item.pending);
  const missing = histories.filter(
    (item) => !item.pending && (item.failed || (item.history?.points.length ?? 0) <= 1),
  );
  const excluded = drawn.filter((item) => (item.history?.excluded_symbols.length ?? 0) > 0);

  const labels = [
    ...new Set(drawn.flatMap((item) => item.history?.points.map((point) => point.date) ?? [])),
  ].sort();
  const series = drawn.map((item, index) => ({
    label: item.portfolio.name,
    color: `var(--color-series-${(index % 8) + 1})`,
    values: alignTo(labels, item.history),
  }));

  const period = PERIODS.find((item) => item.days === days);
  const percent = (value: number) => formatPercent(value, { signed: true, digits: 2 });
  const formatLabel = (label: string) =>
    days <= SHORT_PERIOD_DAYS ? formatDate(label) : formatShortDate(label);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Period">
        {PERIODS.map((option) => (
          <button
            key={option.days}
            type="button"
            onClick={() => setDays(option.days)}
            aria-pressed={option.days === days}
            aria-label={`Last ${option.name}`}
            className={cx(
              "rounded-full border px-3 py-1 text-xs transition-colors",
              option.days === days
                ? "border-gold text-gold"
                : "border-line-strong text-ink-muted hover:text-gold",
            )}
          >
            {option.label}
          </button>
        ))}
        {drawn.length > 0 && (
          <ul className="ms-auto flex flex-wrap gap-x-5 gap-y-1 text-xs">
            {drawn.map((item) => (
              <li key={item.portfolio.id} className="text-ink-muted">
                {item.portfolio.name}{" "}
                <span
                  className={cx(
                    "hm-numeric",
                    (item.history?.cumulative_return ?? 0) > 0
                      ? "text-positive"
                      : (item.history?.cumulative_return ?? 0) < 0
                        ? "text-negative"
                        : "text-ink",
                  )}
                >
                  {percent(item.history?.cumulative_return ?? 0)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ChartFrame
        title="Returns over time"
        units={`Cumulative return since the start of the period, in percent. Not annualized. Last ${period?.name ?? `${days} days`} of stored prices.`}
        legend={series.length > 1 ? series : undefined}
        empty={
          drawn.length > 0
            ? undefined
            : pending
              ? "Loading returns…"
              : "No return series yet. A portfolio needs at least two days of stored prices; fetch its price history to see one."
        }
        caption={
          <>
            Today&rsquo;s weights are applied to each holding&rsquo;s past returns. This shows
            how the current mix would have moved, not what was actually held or when it was
            bought, so it will not match the profit or loss against cost above. Each line ends
            at that portfolio&rsquo;s newest stored price.
            {excluded.map((item) => (
              <span key={item.portfolio.id} className="text-caution block">
                <span aria-hidden="true" className="me-1.5">
                  ◆
                </span>
                {item.portfolio.name}: {item.history?.excluded_symbols.join(", ")} left out,
                with no price history in this period.
              </span>
            ))}
            {missing.map((item) => (
              <span key={item.portfolio.id} className="text-caution block">
                <span aria-hidden="true" className="me-1.5">
                  ◆
                </span>
                {item.portfolio.name} is not drawn:{" "}
                {item.failed
                  ? "its returns could not be loaded."
                  : (item.history?.unavailable_reason ??
                    "too little price history in this period.")}
              </span>
            ))}
          </>
        }
        table={{
          columns: ["Date", ...series.map((line) => line.label)],
          rows: labels.map((label, row) => [
            formatDate(label),
            ...series.map((line) => {
              const value = line.values[row];
              return value === null || value === undefined ? "—" : percent(value);
            }),
          ]),
        }}
      >
        <LineChart
          labels={labels}
          series={series}
          formatValue={percent}
          formatLabel={formatLabel}
          baseline={0}
          includeBaseline
          ariaLabel={`Cumulative return of each portfolio over the last ${period?.name ?? `${days} days`}`}
        />
      </ChartFrame>
    </div>
  );
}
