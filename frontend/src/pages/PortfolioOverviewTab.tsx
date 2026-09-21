import { usePortfolioSummary } from "@/api/portfolios";
import { Money, Percent } from "@/components/Figure";
import { Panel } from "@/components/Panel";
import { Empty, Failed, Loading } from "@/components/states";
import { formatDate, formatPercent, formatQuantity } from "@/lib/format";

import { usePortfolioContext } from "./parts/portfolioContext";

export function PortfolioOverviewTab() {
  const { portfolioId, currency } = usePortfolioContext();
  const { data, isPending, isError, error, refetch } = usePortfolioSummary(portfolioId);

  if (isPending) return <Loading label="Loading overview" />;
  if (isError) return <Failed error={error} onRetry={() => void refetch()} />;

  if (data.holdings.length === 0) {
    return (
      <Panel className="p-0">
        <Empty
          title="No holdings yet"
          body="Add a position or import a CSV, and this portfolio starts reporting."
        />
      </Panel>
    );
  }

  const sectors = Object.entries(data.sector_weights).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel>
        <h2 className="text-ink text-lg font-medium">Allocation by sector</h2>
        <p className="text-ink-dim mt-1 text-xs">
          Share of market value. Holdings without a price are excluded.
        </p>

        <ul className="mt-5 flex flex-col gap-3">
          {sectors.map(([sector, weight]) => (
            <li key={sector}>
              <div className="flex items-baseline justify-between gap-4 text-sm">
                <span className="text-ink-muted">{sector}</span>
                <span className="hm-numeric text-ink">{formatPercent(weight)}</span>
              </div>
              <div className="bg-surface-2 mt-1.5 h-1.5 overflow-hidden rounded-full">
                <div
                  className="bg-gold h-full rounded-full"
                  style={{ width: `${Math.min(100, weight * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>

        {data.unknown_sector_weight > 0 && (
          <p className="text-ink-dim mt-4 text-xs">
            {formatPercent(data.unknown_sector_weight)} of the portfolio is held in assets whose
            sector the provider did not report. That is unknown, not uncategorised.
          </p>
        )}
      </Panel>

      <Panel>
        <h2 className="text-ink text-lg font-medium">Largest holdings</h2>
        <p className="text-ink-dim mt-1 text-xs">
          By market value as of {formatDate(data.data_as_of)}.
        </p>

        <ul className="mt-5 flex flex-col gap-4">
          {[...data.holdings]
            .sort((a, b) => (b.weight ?? -1) - (a.weight ?? -1))
            .slice(0, 6)
            .map((holding) => (
              <li
                key={holding.symbol}
                className="border-line-soft flex items-baseline justify-between gap-4 border-b pb-3 last:border-b-0 last:pb-0"
              >
                <div className="min-w-0">
                  <p className="text-ink font-medium">{holding.symbol}</p>
                  <p className="text-ink-dim truncate text-xs">
                    {holding.name ?? "Name not provided"} · {formatQuantity(holding.quantity)}{" "}
                    units
                  </p>
                </div>
                <div className="text-end">
                  <Money
                    value={holding.market_value}
                    currency={currency}
                    reason="no price"
                    className="text-ink block text-sm"
                  />
                  <Percent value={holding.weight} className="text-ink-dim block text-xs" />
                </div>
              </li>
            ))}
        </ul>

        {data.largest_position_weight !== null && data.largest_position_weight > 0.3 && (
          <p className="text-caution mt-5 text-xs leading-relaxed">
            <span aria-hidden="true" className="me-2">
              ◆
            </span>
            The largest holding is {formatPercent(data.largest_position_weight)} of this
            portfolio. Concentration is an observed condition, not a recommendation to change
            anything.
          </p>
        )}
      </Panel>
    </div>
  );
}
