import { Link } from "react-router-dom";

import { useSignal } from "@/api/signals";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";
import { SeverityBadge } from "@/components/Severity";
import { Failed, Loading } from "@/components/states";
import { formatDate, formatDateTime } from "@/lib/format";
import { formatSignalValue, ruleLabel } from "@/lib/signalUnits";

import { ObservedVersusThreshold } from "./SignalCard";

const EVENT_WORDS: Record<string, string> = {
  created: "Signal raised",
  severity_changed: "Severity changed",
  status_changed: "Status changed",
  reoccurred: "Condition observed again",
  acknowledged: "Acknowledged",
  dismissed: "Dismissed",
  resolved: "Condition cleared",
  updated: "Observation updated",
};

/** Context values are heterogeneous JSON; render what is readable, skip the rest. */
function readableContext(context: unknown): [string, string][] {
  if (!context || typeof context !== "object") return [];
  return Object.entries(context as Record<string, unknown>).flatMap(([key, value]) => {
    if (value === null || value === undefined) return [];
    if (typeof value === "object") return [];
    return [[key.replace(/_/g, " "), String(value)] as [string, string]];
  });
}

/**
 * One signal, in full.
 *
 * Everything the list shows, plus the context that produced it and the
 * append-only trail of every severity and status change. The trail matters: a
 * signal that has been open for a month at rising severity is a different fact
 * from one raised this morning, and only the history says which.
 *
 * Dismissing is behind a confirmation and is described honestly — it hides the
 * signal, it does not mean the condition has cleared.
 */
export function SignalDetail({
  signalId,
  onClose,
  onAcknowledge,
  onDismiss,
  acknowledging,
  dismissing,
}: {
  signalId: string | null;
  onClose: () => void;
  onAcknowledge: (signalId: string) => void;
  onDismiss: (signalId: string) => void;
  acknowledging: boolean;
  dismissing: boolean;
}) {
  const signal = useSignal(signalId);
  const data = signal.data;

  return (
    <Dialog
      open={signalId !== null}
      onClose={onClose}
      size="lg"
      title={data?.title ?? "Signal"}
      description={
        // Several rules title their signal after themselves, and a dialog whose
        // subtitle repeats its heading is noise.
        data && ruleLabel(data.signal_type).toLowerCase() !== data.title.toLowerCase()
          ? ruleLabel(data.signal_type)
          : undefined
      }
      footer={
        data && data.status !== "resolved" && data.status !== "dismissed" ? (
          <div className="flex flex-wrap justify-end gap-3">
            <Button
              variant="danger"
              size="sm"
              loading={dismissing}
              onClick={() => onDismiss(data.id)}
            >
              Dismiss
            </Button>
            {data.acknowledged_at === null && (
              <Button size="sm" loading={acknowledging} onClick={() => onAcknowledge(data.id)}>
                Acknowledge
              </Button>
            )}
          </div>
        ) : null
      }
    >
      {signal.isPending ? (
        <Loading label="Loading signal" />
      ) : signal.isError ? (
        <Failed error={signal.error} />
      ) : (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center gap-4">
            <SeverityBadge severity={signal.data.severity} />
            <span className="text-ink-dim text-xs">
              Raised {formatDateTime(signal.data.first_triggered_at)} · last observed{" "}
              {formatDateTime(signal.data.last_triggered_at)}
            </span>
          </div>

          <p className="text-ink-muted text-sm leading-relaxed">{signal.data.explanation}</p>

          <ObservedVersusThreshold
            observed={signal.data.observed_value}
            threshold={signal.data.threshold_value}
            unit={signal.data.unit}
          />

          <div className="border-line-soft grid gap-4 border-t pt-4 text-xs sm:grid-cols-2">
            <div>
              <p className="hm-eyebrow mb-1">Metric</p>
              <p className="text-ink-muted">{signal.data.metric_name}</p>
            </div>
            <div>
              <p className="hm-eyebrow mb-1">Analysis period</p>
              <p className="text-ink-muted">{signal.data.analysis_period}</p>
            </div>
            <div>
              <p className="hm-eyebrow mb-1">Data as of</p>
              <p className="text-ink-muted">
                {signal.data.data_as_of
                  ? formatDate(signal.data.data_as_of)
                  : "no market data yet"}
              </p>
            </div>
            <div>
              <p className="hm-eyebrow mb-1">Status</p>
              <p className="text-ink-muted capitalize">{signal.data.status}</p>
            </div>
          </div>

          {readableContext(signal.data.context).length > 0 && (
            <div className="border-line-soft border-t pt-4">
              <p className="hm-eyebrow mb-2">What it applies to</p>
              <dl className="grid gap-2 text-xs sm:grid-cols-2">
                {readableContext(signal.data.context).map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <dt className="text-ink-dim capitalize">{key}:</dt>
                    <dd className="text-ink-muted">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          <div className="border-line-soft border-t pt-4">
            <p className="hm-eyebrow mb-2">A reasonable next step</p>
            <p className="text-ink-muted text-sm leading-relaxed">
              {signal.data.suggested_action}
            </p>
          </div>

          {(signal.data.limitations ?? []).length > 0 && (
            <div className="border-line-soft border-t pt-4">
              <p className="hm-eyebrow mb-2">What this does not tell you</p>
              <ul className="text-ink-muted flex flex-col gap-2 text-xs leading-relaxed">
                {(signal.data.limitations ?? []).map((item) => (
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

          {(signal.data.events ?? []).length > 0 && (
            <div className="border-line-soft border-t pt-4">
              <p className="hm-eyebrow mb-3">History</p>
              <ol className="flex flex-col gap-3">
                {(signal.data.events ?? []).map((event, index) => (
                  <li key={`${event.occurred_at}-${index}`} className="flex gap-3 text-xs">
                    <span className="text-ink-faint" aria-hidden="true">
                      ●
                    </span>
                    <div>
                      <p className="text-ink">
                        {EVENT_WORDS[event.event_type] ?? event.event_type}
                        {event.from_severity && event.to_severity && (
                          <span className="text-ink-muted">
                            {" "}
                            — {event.from_severity} to {event.to_severity}
                          </span>
                        )}
                        {event.from_status && event.to_status && (
                          <span className="text-ink-muted">
                            {" "}
                            — {event.from_status} to {event.to_status}
                          </span>
                        )}
                      </p>
                      <p className="text-ink-dim mt-0.5">
                        {formatDateTime(event.occurred_at)}
                        {event.observed_value !== null &&
                          event.observed_value !== undefined && (
                            <>
                              {" · observed "}
                              {formatSignalValue(event.observed_value, signal.data.unit)}
                            </>
                          )}
                      </p>
                      {event.note && <p className="text-ink-muted mt-0.5">{event.note}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {signal.data.status !== "resolved" && (
            <Alert tone="info" title="Only the engine resolves a signal">
              This signal stays open until monitoring observes that the condition has cleared.
              Acknowledging records that you have seen it; dismissing hides it without claiming
              anything about the condition.
            </Alert>
          )}

          <p className="text-ink-dim text-xs leading-relaxed">
            {signal.data.disclaimer}{" "}
            <Link to="/methodology" className="text-gold hover:underline">
              How these figures are calculated
            </Link>
          </p>
        </div>
      )}
    </Dialog>
  );
}
