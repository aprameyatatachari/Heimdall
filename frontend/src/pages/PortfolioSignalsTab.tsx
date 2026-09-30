import { useState } from "react";

import {
  useAcknowledgeSignal,
  useAlertRules,
  useAlertRuleTypes,
  useDeleteAlertRule,
  useDismissSignal,
  useMonitoringRuns,
  useProvisionDefaultRules,
  useRunMonitoring,
  useSignals,
  useSignalSummary,
  useUpdateAlertRule,
  type SignalFilters,
  type SignalSeverity,
  type SignalStatus,
} from "@/api/signals";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Panel } from "@/components/Panel";
import { SeverityCount } from "@/components/Severity";
import { Empty, Failed, Loading } from "@/components/states";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";
import { ruleLabel } from "@/lib/signalUnits";

import { AlertRuleEditor } from "./parts/AlertRuleEditor";
import { SignalCard } from "./parts/SignalCard";
import { SignalDetail } from "./parts/SignalDetail";
import { usePortfolioContext } from "./parts/portfolioContext";

const SEVERITY_ORDER: SignalSeverity[] = ["critical", "high", "elevated", "informational"];

const STATUS_FILTERS: { value: SignalStatus; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
];

/**
 * Gjallarhorn — the Early Warning System.
 *
 * The only screen where the Gjallarhorn name and the horn mark belong, and even
 * here the branded term always sits beside the conventional one. A reader who
 * has never heard of it still reads "High position concentration" and a sentence
 * saying which holding, what share, and which threshold it passed.
 *
 * Three things this screen deliberately does not do: it never presents a signal
 * as a prediction, it never offers a control to mark an active condition
 * resolved, and it never hides what monitoring failed to evaluate. A rule that
 * could not be checked resolves nothing — not being able to look is not evidence
 * that the condition cleared.
 */
export function PortfolioSignalsTab() {
  const { portfolioId } = usePortfolioContext();

  const [filters, setFilters] = useState<SignalFilters>({ status: ["active", "acknowledged"] });
  const [openSignalId, setOpenSignalId] = useState<string | null>(null);
  const [confirmingDismiss, setConfirmingDismiss] = useState<string | null>(null);
  const [showRules, setShowRules] = useState(false);

  const summary = useSignalSummary(portfolioId);
  const signals = useSignals(portfolioId, filters);
  const ruleTypes = useAlertRuleTypes();
  const rules = useAlertRules(portfolioId);
  const monitoringRuns = useMonitoringRuns(portfolioId);

  const acknowledge = useAcknowledgeSignal(portfolioId);
  const dismiss = useDismissSignal(portfolioId);
  const updateRule = useUpdateAlertRule(portfolioId);
  const deleteRule = useDeleteAlertRule(portfolioId);
  const provisionDefaults = useProvisionDefaultRules(portfolioId);
  const runMonitoring = useRunMonitoring(portfolioId);

  const toggleSeverity = (severity: SignalSeverity) => {
    setFilters((current) => {
      const selected = current.severity ?? [];
      const next = selected.includes(severity)
        ? selected.filter((item) => item !== severity)
        : [...selected, severity];
      return { ...current, severity: next.length > 0 ? next : undefined };
    });
  };

  const toggleStatus = (status: SignalStatus) => {
    setFilters((current) => {
      const selected = current.status ?? [];
      const next = selected.includes(status)
        ? selected.filter((item) => item !== status)
        : [...selected, status];
      return { ...current, status: next.length > 0 ? next : undefined };
    });
  };

  const latestRun = monitoringRuns.data?.items[0];
  const counts = summary.data?.by_severity ?? {};

  return (
    <div className="flex flex-col gap-8">
      {/* --- Summary ------------------------------------------------------ */}
      <Panel className="flex flex-col gap-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-ink text-lg font-light">
              Gjallarhorn Signals
              <span className="text-ink-dim ms-3 text-sm">Early warnings</span>
            </h2>
            <p className="text-ink-muted mt-1 max-w-prose text-xs leading-relaxed">
              Each signal describes a condition observed in this portfolio, with the value that
              was measured and the threshold you set for it. None of them is a prediction, and
              none of them is advice.
            </p>
          </div>

          <Button
            variant="secondary"
            onClick={() => runMonitoring.mutate()}
            loading={runMonitoring.isPending}
          >
            Run monitoring now
          </Button>
        </div>

        {summary.isPending ? (
          <Loading label="Loading signal summary" className="py-6" />
        ) : summary.isError ? (
          <Failed error={summary.error} onRetry={() => void summary.refetch()} />
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {SEVERITY_ORDER.map((severity) => (
                <SeverityCount
                  key={severity}
                  severity={severity}
                  count={counts[severity] ?? 0}
                  selected={(filters.severity ?? []).includes(severity)}
                  onClick={() => toggleSeverity(severity)}
                />
              ))}
            </div>
            <p className="text-ink-dim text-xs">
              {summary.data.total_open === 0
                ? "No open signals. Monitoring records the current state each time it runs."
                : `${summary.data.total_open} open ${summary.data.total_open === 1 ? "signal" : "signals"} in total.`}
            </p>
          </>
        )}

        {runMonitoring.data && (
          <MonitoringOutcome
            status={runMonitoring.data.status}
            evaluated={runMonitoring.data.rules_evaluated}
            failed={runMonitoring.data.rules_failed}
            created={runMonitoring.data.signals_created}
            updated={runMonitoring.data.signals_updated}
            resolved={runMonitoring.data.signals_resolved}
            failures={runMonitoring.data.rule_results
              .filter((result) => result.status === "failed")
              .map(
                (result) =>
                  `${ruleLabel(result.rule_type)}: ${result.error ?? "no reason given"}`,
              )}
          />
        )}

        {latestRun && !runMonitoring.data && (
          <p className="text-ink-dim text-xs">
            Last monitored {formatDateTime(latestRun.started_at)} — {latestRun.rules_evaluated}{" "}
            rules evaluated
            {latestRun.rules_failed > 0 ? `, ${latestRun.rules_failed} failed` : ""}.
          </p>
        )}
      </Panel>

      {/* --- Filters ------------------------------------------------------ */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="hm-eyebrow me-2">Status</span>
        {STATUS_FILTERS.map((option) => {
          const selected = (filters.status ?? []).includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => toggleStatus(option.value)}
              aria-pressed={selected}
              className={cx(
                "rounded-full border px-3 py-1.5 text-xs transition-colors",
                selected
                  ? "border-gold text-gold"
                  : "border-line-strong text-ink-muted hover:text-ink",
              )}
            >
              {option.label}
            </button>
          );
        })}
        {(filters.severity ?? []).length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFilters((current) => ({ ...current, severity: undefined }))}
          >
            Clear severity filter
          </Button>
        )}
      </div>

      {/* --- Signals ------------------------------------------------------ */}
      {signals.isPending ? (
        <Loading label="Loading signals" />
      ) : signals.isError ? (
        <Failed error={signals.error} onRetry={() => void signals.refetch()} />
      ) : signals.data.items.length === 0 ? (
        <Panel>
          <Empty
            title="No signals match these filters"
            body="A portfolio with no open signals is a portfolio where no rule's threshold is currently crossed. Resolved and dismissed signals stay available through the filters above."
          />
        </Panel>
      ) : (
        <ul className="flex flex-col gap-4">
          {signals.data.items.map((signal) => (
            <SignalCard
              key={signal.id}
              signal={signal}
              onOpen={() => setOpenSignalId(signal.id)}
              onAcknowledge={() => acknowledge.mutate(signal.id)}
              acknowledging={acknowledge.isPending && acknowledge.variables === signal.id}
            />
          ))}
        </ul>
      )}

      {/* --- Rules -------------------------------------------------------- */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="font-display text-ink text-lg font-light">Alert rules</h2>
          <div className="flex flex-wrap gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowRules((open) => !open)}
              aria-expanded={showRules}
            >
              {showRules ? "Hide rules" : "Show rules"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => provisionDefaults.mutate(false)}
              loading={provisionDefaults.isPending}
            >
              Add any missing rules
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => provisionDefaults.mutate(true)}
              loading={provisionDefaults.isPending}
            >
              Restore defaults
            </Button>
          </div>
        </div>

        {showRules &&
          (rules.isPending || ruleTypes.isPending ? (
            <Loading label="Loading rules" />
          ) : rules.isError ? (
            <Failed error={rules.error} onRetry={() => void rules.refetch()} />
          ) : rules.data.length === 0 ? (
            <Panel>
              <Empty
                title="No rules yet"
                body="Rules are not created with the portfolio, so an empty portfolio is never evaluated before it has holdings. Add the documented set when you are ready."
                action={
                  <Button onClick={() => provisionDefaults.mutate(false)}>
                    Add the default rules
                  </Button>
                }
              />
            </Panel>
          ) : (
            <ul className="flex flex-col gap-3">
              {rules.data.map((rule) => (
                <AlertRuleEditor
                  key={rule.id}
                  rule={rule}
                  catalogueItem={ruleTypes.data?.items.find(
                    (item) => item.rule_type === rule.rule_type,
                  )}
                  saving={updateRule.isPending && updateRule.variables?.ruleId === rule.id}
                  error={updateRule.variables?.ruleId === rule.id ? updateRule.error : null}
                  onSave={(body) => updateRule.mutate({ ruleId: rule.id, body })}
                  onDelete={() => deleteRule.mutate(rule.id)}
                />
              ))}
            </ul>
          ))}
      </section>

      {/* --- Monitoring history ------------------------------------------- */}
      {monitoringRuns.data && monitoringRuns.data.items.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="font-display text-ink text-lg font-light">Monitoring history</h2>
          <Panel className="overflow-x-auto p-0">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-line-strong border-b">
                  {[
                    "Run",
                    "Trigger",
                    "Status",
                    "Evaluated",
                    "Failed",
                    "Created",
                    "Resolved",
                  ].map((column, index) => (
                    <th
                      key={column}
                      scope="col"
                      className={cx(
                        "hm-eyebrow px-4 py-3",
                        index >= 3 ? "text-end" : "text-start",
                      )}
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {monitoringRuns.data.items.map((item) => (
                  <tr key={item.id} className="border-line-soft border-b last:border-b-0">
                    <td className="text-ink-muted px-4 py-3">
                      {formatDateTime(item.started_at)}
                    </td>
                    <td className="text-ink-muted px-4 py-3 capitalize">{item.trigger_type}</td>
                    <td
                      className={cx(
                        "px-4 py-3 capitalize",
                        item.status === "partial" ? "text-caution" : "text-ink-muted",
                      )}
                    >
                      {item.status}
                    </td>
                    <td className="hm-numeric text-ink px-4 py-3 text-end">
                      {item.rules_evaluated}
                    </td>
                    <td
                      className={cx(
                        "hm-numeric px-4 py-3 text-end",
                        item.rules_failed > 0 ? "text-caution" : "text-ink-dim",
                      )}
                    >
                      {item.rules_failed}
                    </td>
                    <td className="hm-numeric text-ink px-4 py-3 text-end">
                      {item.signals_created}
                    </td>
                    <td className="hm-numeric text-ink px-4 py-3 text-end">
                      {item.signals_resolved}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </section>
      )}

      <SignalDetail
        signalId={openSignalId}
        onClose={() => setOpenSignalId(null)}
        onAcknowledge={(id) => acknowledge.mutate(id)}
        onDismiss={(id) => setConfirmingDismiss(id)}
        acknowledging={acknowledge.isPending}
        dismissing={dismiss.isPending}
      />

      <ConfirmDialog
        open={confirmingDismiss !== null}
        onClose={() => setConfirmingDismiss(null)}
        onConfirm={() => {
          if (confirmingDismiss) {
            dismiss.mutate(confirmingDismiss, { onSuccess: () => setOpenSignalId(null) });
          }
          setConfirmingDismiss(null);
        }}
        title="Dismiss this signal?"
        confirmLabel="Dismiss"
        pending={dismiss.isPending}
      >
        <p className="text-ink-muted text-sm leading-relaxed">
          Dismissing hides the signal. It does not mean the condition has cleared — if the same
          condition is observed again, a new signal is raised.
        </p>
      </ConfirmDialog>
    </div>
  );
}

/**
 * What a monitoring run did.
 *
 * A partial run lists the rules that failed **and** keeps the results of the
 * ones that succeeded. Hiding twelve good evaluations because one rule threw
 * would be the opposite of an early warning system.
 */
function MonitoringOutcome({
  status,
  evaluated,
  failed,
  created,
  updated,
  resolved,
  failures,
}: {
  status: string;
  evaluated: number;
  failed: number;
  created: number;
  updated: number;
  resolved: number;
  failures: string[];
}) {
  const tone = status === "partial" || failed > 0 ? "caution" : "info";
  return (
    <Alert
      tone={tone}
      title={status === "partial" ? "Monitoring ran, partly" : "Monitoring ran"}
    >
      <p>
        {evaluated} rules evaluated, {created} signals raised, {updated} updated, {resolved}{" "}
        resolved.
      </p>
      {failures.length > 0 && (
        <>
          <p className="mt-2">
            {failed} {failed === 1 ? "rule" : "rules"} could not be evaluated. Nothing they
            cover was resolved, because not being able to check a condition is not evidence that
            it cleared:
          </p>
          <ul className="mt-1 flex flex-col gap-1">
            {failures.map((failure) => (
              <li key={failure}>{failure}</li>
            ))}
          </ul>
        </>
      )}
    </Alert>
  );
}
