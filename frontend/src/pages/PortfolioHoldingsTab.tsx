import { useState } from "react";

import { usePortfolioSummary, usePositions, useDeletePosition } from "@/api/portfolios";
import type { PositionResponse } from "@/api/types";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Money } from "@/components/Figure";
import { Panel } from "@/components/Panel";
import { Unavailable } from "@/components/Unavailable";
import { Empty, Failed, Loading } from "@/components/states";
import { formatDate, formatQuantity } from "@/lib/format";

import { CsvImportDialog } from "./parts/CsvImportDialog";
import { PositionFormDialog } from "./parts/PositionFormDialog";
import { usePortfolioContext } from "./parts/portfolioContext";

export function PortfolioHoldingsTab() {
  const { portfolioId, currency } = usePortfolioContext();
  const positions = usePositions(portfolioId);
  const summary = usePortfolioSummary(portfolioId);
  const remove = useDeletePosition(portfolioId);

  const [adding, setAdding] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState<PositionResponse | null>(null);
  const [deleting, setDeleting] = useState<PositionResponse | null>(null);

  // Prices live on the summary, quantities on the positions. Joining by symbol
  // keeps the table showing a holding even when it has no price at all.
  const priced = new Map((summary.data?.holdings ?? []).map((h) => [h.symbol, h]));

  const actions = (
    <div className="flex flex-wrap gap-3">
      <Button variant="secondary" size="sm" onClick={() => setImporting(true)}>
        Import CSV
      </Button>
      <Button size="sm" onClick={() => setAdding(true)}>
        Add holding
      </Button>
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-ink text-lg font-medium">Holdings</h2>
          <p className="text-ink-dim mt-1 text-xs">
            Quantities and cost are yours. Prices and market values come from the market-data
            provider as of {formatDate(summary.data?.data_as_of)}.
          </p>
        </div>
        {actions}
      </div>

      <Panel className="p-0">
        {positions.isPending ? (
          <Loading label="Loading holdings" />
        ) : positions.isError ? (
          <Failed error={positions.error} onRetry={() => void positions.refetch()} />
        ) : positions.data.length === 0 ? (
          <Empty
            title="No holdings yet"
            body="Add a holding one at a time, or import a CSV exported from your broker."
            action={actions}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] text-sm">
              <caption className="sr-only">
                Holdings in this portfolio, with quantity, cost and current market value.
              </caption>
              <thead>
                <tr className="border-line-strong border-b">
                  {[
                    "Symbol",
                    "Quantity",
                    "Average cost",
                    "Price",
                    "Market value",
                    "Profit / loss",
                    "",
                  ].map((heading, index) => (
                    <th
                      key={heading || index}
                      scope="col"
                      className={`text-ink-dim px-4 py-3 text-2xs font-medium tracking-wider uppercase ${
                        index === 0 || index === 6 ? "text-start" : "text-end"
                      }`}
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.data.map((position) => {
                  const holding = priced.get(position.asset.symbol);
                  return (
                    <tr
                      key={position.id}
                      className="border-line-soft hover:bg-surface-2 border-b transition-colors last:border-b-0"
                    >
                      <th scope="row" className="px-4 py-3 text-start font-normal">
                        <span className="text-ink font-medium">{position.asset.symbol}</span>
                        <span className="text-ink-dim block text-xs">
                          {position.asset.name ?? "Name not provided"}
                        </span>
                      </th>
                      <td className="hm-numeric text-ink px-4 py-3 text-end">
                        {formatQuantity(position.quantity)}
                      </td>
                      <td className="hm-numeric text-ink-muted px-4 py-3 text-end">
                        <Money value={position.average_cost} currency={position.currency} />
                      </td>
                      <td className="px-4 py-3 text-end">
                        {holding?.latest_price ? (
                          <>
                            <Money
                              value={holding.latest_price}
                              currency={currency}
                              className="text-ink-muted"
                            />
                            <span className="text-ink-faint block text-xs">
                              {formatDate(holding.latest_price_date)}
                            </span>
                          </>
                        ) : (
                          // Shown, never dropped and never zero: a holding with
                          // no price is still a holding.
                          <Unavailable reason="no price" />
                        )}
                      </td>
                      <td className="px-4 py-3 text-end">
                        <Money
                          value={holding?.market_value}
                          currency={currency}
                          reason="no price"
                          className="text-ink"
                        />
                      </td>
                      <td className="px-4 py-3 text-end">
                        <Money
                          value={holding?.unrealized_profit_loss}
                          currency={currency}
                          signed
                          tone
                          reason="no price"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setEditing(position)}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleting(position)}
                            className="text-negative hover:text-negative"
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <PositionFormDialog
        open={adding}
        onClose={() => setAdding(false)}
        portfolioId={portfolioId}
      />

      <PositionFormDialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        portfolioId={portfolioId}
        position={editing ?? undefined}
      />

      <CsvImportDialog
        open={importing}
        onClose={() => setImporting(false)}
        portfolioId={portfolioId}
      />

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return;
          remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
        title={`Remove ${deleting?.asset.symbol ?? "this holding"}?`}
        confirmLabel="Remove holding"
        pending={remove.isPending}
      >
        <p className="text-ink-muted text-sm leading-relaxed">
          The holding is removed from this portfolio. Analysis runs already stored keep the
          figures they were computed from.
        </p>
      </ConfirmDialog>
    </div>
  );
}
