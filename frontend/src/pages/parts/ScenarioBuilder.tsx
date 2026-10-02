import { useState } from "react";

import type { ScenarioCatalogueItem, ShockTargetType, StressTestRequest } from "@/api/stress";
import { useRefreshMarketData, type HoldingSummary } from "@/api/portfolios";
import { ApiError } from "@/api/errors";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { Select } from "@/components/Select";

import { CoverageWarning } from "./CoverageWarning";
import { Panel } from "@/components/Panel";
import { cx } from "@/lib/cx";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";
import {
  duplicateTargets,
  PRECEDENCE_EXPLANATION,
  resolveShock,
  shockSource,
  type Shock,
} from "@/lib/shocks";

/** A shock as the form holds it: percentages as typed, not yet parsed. */
interface DraftShock {
  id: number;
  target_type: ShockTargetType;
  target: string;
  /** Percent, as typed. "-20" means a 20% fall. */
  percent: string;
}

let nextId = 1;

function emptyShock(target_type: ShockTargetType = "portfolio"): DraftShock {
  return { id: nextId++, target_type, target: "", percent: "" };
}

function parsePercent(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const numeric = Number(trimmed);
  if (!Number.isFinite(numeric)) return null;
  return numeric / 100;
}

/**
 * Choose a scenario, or build one.
 *
 * Nothing runs until the user has seen what it assumes. A historical scenario
 * shows its window and what it replays; a custom one shows the shock that will
 * actually apply to each holding, resolved by the same precedence the engine
 * uses. Precedence is stated on screen rather than left to be discovered, which
 * is the difference between a tool and a trap. AGENTS.md section 6.8.
 */
export function ScenarioBuilder({
  portfolioId,
  scenarios,
  limitations,
  holdings,
  currency,
  pending,
  error,
  onRun,
}: {
  portfolioId: string;
  scenarios: ScenarioCatalogueItem[];
  limitations: string[];
  holdings: HoldingSummary[];
  currency: string;
  pending: boolean;
  error: unknown;
  onRun: (body: StressTestRequest) => void;
}) {
  const [mode, setMode] = useState<"historical" | "custom">("historical");
  const [scenarioKey, setScenarioKey] = useState(scenarios[0]?.key ?? "");
  const [name, setName] = useState("Custom scenario");
  // Seeded with a market-wide shock, which is the scenario most people want
  // first and the one that makes precedence visible once they add a second.
  const [shocks, setShocks] = useState<DraftShock[]>([emptyShock("portfolio")]);

  const chosen = scenarios.find((item) => item.key === scenarioKey);
  const fetchPrices = useRefreshMarketData(portfolioId);

  // The one failure with an obvious next step: a historical scenario's own
  // window has no stored prices. Saying "refresh and try again" and leaving
  // someone to work out which dates is a dead end with instructions attached.
  //
  // Historical only. A custom scenario has no window of its own to fetch, and
  // offering the catalogue's would be offering to fix a scenario the user is
  // not running.
  const missingData =
    mode === "historical" &&
    error instanceof ApiError &&
    error.code === "scenario_data_unavailable";

  const parsed: Shock[] = shocks.flatMap((shock) => {
    const value = parsePercent(shock.percent);
    if (value === null) return [];
    if (shock.target_type !== "portfolio" && !shock.target.trim()) return [];
    return [
      {
        target_type: shock.target_type,
        target: shock.target_type === "portfolio" ? null : shock.target.trim(),
        value,
      },
    ];
  });

  const duplicates = duplicateTargets(parsed);
  const incomplete = shocks.length !== parsed.length;
  const canRunCustom = parsed.length > 0 && duplicates.length === 0 && !incomplete;

  const update = (id: number, patch: Partial<DraftShock>) => {
    setShocks((current) =>
      current.map((shock) => (shock.id === id ? { ...shock, ...patch } : shock)),
    );
  };

  const submit = () => {
    if (mode === "historical") {
      if (scenarioKey) onRun({ scenario_key: scenarioKey });
      return;
    }
    onRun({
      custom: {
        name: name.trim() || "Custom scenario",
        shocks: parsed.map((shock) => ({
          target_type: shock.target_type,
          target: shock.target ?? null,
          shock_type: "relative_price",
          // A decimal string: the API takes a Decimal, and a float literal here
          // would arrive as 0.30000000000000004 often enough to matter.
          value: shock.value.toFixed(6),
        })),
      },
    });
  };

  return (
    <Panel className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Scenario type">
        {(["historical", "custom"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setMode(option)}
            aria-pressed={mode === option}
            className={cx(
              "rounded-md border px-4 py-2 text-sm transition-colors",
              mode === option
                ? "border-gold text-gold"
                : "border-line-strong text-ink-muted hover:text-ink",
            )}
          >
            {option === "historical" ? "Historical scenario" : "Build a scenario"}
          </button>
        ))}
      </div>

      {mode === "historical" ? (
        <div className="flex flex-col gap-4">
          <Select
            label="Scenario"
            value={scenarioKey}
            onChange={(event) => setScenarioKey(event.target.value)}
            className="max-w-lg"
          >
            {scenarios.map((item) => (
              <option key={item.key} value={item.key}>
                {item.name}
              </option>
            ))}
          </Select>

          {chosen && (
            <div className="border-line-soft bg-surface-2 rounded-md border p-4">
              <p className="hm-eyebrow mb-2">What this replays</p>
              <p className="text-ink-muted text-sm leading-relaxed">{chosen.description}</p>
              <p className="text-ink-dim mt-3 text-xs">
                {/* The catalogue's own `window` is the same two dates unformatted,
                    so printing both said everything twice. */}
                {formatDate(chosen.start)} → {formatDate(chosen.end)}
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <Field
            label="Scenario name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            className="max-w-lg"
          />

          <div className="flex flex-col gap-3">
            <p className="hm-eyebrow">Shocks</p>
            {shocks.map((shock) => (
              <div key={shock.id} className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-ink-dim text-xs">Applies to</span>
                  <select
                    value={shock.target_type}
                    onChange={(event) =>
                      update(shock.id, {
                        target_type: event.target.value as ShockTargetType,
                        target: "",
                      })
                    }
                    aria-label="Shock applies to"
                    className="border-line bg-surface-2 text-ink focus:border-gold h-10 rounded-md border px-3 text-sm outline-none"
                  >
                    <option value="portfolio">Whole portfolio</option>
                    <option value="sector">A sector</option>
                    <option value="symbol">One holding</option>
                  </select>
                </label>

                {shock.target_type !== "portfolio" && (
                  <label className="flex flex-col gap-1.5">
                    <span className="text-ink-dim text-xs">
                      {shock.target_type === "symbol" ? "Symbol" : "Sector"}
                    </span>
                    <input
                      value={shock.target}
                      onChange={(event) => update(shock.id, { target: event.target.value })}
                      aria-label={shock.target_type === "symbol" ? "Symbol" : "Sector"}
                      className="border-line bg-surface-2 text-ink focus:border-gold h-10 w-40 rounded-md border px-3 text-sm outline-none"
                    />
                  </label>
                )}

                <label className="flex flex-col gap-1.5">
                  <span className="text-ink-dim text-xs">Price change</span>
                  <div className="border-line bg-surface-2 focus-within:border-gold flex h-10 items-center rounded-md border px-3">
                    <input
                      value={shock.percent}
                      onChange={(event) => update(shock.id, { percent: event.target.value })}
                      inputMode="decimal"
                      placeholder="-20"
                      aria-label="Price change percent"
                      className="text-ink w-20 bg-transparent text-sm outline-none"
                    />
                    <span className="text-ink-dim text-sm">%</span>
                  </div>
                </label>

                {shocks.length > 1 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setShocks((current) => current.filter((item) => item.id !== shock.id))
                    }
                  >
                    Remove
                    <span className="sr-only"> this shock</span>
                  </Button>
                )}
              </div>
            ))}

            <div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShocks((current) => [...current, emptyShock("symbol")])}
              >
                Add a shock
              </Button>
            </div>
          </div>

          <Alert tone="info" title="How overlapping shocks resolve">
            {PRECEDENCE_EXPLANATION}
          </Alert>

          {duplicates.length > 0 && (
            <Alert title="Two shocks target the same thing">
              {duplicates.join(", ")} is shocked more than once. Which one applies would be
              ambiguous, so remove one before running.
            </Alert>
          )}

          <ResolvedShocks holdings={holdings} shocks={parsed} currency={currency} />
        </div>
      )}

      {/* Before the run, not after it: a scenario over a window some holdings
          do not cover still draws its charts, of the holdings that are. */}
      {mode === "historical" && chosen && !missingData && (
        <CoverageWarning
          portfolioId={portfolioId}
          start={chosen.start}
          end={chosen.end}
          what="scenario"
        />
      )}

      {limitations.length > 0 && (
        <div className="border-line-soft border-t pt-4">
          <p className="hm-eyebrow mb-2">Before you run this</p>
          <ul className="text-ink-muted flex flex-col gap-2 text-xs leading-relaxed">
            {limitations.map((item) => (
              <li key={item} className="flex gap-2">
                <span aria-hidden="true" className="text-ink-faint">
                  —
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {missingData && chosen ? (
        <Alert tone="caution" title="This scenario's prices are not stored yet">
          <p>
            A historical scenario replays the returns observed in its own window, and this
            portfolio has no prices covering {formatDate(chosen.start)} to{" "}
            {formatDate(chosen.end)}. Fetching them is one step, and then the scenario can run.
          </p>
          <Button
            size="sm"
            className="mt-3"
            loading={fetchPrices.isPending}
            onClick={() =>
              fetchPrices.mutate(
                { start: chosen.start, end: chosen.end },
                // Run it straight away: being sent back to press the same
                // button again would be a second step for no decision.
                { onSuccess: () => onRun({ scenario_key: chosen.key }) },
              )
            }
          >
            Fetch prices for this period and run
          </Button>
        </Alert>
      ) : (
        error !== null &&
        error !== undefined && (
          <Alert title="The scenario could not be run">
            {error instanceof Error ? error.message : "Something went wrong."}
          </Alert>
        )
      )}

      <div>
        <Button
          onClick={submit}
          loading={pending}
          disabled={mode === "custom" ? !canRunCustom : !scenarioKey}
        >
          Run this scenario
        </Button>
      </div>
    </Panel>
  );
}

/**
 * What each holding will actually receive.
 *
 * Shown before the run, not after: the precedence rule is only useful if it can
 * be checked while the scenario is still being written.
 */
function ResolvedShocks({
  holdings,
  shocks,
  currency,
}: {
  holdings: HoldingSummary[];
  shocks: Shock[];
  currency: string;
}) {
  if (holdings.length === 0) return null;

  return (
    <div className="border-line-soft rounded-md border">
      <p className="hm-eyebrow border-line-soft border-b px-4 py-3">
        The shock each holding will receive
      </p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-line-soft border-b">
            <th scope="col" className="hm-eyebrow px-4 py-2 text-start">
              Holding
            </th>
            <th scope="col" className="hm-eyebrow px-4 py-2 text-start">
              Sector
            </th>
            <th scope="col" className="hm-eyebrow px-4 py-2 text-end">
              Market value
            </th>
            <th scope="col" className="hm-eyebrow px-4 py-2 text-end">
              Shock applied
            </th>
            <th scope="col" className="hm-eyebrow px-4 py-2 text-start">
              From
            </th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((holding) => {
            const shock = resolveShock(holding.symbol, holding.sector, shocks);
            return (
              <tr key={holding.symbol} className="border-line-soft border-b last:border-b-0">
                <td className="text-ink px-4 py-2">{holding.symbol}</td>
                <td className="text-ink-muted px-4 py-2">{holding.sector}</td>
                <td className="hm-numeric text-ink-muted px-4 py-2 text-end">
                  {formatMoney(holding.market_value, currency)}
                </td>
                <td className="hm-numeric px-4 py-2 text-end">
                  {shock === null ? (
                    <span className="text-ink-faint">no shock</span>
                  ) : (
                    <span className={shock.value < 0 ? "text-negative" : "text-positive"}>
                      {formatPercent(shock.value, { signed: true })}
                    </span>
                  )}
                </td>
                <td className="text-ink-dim px-4 py-2 text-xs">
                  {shock === null ? "—" : shockSource(shock)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
