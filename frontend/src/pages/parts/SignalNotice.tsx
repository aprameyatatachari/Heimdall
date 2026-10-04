import { Link } from "react-router-dom";

import type { WarningSignalResponse } from "@/api/types";
import { Button } from "@/components/Button";
import { SeverityBadge } from "@/components/Severity";
import { fadeOut, useFadeIn, useGSAP } from "@/lib/motion";

const SEVERITY_RANK: Record<string, number> = {
  critical: 3,
  high: 2,
  elevated: 1,
  informational: 0,
};

/**
 * Says that a new signal has been observed, once, and waits.
 *
 * It does not time out. A notice that removes itself after a few seconds is one
 * that a reader who looked away never saw, and a warning nobody saw is the thing
 * this whole feature exists to prevent. It stays until it is dismissed or
 * followed.
 *
 * Polite, not assertive, and it does not take focus: it describes a condition
 * that was observed, not an emergency. It fades in over 200ms and does nothing
 * else — severity never pulses or flashes. DESIGN.md sections 6.4 and 7.1.
 */
export function SignalNotice({
  signals,
  to,
  onDismiss,
}: {
  signals: WarningSignalResponse[];
  /** Where the signals can be read in full. */
  to: string;
  onDismiss: () => void;
}) {
  const ref = useFadeIn<HTMLDivElement>();
  const { contextSafe } = useGSAP({ scope: ref });
  const dismiss = contextSafe(() => fadeOut(ref.current, onDismiss));

  const [first] = [...signals].sort(
    (a, b) => (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0),
  );
  if (!first) return null;

  const others = signals.length - 1;

  return (
    <div
      ref={ref}
      role="status"
      aria-live="polite"
      className="hm-panel border-line-strong fixed end-4 bottom-4 z-40 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-3 p-4 shadow-lg"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="hm-eyebrow">
          {signals.length === 1 ? "New Gjallarhorn signal" : "New Gjallarhorn signals"}
        </p>
        <SeverityBadge severity={first.severity} />
      </div>

      <div>
        <p className="text-ink text-sm">{first.title}</p>
        <p className="text-ink-muted mt-1 text-xs leading-relaxed">
          {others > 0
            ? `And ${others} more observed in the latest check.`
            : "Observed in the latest check of this portfolio."}{" "}
          An observation, not a prediction.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Link
          to={to}
          onClick={onDismiss}
          className="text-gold hover:text-gold-bright text-sm transition-colors"
        >
          {signals.length === 1 ? "View signal" : "View signals"}
        </Link>
        <Button variant="ghost" size="sm" onClick={dismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
