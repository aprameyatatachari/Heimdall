import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { usePortfolio, usePortfolioSummary } from "@/api/portfolios";
import { useSignalSummary } from "@/api/signals";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataAsOf } from "@/components/DataAsOf";
import { Money, Percent } from "@/components/Figure";
import { Panel } from "@/components/Panel";
import { Failed, Loading } from "@/components/states";
import { useDeletePortfolio } from "@/api/portfolios";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { SIGNAL_POLL_MS, useNewSignals } from "@/hooks/useNewSignals";
import { cx } from "@/lib/cx";
import { rememberPortfolio } from "@/lib/lastPortfolio";
import { useFadeIn } from "@/lib/motion";
import { useNavigate } from "react-router-dom";

import { PortfolioFormDialog } from "./parts/PortfolioFormDialog";
import { PriceRefresh } from "./parts/PriceRefresh";
import { SignalNotice } from "./parts/SignalNotice";

const TABS = [
  { to: ".", label: "Overview", end: true },
  { to: "holdings", label: "Holdings", end: false },
  { to: "analytics", label: "Analytics", end: false },
  { to: "stress", label: "Stress test", end: false },
  { to: "signals", label: "Signals", end: false },
  { to: "reports", label: "Reports", end: false },
];

function SummaryTile({
  label,
  children,
  caption,
}: {
  label: string;
  children: React.ReactNode;
  caption?: string;
}) {
  return (
    <div className="border-line-soft border-t pt-4 first:border-t-0 sm:border-t-0 sm:border-s sm:ps-6 sm:first:border-s-0 sm:first:ps-0">
      <p className="hm-eyebrow mb-2">{label}</p>
      <p className="text-ink text-xl">{children}</p>
      {caption && <p className="text-ink-dim mt-1 text-xs">{caption}</p>}
    </div>
  );
}

/**
 * How many signals are open, on the tab that leads to them.
 *
 * The number changes instantly when it changes; only the badge's first
 * appearance fades. A count that animated on every update would invite reading
 * a transient value. DESIGN.md section 7.1.
 */
function OpenSignalCount({ count }: { count: number }) {
  const ref = useFadeIn<HTMLSpanElement>();
  return (
    <span
      ref={ref}
      className="border-line-strong text-ink hm-numeric ms-2 inline-flex min-w-5 items-center justify-center rounded-full border px-1.5 text-xs"
    >
      {count}
      <span className="sr-only"> open</span>
    </span>
  );
}

export function PortfolioLayout() {
  const { portfolioId = "" } = useParams();
  const navigate = useNavigate();
  const portfolio = usePortfolio(portfolioId);
  const summary = usePortfolioSummary(portfolioId);
  const signalSummary = useSignalSummary(portfolioId, { refetchInterval: SIGNAL_POLL_MS });
  const newSignals = useNewSignals(portfolioId);
  const remove = useDeletePortfolio();

  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useDocumentTitle(portfolio.data?.name ?? "Portfolio");

  // Remembered only once it has loaded, so an address that leads nowhere is
  // never what the main navigation returns to.
  const loadedId = portfolio.data?.id;
  useEffect(() => {
    if (loadedId) rememberPortfolio(loadedId);
  }, [loadedId]);

  if (portfolio.isPending) return <Loading label="Loading portfolio" />;
  if (portfolio.isError) {
    return <Failed error={portfolio.error} onRetry={() => void portfolio.refetch()} />;
  }

  const currency = portfolio.data.base_currency;
  const s = summary.data;
  const openSignals = signalSummary.data?.total_open ?? 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            to="/app/portfolios"
            className="text-ink-dim hover:text-gold mb-3 inline-flex items-center gap-2 text-sm transition-colors"
          >
            <span aria-hidden="true">←</span> All portfolios
          </Link>
          <h1 className="font-display text-ink text-[length:var(--text-2xl)] leading-tight font-light">
            {portfolio.data.name}
          </h1>
          {portfolio.data.description && (
            <p className="text-ink-muted mt-2 max-w-prose text-sm">
              {portfolio.data.description}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button variant="danger" size="sm" onClick={() => setConfirmingDelete(true)}>
            Delete
          </Button>
        </div>
      </div>

      <Panel>
        {summary.isPending ? (
          <Loading label="Loading summary" className="py-8" />
        ) : summary.isError ? (
          <Failed error={summary.error} onRetry={() => void summary.refetch()} />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryTile
                label="Market value"
                caption={
                  s && s.priced_holdings_count < s.holdings_count
                    ? `${s.priced_holdings_count} of ${s.holdings_count} holdings priced`
                    : undefined
                }
              >
                <Money
                  value={s?.total_market_value}
                  currency={currency}
                  reason="no prices yet"
                />
              </SummaryTile>

              <SummaryTile label="Cost basis">
                <Money value={s?.total_cost_basis} currency={currency} />
              </SummaryTile>

              <SummaryTile
                label="Unrealized profit / loss"
                caption="Against cost basis, excluding fees and taxes"
              >
                <Money
                  value={s?.unrealized_profit_loss}
                  currency={currency}
                  signed
                  tone
                  reason="needs prices"
                />
              </SummaryTile>

              <SummaryTile label="Return on cost">
                <Percent
                  value={s?.unrealized_profit_loss_percent}
                  signed
                  tone
                  reason="needs prices"
                />
              </SummaryTile>
            </div>

            <div className="border-line-soft mt-6 border-t pt-4">
              <DataAsOf
                date={s?.data_as_of}
                action={
                  <PriceRefresh
                    portfolioId={portfolioId}
                    fetchedAt={s?.prices_fetched_at}
                    hasHoldings={(s?.holdings_count ?? 0) > 0}
                  />
                }
              />
              {s && s.unpriced_symbols.length > 0 && (
                <p className="text-caution mt-3 text-sm">
                  <span aria-hidden="true" className="me-2">
                    ◆
                  </span>
                  No price available for {s.unpriced_symbols.join(", ")}. These holdings are
                  excluded from the market value above, not counted as zero.
                </p>
              )}
            </div>
          </>
        )}
      </Panel>

      <nav aria-label="Portfolio sections" className="border-line -mb-px flex gap-1 border-b">
        {TABS.map((tab) => (
          <NavLink
            key={tab.label}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              cx(
                "border-b-2 px-4 py-3 text-sm transition-colors",
                isActive
                  ? "border-gold text-gold"
                  : "text-ink-muted hover:text-ink border-transparent",
              )
            }
          >
            {tab.label}
            {tab.to === "signals" && openSignals > 0 && <OpenSignalCount count={openSignals} />}
          </NavLink>
        ))}
      </nav>

      <Outlet context={{ portfolioId, currency }} />

      {newSignals.fresh.length > 0 && (
        <SignalNotice
          signals={newSignals.fresh}
          to={`/app/portfolios/${portfolioId}/signals`}
          onDismiss={newSignals.clear}
        />
      )}

      <PortfolioFormDialog
        open={editing}
        onClose={() => setEditing(false)}
        portfolio={portfolio.data}
      />

      <ConfirmDialog
        open={confirmingDelete}
        onClose={() => setConfirmingDelete(false)}
        onConfirm={() => {
          remove.mutate(portfolioId, {
            onSuccess: () => navigate("/app/portfolios", { replace: true }),
          });
        }}
        title={`Delete ${portfolio.data.name}?`}
        confirmLabel="Delete portfolio"
        pending={remove.isPending}
      >
        <p className="text-ink-muted text-sm leading-relaxed">
          Its holdings, analysis runs, stress tests, signals and reports are deleted with it.
          This cannot be undone.
        </p>
      </ConfirmDialog>
    </div>
  );
}
