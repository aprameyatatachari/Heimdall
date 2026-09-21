import { useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { usePortfolio, usePortfolioSummary } from "@/api/portfolios";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataAsOf } from "@/components/DataAsOf";
import { Money, Percent } from "@/components/Figure";
import { Panel } from "@/components/Panel";
import { Failed, Loading } from "@/components/states";
import { useDeletePortfolio } from "@/api/portfolios";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { cx } from "@/lib/cx";
import { useNavigate } from "react-router-dom";

import { PortfolioFormDialog } from "./parts/PortfolioFormDialog";
import { RefreshMarketDataButton } from "./parts/RefreshMarketDataButton";

const TABS = [
  { to: ".", label: "Overview", end: true },
  { to: "holdings", label: "Holdings", end: false },
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

export function PortfolioLayout() {
  const { portfolioId = "" } = useParams();
  const navigate = useNavigate();
  const portfolio = usePortfolio(portfolioId);
  const summary = usePortfolioSummary(portfolioId);
  const remove = useDeletePortfolio();

  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useDocumentTitle(portfolio.data?.name ?? "Portfolio");

  if (portfolio.isPending) return <Loading label="Loading portfolio" />;
  if (portfolio.isError) {
    return <Failed error={portfolio.error} onRetry={() => void portfolio.refetch()} />;
  }

  const currency = portfolio.data.base_currency;
  const s = summary.data;

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
                action={<RefreshMarketDataButton portfolioId={portfolioId} />}
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
          </NavLink>
        ))}
      </nav>

      <Outlet context={{ portfolioId, currency }} />

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
