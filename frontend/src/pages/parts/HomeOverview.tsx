import { Link } from "react-router-dom";

import { BarChart } from "@/components/charts/BarChart";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { Money, Percent } from "@/components/Figure";
import { Panel } from "@/components/Panel";
import type { PortfolioOverview } from "@/hooks/usePortfolioOverviews";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";

/** How many holdings a chart names before the rest are folded together. */
const NAMED_HOLDINGS = 10;

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="hm-eyebrow mb-1">{label}</dt>
      <dd className="text-ink text-sm">{children}</dd>
    </div>
  );
}

/**
 * One portfolio, with the figures a reader would otherwise have to open it for.
 *
 * Every figure keeps its own missing state. A portfolio with no prices shows
 * "needs prices", not a zero, and one whose summary could not be loaded still
 * links through to where the reason is shown.
 */
export function PortfolioCard({
  portfolio,
  summary,
  summaryPending,
  signals,
}: PortfolioOverview) {
  const currency = portfolio.base_currency;
  const open = signals?.total_open;
  const reason = summaryPending ? "loading" : "needs prices";

  return (
    <Link
      to={`/app/portfolios/${portfolio.id}`}
      className="hm-panel hover:border-gold flex h-full flex-col gap-4 p-5 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink truncate text-base">{portfolio.name}</p>
          <p className="text-ink-dim mt-1 text-xs">
            {portfolio.position_count} {portfolio.position_count === 1 ? "holding" : "holdings"}
            <span aria-hidden="true"> · </span>
            {currency}
            {portfolio.benchmark_symbol && (
              <>
                <span aria-hidden="true"> · </span>
                versus {portfolio.benchmark_symbol}
              </>
            )}
          </p>
        </div>
        {open !== undefined && (
          <span
            className={
              open > 0
                ? "border-line-strong text-ink shrink-0 rounded-full border px-2.5 py-1 text-xs"
                : "text-ink-dim shrink-0 py-1 text-xs"
            }
          >
            {open === 0
              ? "No open signals"
              : `${open} open ${open === 1 ? "signal" : "signals"}`}
          </span>
        )}
      </div>

      <p className="text-ink text-2xl">
        <Money value={summary?.total_market_value} currency={currency} reason={reason} />
      </p>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Stat label="Profit / loss">
          <Money
            value={summary?.unrealized_profit_loss}
            currency={currency}
            signed
            tone
            reason={reason}
          />
        </Stat>
        <Stat label="Return on cost">
          <Percent
            value={summary?.unrealized_profit_loss_percent}
            signed
            tone
            reason={reason}
          />
        </Stat>
        <Stat label="Cost basis">
          <Money value={summary?.total_cost_basis} currency={currency} reason={reason} />
        </Stat>
        <Stat label="Largest holding">
          <Percent value={summary?.largest_position_weight} reason={reason} />
        </Stat>
      </dl>

      <p className="text-ink-faint mt-auto text-xs">
        {summary?.data_as_of
          ? `Prices as of ${formatDate(summary.data_as_of)}`
          : summaryPending
            ? "Loading prices"
            : "No prices yet"}
        {summary && summary.unpriced_symbols.length > 0 && (
          <span className="text-caution">
            {" "}
            · {summary.unpriced_symbols.length} unpriced, excluded from the value
          </span>
        )}
      </p>
    </Link>
  );
}

interface CurrencyGroup {
  currency: string;
  portfolios: number;
  marketValue: number;
  costBasis: number;
  holdings: { symbol: string; name: string | null; value: number; portfolios: number }[];
  unpriced: string[];
  oldest: string | null;
}

/**
 * Add the portfolios up, one currency at a time.
 *
 * Amounts in different currencies are never added together: there is no
 * exchange rate in this application, and a total that mixed rupees with dollars
 * would be a number with no unit. The sums here are made in the browser from
 * each portfolio's own figures, for a chart; the figures of record are each
 * portfolio's own.
 */
function groupByCurrency(loaded: PortfolioOverview[]): CurrencyGroup[] {
  const groups = new Map<string, CurrencyGroup>();

  for (const { portfolio, summary } of loaded) {
    if (!summary) continue;
    const group = groups.get(portfolio.base_currency) ?? {
      currency: portfolio.base_currency,
      portfolios: 0,
      marketValue: 0,
      costBasis: 0,
      holdings: [],
      unpriced: [],
      oldest: null,
    };
    groups.set(portfolio.base_currency, group);
    group.portfolios += 1;

    for (const holding of summary.holdings) {
      const value = holding.market_value === null ? null : Number(holding.market_value);
      if (value === null || Number.isNaN(value)) {
        // Left out of every total and named, rather than counted as nothing.
        if (!group.unpriced.includes(holding.symbol)) group.unpriced.push(holding.symbol);
        continue;
      }
      group.marketValue += value;
      group.costBasis += Number(holding.cost_basis);
      const existing = group.holdings.find((item) => item.symbol === holding.symbol);
      if (existing) {
        existing.value += value;
        existing.portfolios += 1;
      } else {
        group.holdings.push({
          symbol: holding.symbol,
          name: holding.name ?? null,
          value,
          portfolios: 1,
        });
      }
    }

    if (summary.data_as_of && (group.oldest === null || summary.data_as_of < group.oldest)) {
      group.oldest = summary.data_as_of;
    }
  }

  return [...groups.values()]
    .filter((group) => group.holdings.length > 0)
    .sort((a, b) => b.holdings.length - a.holdings.length);
}

/**
 * Everything held, across every portfolio.
 *
 * The question a single portfolio's screen cannot answer: how much of one
 * instrument is held in total when it sits in more than one portfolio.
 */
export function HoldingsAcrossPortfolios({ loaded }: { loaded: PortfolioOverview[] }) {
  const groups = groupByCurrency(loaded);
  const waiting = loaded.some((item) => item.summaryPending);

  if (groups.length === 0) {
    return (
      <Panel>
        <p className="text-ink-dim text-sm">
          {waiting
            ? "Loading holdings…"
            : "No priced holdings yet. Add holdings to a portfolio and fetch their prices to see them here."}
        </p>
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {groups.length > 1 && (
        <p className="text-ink-dim max-w-prose text-xs leading-relaxed">
          Your portfolios are in {groups.length} currencies. Each is shown on its own: amounts
          in different currencies are not converted or added together.
        </p>
      )}

      {groups.map((group) => {
        const ordered = [...group.holdings].sort((a, b) => b.value - a.value);
        const named = ordered.slice(0, NAMED_HOLDINGS);
        const rest = ordered.slice(NAMED_HOLDINGS);
        const restValue = rest.reduce((sum, item) => sum + item.value, 0);
        const money = (value: number) => formatMoney(value.toFixed(2), group.currency);
        const share = (value: number) =>
          formatPercent(group.marketValue === 0 ? 0 : value / group.marketValue, { digits: 1 });
        const profit = group.marketValue - group.costBasis;

        return (
          <div key={group.currency} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_2fr]">
            <Panel className="flex flex-col gap-5">
              <div>
                <p className="hm-eyebrow mb-2">Total held · {group.currency}</p>
                <p className="hm-numeric text-ink text-2xl">{money(group.marketValue)}</p>
                <p className="text-ink-dim mt-1 text-xs">
                  Across {group.portfolios}{" "}
                  {group.portfolios === 1 ? "portfolio" : "portfolios"} and{" "}
                  {group.holdings.length}{" "}
                  {group.holdings.length === 1 ? "instrument" : "instruments"}
                </p>
              </div>
              <dl className="grid grid-cols-2 gap-4">
                <Stat label="Cost basis">
                  <span className="hm-numeric">{money(group.costBasis)}</span>
                </Stat>
                <Stat label="Profit / loss">
                  <Money value={profit.toFixed(2)} currency={group.currency} signed tone />
                </Stat>
                <Stat label="Return on cost">
                  <Percent
                    value={group.costBasis === 0 ? null : profit / group.costBasis}
                    signed
                    tone
                    reason="no cost basis"
                  />
                </Stat>
                <Stat label="Largest holding">
                  <span className="hm-numeric">
                    {named[0] ? `${named[0].symbol} ${share(named[0].value)}` : "—"}
                  </span>
                </Stat>
              </dl>
              {group.unpriced.length > 0 && (
                <p className="text-caution text-xs">
                  <span aria-hidden="true" className="me-1.5">
                    ◆
                  </span>
                  No price for {group.unpriced.join(", ")}. Excluded from these totals, not
                  counted as zero.
                </p>
              )}
            </Panel>

            <ChartFrame
              title={`Holdings across your ${group.currency} portfolios`}
              units={`Market value in ${group.currency}, with each holding's share of the total`}
              caption={
                <>
                  A holding that sits in more than one portfolio is added together. Unrealized
                  figures against cost basis, excluding fees and taxes.
                  {group.oldest && <> Prices as of {formatDate(group.oldest)} or later.</>}
                </>
              }
              table={{
                columns: ["Holding", "Portfolios", "Market value", "Share"],
                rows: ordered.map((item) => [
                  item.name ? `${item.symbol} — ${item.name}` : item.symbol,
                  String(item.portfolios),
                  money(item.value),
                  share(item.value),
                ]),
              }}
            >
              <BarChart
                data={[
                  ...named.map((item) => ({ label: item.symbol, value: item.value })),
                  ...(rest.length > 0
                    ? [
                        {
                          label: `${rest.length} other ${rest.length === 1 ? "holding" : "holdings"}`,
                          value: restValue,
                          color: "var(--color-series-2)",
                        },
                      ]
                    : []),
                ]}
                formatValue={money}
                secondary={(datum) => (datum.value === null ? undefined : share(datum.value))}
                ariaLabel={`Market value by holding across ${group.currency} portfolios`}
              />
            </ChartFrame>
          </div>
        );
      })}
    </div>
  );
}
