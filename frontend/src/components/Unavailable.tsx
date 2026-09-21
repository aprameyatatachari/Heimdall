import { cx } from "@/lib/cx";
import { UNAVAILABLE } from "@/lib/format";

/**
 * A value the backend could not produce.
 *
 * Never a zero, never an empty cell, never a bare dash. The reason travels with
 * the dash, because "unavailable" without a cause is indistinguishable from a
 * bug. See AGENTS.md section 7.2.
 */
export function Unavailable({ reason, className }: { reason?: string; className?: string }) {
  return (
    <span className={cx("text-ink-faint inline-flex items-baseline gap-1.5", className)}>
      <span aria-hidden="true">{UNAVAILABLE}</span>
      <span className="text-xs">{reason ?? "unavailable"}</span>
      <span className="sr-only">Unavailable{reason ? `: ${reason}` : ""}</span>
    </span>
  );
}
