import { useEffect, useRef } from "react";

import { messageFor } from "@/api/errors";
import { useRefreshMarketData } from "@/api/portfolios";
import { Button } from "@/components/Button";
import { formatDateTimeSeconds } from "@/lib/format";

import { RefreshMarketDataButton } from "./RefreshMarketDataButton";

/**
 * Keeps a portfolio's prices current, and says how current they are.
 *
 * Three things, because "refresh" meant three different needs:
 *
 * - **On load.** Opening or reloading the page reads the newest prices once,
 *   without being asked. A live provider revises today's bar all session, and a
 *   page that showed this morning's price until someone pressed a button would
 *   be presenting a stale figure as current.
 * - **On demand.** One button, one click, every holding. No dialog and no dates,
 *   because the question is only ever "what is it now".
 * - **While it stays open.** Every five minutes, for as long as the tab is
 *   visible. A page left open through a session would otherwise show the price
 *   it opened with.
 * - **History.** Fetching a past window is a different job with a different
 *   answer, and keeps its own dialog.
 *
 * Each of the first three also asks for the portfolio's Gjallarhorn rules to be
 * evaluated against the prices just read. That is what makes the warnings live:
 * a signal computed from older prices than the ones on screen would describe a
 * portfolio the reader is no longer looking at.
 *
 * The time shown is to the second and is the *oldest* fetch among the holdings,
 * so it is true of every price on the screen rather than only the freshest one.
 */
export const LIVE_REFRESH_MS = 5 * 60_000;

export function PriceRefresh({
  portfolioId,
  fetchedAt,
  hasHoldings,
}: {
  portfolioId: string;
  /** When the stalest price on screen was last read. Null when nothing is priced. */
  fetchedAt: string | null | undefined;
  hasHoldings: boolean;
}) {
  const refresh = useRefreshMarketData(portfolioId);
  const refreshedFor = useRef<string | null>(null);
  const { mutate, isPending } = refresh;
  const pending = useRef(isPending);
  pending.current = isPending;

  // Once per portfolio per page load. The ref survives the extra mount React's
  // strict mode performs in development, so this does not fire twice there.
  useEffect(() => {
    if (!hasHoldings || refreshedFor.current === portfolioId) return;
    refreshedFor.current = portfolioId;
    mutate({ quick: true, monitor: true });
  }, [portfolioId, hasHoldings, mutate]);

  // A hidden tab makes no requests: nobody is reading the figures, and the
  // server's own scheduler, where it is enabled, does not depend on this page.
  useEffect(() => {
    if (!hasHoldings) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible" || pending.current) return;
      mutate({ quick: true, monitor: true });
    }, LIVE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [portfolioId, hasHoldings, mutate]);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Button
        size="sm"
        variant="secondary"
        loading={refresh.isPending}
        onClick={() => mutate({ quick: true, monitor: true })}
        disabled={!hasHoldings}
      >
        {refresh.isPending ? "Refreshing" : "Refresh now"}
      </Button>

      <RefreshMarketDataButton portfolioId={portfolioId} />

      <p className="text-ink-dim text-xs" role="status" aria-live="polite">
        {refresh.isPending ? (
          "Reading the newest prices…"
        ) : refresh.isError ? (
          <span className="text-caution">
            <span aria-hidden="true" className="me-1.5">
              ◆
            </span>
            Prices could not be refreshed: {messageFor(refresh.error)} The figures shown are
            from the last successful fetch.
          </span>
        ) : fetchedAt ? (
          <>Prices fetched {formatDateTimeSeconds(fetchedAt)}</>
        ) : (
          "No prices fetched yet"
        )}
      </p>

      {refresh.data && refresh.data.failures.length > 0 && !refresh.isPending && (
        <p className="text-caution basis-full text-xs">
          <span aria-hidden="true" className="me-1.5">
            ◆
          </span>
          Not refreshed: {refresh.data.failures.map((failure) => failure.symbol).join(", ")}.
          Their figures are from an earlier fetch.
        </p>
      )}
    </div>
  );
}
