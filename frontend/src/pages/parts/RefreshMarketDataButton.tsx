import { useState } from "react";

import { messageFor } from "@/api/errors";
import { useRefreshMarketData } from "@/api/portfolios";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";
import { Field } from "@/components/Field";
import { formatDate } from "@/lib/format";

/**
 * Fetches price history for every holding in the portfolio.
 *
 * The window is explicit rather than implied. What comes back is reported in
 * full, including assets that could not be refreshed — a partial refresh is
 * normal and is never presented as a complete one.
 */
export function RefreshMarketDataButton({ portfolioId }: { portfolioId: string }) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const refresh = useRefreshMarketData(portfolioId);

  const result = refresh.data;

  return (
    <>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        Refresh prices
      </Button>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Refresh market data"
        description="Fetch daily price history for every holding in this portfolio."
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={refresh.isPending}>
              Close
            </Button>
            <Button
              loading={refresh.isPending}
              onClick={() =>
                refresh.mutate({ start: start || undefined, end: end || undefined })
              }
            >
              {refresh.isPending ? "Fetching" : "Fetch prices"}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="From"
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              hint="Leave blank for the provider's default range."
            />
            <Field
              label="To"
              type="date"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
          </div>

          {refresh.isError && <Alert tone="error">{messageFor(refresh.error)}</Alert>}

          {result && (
            <div className="border-line rounded-md border p-4 text-sm">
              <p className="text-ink font-medium">
                {result.bars_written === 0
                  ? "Already up to date"
                  : `${result.bars_written.toLocaleString()} price bars written`}
              </p>
              <p className="text-ink-muted mt-1">
                {result.assets_refreshed} asset{result.assets_refreshed === 1 ? "" : "s"}{" "}
                refreshed · data as of {formatDate(result.data_as_of)} · source {result.source}
              </p>

              {result.failures.length > 0 && (
                <div className="border-line-soft mt-4 border-t pt-3">
                  {/* Reported rather than swallowed: an asset with no prices is
                      excluded from every figure that follows, and the user needs
                      to know which one. */}
                  <p className="text-caution font-medium">
                    <span aria-hidden="true" className="me-2">
                      ◆
                    </span>
                    {result.failures.length} asset
                    {result.failures.length === 1 ? "" : "s"} could not be refreshed
                  </p>
                  <ul className="text-ink-muted mt-2 flex flex-col gap-1">
                    {result.failures.map((failure) => (
                      <li key={failure.symbol}>
                        <span className="text-ink font-medium">{failure.symbol}</span> —{" "}
                        {failure.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <p className="text-ink-dim text-xs leading-relaxed">
            Prices come from the configured market-data provider. Heimdall stores what it
            receives and reports the date it covers; it does not fill gaps or estimate missing
            observations.
          </p>
        </div>
      </Dialog>
    </>
  );
}
