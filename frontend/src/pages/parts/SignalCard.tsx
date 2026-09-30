import type { WarningSignalResponse } from "@/api/types";
import { Button } from "@/components/Button";
import { SeverityBadge } from "@/components/Severity";
import { cx } from "@/lib/cx";
import { formatDate, formatDateTime } from "@/lib/format";
import { formatSignalValue, ruleLabel, unitDescription } from "@/lib/signalUnits";

const STATUS_WORDS: Record<string, string> = {
  active: "Active",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
  dismissed: "Dismissed",
};

/**
 * Observed against threshold.
 *
 * Two similar numbers side by side with no labels is the failure mode this
 * exists to prevent: "34.2% / 30%" says nothing about which is the portfolio and
 * which is the line it crossed. Each is labelled, and the observed value is the
 * one given weight.
 */
export function ObservedVersusThreshold({
  observed,
  threshold,
  unit,
  className,
}: {
  observed: string | null;
  threshold: string | null;
  unit: string;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-end gap-x-8 gap-y-3", className)}>
      <div>
        <p className="hm-eyebrow mb-1">Observed</p>
        <p className="hm-numeric text-ink text-lg">{formatSignalValue(observed, unit)}</p>
      </div>
      <div>
        <p className="hm-eyebrow mb-1">Your threshold</p>
        <p className="hm-numeric text-ink-muted text-lg">
          {formatSignalValue(threshold, unit)}
        </p>
      </div>
      <p className="text-ink-dim pb-1 text-xs">{unitDescription(unit)}</p>
    </div>
  );
}

/**
 * One Gjallarhorn Signal in a list.
 *
 * The branded term appears beside the conventional one, never instead of it: a
 * reader who has never heard of Gjallarhorn still reads "High position
 * concentration" and the sentence explaining it. AGENTS.md section 6.9.
 *
 * Acknowledging is offered here; resolving is not offered anywhere. A signal
 * resolves when its condition stops being observed, and a control that let
 * someone mark an active condition resolved would be a control for hiding risk.
 */
export function SignalCard({
  signal,
  onOpen,
  onAcknowledge,
  acknowledging,
}: {
  signal: WarningSignalResponse;
  onOpen: () => void;
  onAcknowledge: () => void;
  acknowledging: boolean;
}) {
  const open = signal.status === "active" || signal.status === "acknowledged";

  return (
    <li className="hm-panel flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <SeverityBadge severity={signal.severity} />
            <span className="text-ink-dim text-2xs tracking-[0.2em] uppercase">
              Gjallarhorn Signal
            </span>
            <span
              className={cx(
                "text-2xs rounded-full border px-2 py-0.5 uppercase",
                signal.status === "resolved"
                  ? "border-positive text-positive"
                  : signal.status === "dismissed"
                    ? "border-line-strong text-ink-dim"
                    : "border-line-strong text-ink-muted",
              )}
            >
              {STATUS_WORDS[signal.status] ?? signal.status}
            </span>
          </div>
          <h3 className="text-ink text-base">{signal.title}</h3>
          {/* Some rules title their signal after themselves — "Stale market
              data" under the stale-market-data rule — and printing both said
              the same thing twice. */}
          {ruleLabel(signal.signal_type).toLowerCase() !== signal.title.toLowerCase() && (
            <p className="text-ink-dim mt-1 text-xs">{ruleLabel(signal.signal_type)}</p>
          )}
        </div>
      </div>

      <p className="text-ink-muted max-w-prose text-sm leading-relaxed">{signal.explanation}</p>

      <ObservedVersusThreshold
        observed={signal.observed_value}
        threshold={signal.threshold_value}
        unit={signal.unit}
      />

      <div className="text-ink-dim flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <span>Metric: {signal.metric_name}</span>
        <span>Period: {signal.analysis_period}</span>
        <span>
          Data as of {signal.data_as_of ? formatDate(signal.data_as_of) : "no market data"}
        </span>
        <span>First seen {formatDateTime(signal.first_triggered_at)}</span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" onClick={onOpen}>
          Details
          <span className="sr-only"> of {signal.title}</span>
        </Button>
        {open && signal.acknowledged_at === null && (
          <Button variant="ghost" size="sm" onClick={onAcknowledge} loading={acknowledging}>
            Acknowledge
            <span className="sr-only"> {signal.title}</span>
          </Button>
        )}
        {signal.acknowledged_at !== null && signal.status !== "resolved" && (
          <span className="text-ink-dim text-xs">
            Acknowledged {formatDateTime(signal.acknowledged_at)} — the condition is still
            present
          </span>
        )}
      </div>
    </li>
  );
}
