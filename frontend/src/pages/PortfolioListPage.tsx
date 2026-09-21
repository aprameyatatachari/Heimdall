import { useState } from "react";
import { Link } from "react-router-dom";

import type { PortfolioResponse } from "@/api/types";
import { usePortfolios } from "@/api/portfolios";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Empty, Failed, Loading } from "@/components/states";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

import { PortfolioFormDialog } from "./parts/PortfolioFormDialog";

function PortfolioRow({ portfolio }: { portfolio: PortfolioResponse }) {
  return (
    <li className="border-line-soft border-b last:border-b-0">
      <Link
        to={`/app/portfolios/${portfolio.id}`}
        className="hover:bg-surface-2 flex flex-wrap items-center gap-4 px-5 py-4 transition-colors"
      >
        <div className="min-w-0 flex-1">
          <p className="text-ink truncate font-medium">{portfolio.name}</p>
          {portfolio.description && (
            <p className="text-ink-dim mt-0.5 truncate text-sm">{portfolio.description}</p>
          )}
        </div>

        <div className="text-ink-muted flex items-center gap-6 text-sm">
          <span className="hm-numeric">
            {portfolio.position_count}
            <span className="text-ink-dim ms-1.5">
              {portfolio.position_count === 1 ? "holding" : "holdings"}
            </span>
          </span>
          <span className="text-ink-dim">{portfolio.base_currency}</span>
          {portfolio.benchmark_symbol && (
            <span className="text-ink-dim hidden sm:inline">
              vs {portfolio.benchmark_symbol}
            </span>
          )}
        </div>
      </Link>
    </li>
  );
}

export function PortfolioListPage() {
  useDocumentTitle("Portfolios");
  const [creating, setCreating] = useState(false);
  const { data, isPending, isError, error, refetch } = usePortfolios();

  const portfolios = data?.items ?? [];

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Your portfolios"
        title="Portfolios"
        description="Track what you hold. Analyse it. Test it against adverse conditions."
        actions={<Button onClick={() => setCreating(true)}>New portfolio</Button>}
      />

      <Panel className="p-0">
        {isPending ? (
          <Loading label="Loading portfolios" />
        ) : isError ? (
          <Failed error={error} onRetry={() => void refetch()} />
        ) : portfolios.length === 0 ? (
          <Empty
            title="No portfolios yet"
            body="A portfolio is a set of holdings Heimdall can measure, stress test and report on. Create one to begin."
            action={
              <Button onClick={() => setCreating(true)}>Create your first portfolio</Button>
            }
          />
        ) : (
          <ul>
            {portfolios.map((portfolio) => (
              <PortfolioRow key={portfolio.id} portfolio={portfolio} />
            ))}
          </ul>
        )}
      </Panel>

      {data && data.total > portfolios.length && (
        <p className="text-ink-dim text-xs">
          Showing {portfolios.length} of {data.total}.
        </p>
      )}

      <PortfolioFormDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
