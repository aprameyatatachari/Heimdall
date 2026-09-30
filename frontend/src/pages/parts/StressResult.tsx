import type { StressTestRunResponse } from "@/api/types";
import { Alert } from "@/components/Alert";
import { BarChart } from "@/components/charts/BarChart";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { DataAsOf } from "@/components/DataAsOf";
import { Money } from "@/components/Figure";
import { Panel } from "@/components/Panel";
import { cx } from "@/lib/cx";
import { formatMoney, formatPercent, UNAVAILABLE } from "@/lib/format";

/** A ratio arriving as a decimal string. Ratios are safe to parse; money is not. */
function ratio(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function Figure({
  label,
  children,
  caption,
}: {
  label: string;
  children: React.ReactNode;
  caption?: string;
}) {
  return (
    <div>
      <p className="hm-eyebrow mb-2">{label}</p>
      <p className="hm-numeric text-ink text-xl">{children}</p>
      {caption && <p className="text-ink-dim mt-1 text-xs">{caption}</p>}
    </div>
  );
}

/**
 * What a scenario implied for the portfolio.
 *
 * Every figure here is an estimate of sensitivity to a price change, and the
 * screen says so rather than leaving it to the footer. The position table is not
 * decoration: the headline number is only trustworthy if it can be taken apart,
 * and the backend's own reconciliation flag says whether the parts add up.
 */
export function StressResult({ run }: { run: StressTestRunResponse }) {
  const totalImpactPercent = ratio(run.total_impact_percent);
  const isLoss = totalImpactPercent !== null && totalImpactPercent < 0;

  const contributions = run.positions
    .map((position) => ({
      symbol: position.symbol,
      share: ratio(position.contribution_to_loss),
    }))
    .filter((entry) => entry.share !== null)
    .sort((first, second) => (second.share ?? 0) - (first.share ?? 0));

  return (
    <div className="flex flex-col gap-6">
      <Panel className="flex flex-col gap-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="hm-eyebrow mb-1">Scenario</p>
            <h2 className="font-display text-ink text-lg font-light">{run.scenario_name}</h2>
            <p className="text-ink-dim mt-1 text-xs capitalize">{run.scenario_type} scenario</p>
          </div>
          <DataAsOf date={run.data_as_of} />
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Figure label="Starting value" caption="Holdings at their latest stored prices">
            <Money value={run.starting_value} currency={run.currency} />
          </Figure>
          <Figure label="Estimated ending value" caption="If these price changes occurred">
            <Money value={run.ending_value} currency={run.currency} />
          </Figure>
          <Figure label="Estimated impact">
            <Money value={run.total_impact} currency={run.currency} signed tone />
          </Figure>
          <Figure label="Estimated impact, percent">
            <span
              className={cx(
                totalImpactPercent === null
                  ? "text-ink"
                  : totalImpactPercent < 0
                    ? "text-negative"
                    : "text-positive",
              )}
            >
              {totalImpactPercent === null
                ? UNAVAILABLE
                : formatPercent(totalImpactPercent, { signed: true })}
            </span>
          </Figure>
        </div>

        {run.status === "partial" && run.excluded_symbols.length > 0 && (
          <Alert tone="caution" title="Some holdings are not in this estimate">
            <p>
              {run.excluded_symbols.join(", ")} had no usable price data for this scenario, so
              they are excluded from every figure above. They are not treated as unaffected, and
              they are not counted as zero — the estimate simply does not cover them.
            </p>
          </Alert>
        )}

        {!run.reconciles && (
          <Alert tone="caution" title="The position impacts do not sum to the total">
            The table below should add up to the headline figure and does not. Treat the
            per-holding numbers with caution and report this.
          </Alert>
        )}
      </Panel>

      {contributions.length > 0 && (
        <ChartFrame
          title="Contribution to the estimated loss"
          units="Share of the total loss, by holding"
          caption="A holding with a negative share offset part of the loss rather than adding to it."
          table={{
            columns: ["Holding", "Share of loss"],
            rows: contributions.map((entry) => [
              entry.symbol,
              entry.share === null ? UNAVAILABLE : formatPercent(entry.share),
            ]),
          }}
        >
          <BarChart
            data={contributions.map((entry) => ({
              label: entry.symbol,
              value: entry.share,
              color: (entry.share ?? 0) < 0 ? "var(--color-positive)" : "var(--color-series-5)",
            }))}
            formatValue={(value) => formatPercent(value, { digits: 2 })}
            ariaLabel="Share of the estimated loss contributed by each holding"
          />
        </ChartFrame>
      )}

      <Panel className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-sm">
          <caption className="text-ink-dim px-5 py-4 text-start text-xs">
            Every holding the scenario covers, with the return applied to it and where that
            return came from.
          </caption>
          <thead>
            <tr className="border-line-strong border-b">
              {[
                "Holding",
                "Sector",
                "Applied return",
                "From",
                "Starting",
                "Ending",
                "Impact",
              ].map((column, index) => (
                <th
                  key={column}
                  scope="col"
                  className={cx("hm-eyebrow px-4 py-3", index >= 2 ? "text-end" : "text-start")}
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {run.positions.map((position) => {
              const applied = ratio(position.applied_return);
              return (
                <tr key={position.symbol} className="border-line-soft border-b last:border-b-0">
                  <td className="text-ink px-4 py-3">{position.symbol}</td>
                  <td className="text-ink-muted px-4 py-3">{position.sector}</td>
                  <td
                    className={cx(
                      "hm-numeric px-4 py-3 text-end",
                      applied === null
                        ? "text-ink"
                        : applied < 0
                          ? "text-negative"
                          : "text-positive",
                    )}
                  >
                    {applied === null ? UNAVAILABLE : formatPercent(applied, { signed: true })}
                  </td>
                  <td className="text-ink-dim px-4 py-3 text-end text-xs">
                    {position.return_source}
                  </td>
                  <td className="hm-numeric text-ink-muted px-4 py-3 text-end">
                    {formatMoney(position.starting_value, run.currency)}
                  </td>
                  <td className="hm-numeric text-ink-muted px-4 py-3 text-end">
                    {formatMoney(position.ending_value, run.currency)}
                  </td>
                  <td className="hm-numeric px-4 py-3 text-end">
                    <Money value={position.impact} currency={run.currency} signed tone />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>

      <Panel>
        <p className="hm-eyebrow mb-3">What this estimate cannot tell you</p>
        <ul className="text-ink-muted flex flex-col gap-2 text-xs leading-relaxed">
          {run.limitations.map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden="true" className="text-ink-faint">
                —
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <p className="text-ink-dim mt-4 max-w-prose text-xs leading-relaxed">
          {run.disclaimer}
        </p>
      </Panel>

      {!isLoss && totalImpactPercent !== null && (
        <p className="text-ink-dim text-xs">
          This scenario increases the portfolio&apos;s value. That is a property of the shocks
          applied, not a prediction and not a recommendation.
        </p>
      )}
    </div>
  );
}
