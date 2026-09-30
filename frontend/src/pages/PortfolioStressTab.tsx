import { useState } from "react";

import { usePortfolioSummary } from "@/api/portfolios";
import {
  newestStressRunId,
  useRunStressTest,
  useScenarioCatalogue,
  useStressRun,
  useStressRuns,
  type StressTestRequest,
} from "@/api/stress";
import { Alert } from "@/components/Alert";
import { Panel } from "@/components/Panel";
import { Select } from "@/components/Select";
import { Failed, Loading } from "@/components/states";
import { formatDateTime } from "@/lib/format";

import { ScenarioBuilder } from "./parts/ScenarioBuilder";
import { StressResult } from "./parts/StressResult";
import { usePortfolioContext } from "./parts/portfolioContext";

/**
 * Stress testing.
 *
 * A stress test asks one question — if these prices moved this way, what would
 * this portfolio be worth — and the screen is built so the question is fully
 * visible before it is answered. The scenario, its window, its limitations and
 * the shock each holding will receive are all on screen before the run button
 * does anything.
 *
 * The builder keeps its own state across a failed run, so a rejected scenario
 * comes back exactly as it was typed rather than as an empty form.
 */
export function PortfolioStressTab() {
  const { portfolioId, currency } = usePortfolioContext();
  const catalogue = useScenarioCatalogue();
  const summary = usePortfolioSummary(portfolioId);
  const runs = useStressRuns(portfolioId);
  const start = useRunStressTest(portfolioId);

  const [chosenRunId, setChosenRunId] = useState<string | null>(null);
  const activeRunId = chosenRunId ?? newestStressRunId(runs.data);
  const run = useStressRun(activeRunId);

  const runScenario = (body: StressTestRequest) => {
    start.mutate(body, { onSuccess: (created) => setChosenRunId(created.id) });
  };

  if (catalogue.isPending || runs.isPending) return <Loading label="Loading stress tests" />;
  if (catalogue.isError) {
    return <Failed error={catalogue.error} onRetry={() => void catalogue.refetch()} />;
  }
  if (runs.isError) return <Failed error={runs.error} onRetry={() => void runs.refetch()} />;

  const history = runs.data.items;

  return (
    <div className="flex flex-col gap-8">
      <ScenarioBuilder
        scenarios={catalogue.data.items}
        limitations={catalogue.data.limitations ?? []}
        holdings={summary.data?.holdings ?? []}
        currency={currency}
        pending={start.isPending}
        error={start.error}
        onRun={runScenario}
      />

      {history.length === 0 ? (
        <Panel>
          <p className="text-ink-muted text-sm leading-relaxed">
            No scenario has been run against this portfolio yet. Choose one above to see what it
            would have implied for the holdings as they stand today.
          </p>
        </Panel>
      ) : (
        <>
          <Panel className="flex flex-wrap items-end justify-between gap-4">
            <Select
              label="Stress test"
              value={activeRunId ?? ""}
              onChange={(event) => setChosenRunId(event.target.value)}
            >
              {history.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.scenario_name} — {formatDateTime(item.created_at)}
                </option>
              ))}
            </Select>
          </Panel>

          {run.isPending ? (
            <Loading label="Loading result" />
          ) : run.isError ? (
            <Failed error={run.error} onRetry={() => void run.refetch()} />
          ) : run.data.status === "failed" ? (
            <Alert title="This scenario could not be completed">
              The scenario did not produce a result. Your inputs are still in the builder above,
              so it can be adjusted and run again.
            </Alert>
          ) : (
            <StressResult run={run.data} />
          )}
        </>
      )}
    </div>
  );
}
