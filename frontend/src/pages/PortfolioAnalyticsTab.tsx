import { useState } from "react";

import {
  newestRunId,
  useAnalysisRun,
  useAnalysisRuns,
  useCreateAnalysisRun,
  type AnalysisRunRequest,
} from "@/api/analytics";
import { usePortfolio, usePortfolioSummary } from "@/api/portfolios";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { DataAsOf } from "@/components/DataAsOf";
import { MetricTile } from "@/components/MetricTile";
import { Panel } from "@/components/Panel";
import { Select } from "@/components/Select";
import { Empty, Failed, Loading } from "@/components/states";
import { formatDateTime } from "@/lib/format";
import {
  indexResults,
  runParameters,
  TILE_GROUPS,
  unavailableResults,
  METRICS,
} from "@/lib/metrics";

import {
  AllocationChart,
  ComparisonChart,
  CorrelationChart,
  DrawdownChart,
  RiskContributionChart,
  RollingVolatilityChart,
  SectorChart,
  ValueChart,
} from "./parts/AnalyticsCharts";
import { AnalysisControls } from "./parts/AnalysisControls";
import { usePortfolioContext } from "./parts/portfolioContext";
import { RefreshMarketDataButton } from "./parts/RefreshMarketDataButton";

const STATUS_WORDS: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  succeeded: "Complete",
  partial: "Partial",
  failed: "Failed",
};

/**
 * The analytics dashboard.
 *
 * It shows one **stored** analysis run, chosen from this portfolio's history, so
 * what is on screen is exactly what a report of that run would contain. Changing
 * a parameter runs a new analysis; it never edits the one being displayed.
 *
 * Three run states are all first-class here, because on a risk screen the
 * difference matters more than anywhere else in the product:
 *
 * - `succeeded` — every metric computed.
 * - `partial` — some metrics could not be computed. The ones that did are shown,
 *   and the ones that did not are listed with the backend's reasons at the top.
 *   A partial run is not an error page: discarding twenty good metrics because
 *   two were unavailable would hide more than it protects.
 * - `failed` — the reason, and the parameters preserved so the run can be tried
 *   again without retyping them.
 */
export function PortfolioAnalyticsTab() {
  const { portfolioId, currency } = usePortfolioContext();
  const portfolio = usePortfolio(portfolioId);
  const summary = usePortfolioSummary(portfolioId);
  const runs = useAnalysisRuns(portfolioId);
  const create = useCreateAnalysisRun(portfolioId);

  const [chosenRunId, setChosenRunId] = useState<string | null>(null);
  const [showControls, setShowControls] = useState(false);

  const activeRunId = chosenRunId ?? newestRunId(runs.data);
  const run = useAnalysisRun(activeRunId);

  const runAnalysis = (body: AnalysisRunRequest) => {
    create.mutate(body, {
      onSuccess: (created) => {
        setChosenRunId(created.id);
        setShowControls(false);
      },
    });
  };

  if (runs.isPending) return <Loading label="Loading analyses" />;
  if (runs.isError) return <Failed error={runs.error} onRetry={() => void runs.refetch()} />;

  const history = runs.data.items;
  const parameters = runParameters(run.data);
  const results = indexResults(run.data);
  const unavailable = unavailableResults(run.data);
  const valueSeries = results["portfolio_value_series"];
  const holdings = summary.data?.holdings ?? [];

  /* --- Nothing has been analysed yet ------------------------------------- */
  if (history.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        <Panel>
          <Empty
            title="No analysis yet"
            body="An analysis measures return, volatility, drawdown and tail risk over a window you choose, and stores the result so it can be explained and reported later."
            action={
              <Button onClick={() => setShowControls(true)} disabled={showControls}>
                Choose a window
              </Button>
            }
          />
        </Panel>
        {showControls && (
          <Panel>
            <h2 className="text-ink mb-5 text-sm font-medium">Analysis parameters</h2>
            <AnalysisControls
              portfolioBenchmark={portfolio.data?.benchmark_symbol}
              pending={create.isPending}
              error={create.error}
              onRun={runAnalysis}
            />
          </Panel>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {/* --- Which run, and how to make another --------------------------- */}
      <Panel className="flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <Select
            label="Analysis run"
            value={activeRunId ?? ""}
            onChange={(event) => setChosenRunId(event.target.value)}
          >
            {history.map((item) => (
              <option key={item.id} value={item.id}>
                {formatDateTime(item.created_at)} — {STATUS_WORDS[item.status] ?? item.status}
              </option>
            ))}
          </Select>

          <Button
            variant="secondary"
            onClick={() => setShowControls((open) => !open)}
            aria-expanded={showControls}
          >
            {showControls ? "Hide parameters" : "New analysis"}
          </Button>
        </div>

        {showControls && (
          <div className="border-line-soft border-t pt-5">
            <AnalysisControls
              previous={parameters}
              portfolioBenchmark={portfolio.data?.benchmark_symbol}
              pending={create.isPending}
              error={create.error}
              onRun={runAnalysis}
            />
          </div>
        )}
      </Panel>

      {run.isPending ? (
        <Loading label="Loading analysis" />
      ) : run.isError ? (
        <Failed error={run.error} onRetry={() => void run.refetch()} />
      ) : (
        <>
          {/* --- What this run could not compute -------------------------- */}
          {run.data.status === "failed" && (
            <Alert title="This analysis failed">
              <p>{run.data.error_message ?? "The analysis could not be completed."}</p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() => setShowControls(true)}
              >
                Review the parameters and try again
              </Button>
            </Alert>
          )}

          {run.data.status === "partial" && unavailable.length > 0 && (
            <Alert tone="caution" title="Some metrics could not be computed">
              <p className="mb-2">
                Everything below was computed from the data available. These were not, and are
                shown as unavailable rather than as zero:
              </p>
              <ul className="flex flex-col gap-1.5">
                {unavailable.map((result) => (
                  <li key={result.metric}>
                    <span className="text-ink">
                      {METRICS[result.metric]?.label ?? result.metric}
                    </span>
                    {" — "}
                    {result.unavailable_reason ?? "no reason given"}
                  </li>
                ))}
              </ul>
            </Alert>
          )}

          {/* --- Provenance ----------------------------------------------- */}
          <Panel className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="hm-eyebrow mb-1">Analysis window</p>
                <p className="text-ink text-sm">
                  {parameters.start ?? "—"} → {parameters.end ?? "—"}
                </p>
              </div>
              <DataAsOf
                date={run.data.data_as_of}
                action={<RefreshMarketDataButton portfolioId={portfolioId} />}
              />
            </div>

            {run.data.notes.length > 0 && (
              <div className="border-line-soft border-t pt-4">
                <p className="hm-eyebrow mb-2">Assumptions</p>
                <ul className="text-ink-muted flex flex-col gap-2 text-xs leading-relaxed">
                  {run.data.notes.map((note) => (
                    <li key={note} className="flex gap-2">
                      <span aria-hidden="true" className="text-ink-faint">
                        —
                      </span>
                      <span>{note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>

          {/* --- Tiles ---------------------------------------------------- */}
          {TILE_GROUPS.map((group) => {
            const present = group.metrics.filter((metric) => results[metric] !== undefined);
            // A group with nothing in it is omitted rather than rendered as a
            // row of dashes: a portfolio with no benchmark has no benchmark
            // section, which is different from having one that failed.
            if (present.length === 0) return null;
            return (
              <section key={group.title} className="flex flex-col gap-4">
                <div>
                  <h2 className="font-display text-ink text-lg font-light">{group.title}</h2>
                  {group.blurb && <p className="text-ink-dim mt-1 text-xs">{group.blurb}</p>}
                </div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {present.map((metric) => (
                    <MetricTile
                      key={metric}
                      metric={metric}
                      result={results[metric]}
                      currency={currency}
                    />
                  ))}
                </div>
              </section>
            );
          })}

          {/* --- Charts --------------------------------------------------- */}
          <section className="flex flex-col gap-4">
            <h2 className="font-display text-ink text-lg font-light">Over the window</h2>
            <div className="grid gap-4">
              <ValueChart result={valueSeries} currency={currency} />
              {results["benchmark_comparison_series"] && (
                <ComparisonChart
                  result={results["benchmark_comparison_series"]}
                  currency={currency}
                />
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                <DrawdownChart result={valueSeries} currency={currency} />
                <RollingVolatilityChart
                  result={results["rolling_volatility"]}
                  currency={currency}
                />
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <h2 className="font-display text-ink text-lg font-light">Composition and risk</h2>
            <div className="grid gap-4 lg:grid-cols-2">
              {summary.isPending ? (
                <Loading label="Loading holdings" />
              ) : (
                <AllocationChart
                  holdings={holdings}
                  currency={currency}
                  dataAsOf={summary.data?.data_as_of}
                />
              )}
              <SectorChart result={results["largest_sector_weight"]} currency={currency} />
              <RiskContributionChart
                result={results["risk_contribution"]}
                currency={currency}
              />
              <CorrelationChart
                result={results["average_pairwise_correlation"]}
                currency={currency}
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
