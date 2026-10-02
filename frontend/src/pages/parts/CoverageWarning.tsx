import { messageFor } from "@/api/errors";
import { usePriceCoverage, useRefreshMarketData } from "@/api/portfolios";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { formatDate } from "@/lib/format";

/**
 * Says which holdings have no prices for a period, before anything is run on it.
 *
 * An analysis or a scenario over a window some holdings do not cover still
 * produces charts — of the holdings that *are* covered. Those charts look
 * complete, and nothing on them says a third of the portfolio is missing. So the
 * check happens first, while there is still a decision to make: fetch the
 * prices, change the window, or go ahead knowing what is left out.
 *
 * It renders nothing when coverage is complete, and nothing while it is still
 * being checked: a warning that flashes up and vanishes is worse than none.
 */
export function CoverageWarning({
  portfolioId,
  start,
  end,
  what,
}: {
  portfolioId: string;
  start: string;
  end: string;
  /** What is about to run, for the sentence: "analysis" or "scenario". */
  what: string;
}) {
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(start) && /^\d{4}-\d{2}-\d{2}$/.test(end);
  const coverage = usePriceCoverage(portfolioId, valid ? { start, end } : null);
  const fetchPrices = useRefreshMarketData(portfolioId);

  if (!coverage.data || coverage.data.complete) return null;

  const missing = coverage.data.holdings.filter((holding) => holding.status === "none");
  const partial = coverage.data.holdings.filter((holding) => holding.status === "partial");
  const everyHoldingMissing = missing.length === coverage.data.holdings.length;

  return (
    <Alert
      tone="caution"
      title={
        everyHoldingMissing
          ? "No holding has prices for this period"
          : "Some holdings have no prices for this period"
      }
    >
      <p>
        {formatDate(coverage.data.start)} to {formatDate(coverage.data.end)}.{" "}
        {everyHoldingMissing
          ? `The ${what} cannot produce anything until prices for it are fetched.`
          : `The ${what} would run on the holdings that are covered and leave the rest out, so its charts would describe only part of this portfolio.`}
      </p>

      <ul className="mt-2 flex flex-col gap-1">
        {missing.map((holding) => (
          <li key={holding.symbol}>
            <span className="text-ink">{holding.symbol}</span> — no prices stored in this period
          </li>
        ))}
        {partial.map((holding) => (
          <li key={holding.symbol}>
            <span className="text-ink">{holding.symbol}</span> —{" "}
            {holding.first_date && holding.last_date
              ? `prices only from ${formatDate(holding.first_date)} to ${formatDate(holding.last_date)}`
              : "only partly covered"}
          </li>
        ))}
      </ul>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          loading={fetchPrices.isPending}
          onClick={() => fetchPrices.mutate({ start, end })}
        >
          Fetch prices for this period
        </Button>
        {fetchPrices.isError && (
          <span className="text-negative text-xs">{messageFor(fetchPrices.error)}</span>
        )}
        {fetchPrices.isSuccess && !coverage.isFetching && (
          <span className="text-ink-dim text-xs">
            Fetched. Anything still listed is not available from the provider for this period.
          </span>
        )}
      </div>
    </Alert>
  );
}
