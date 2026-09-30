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
      {/* The word comes before the reason and the reason is said once: with the
          reason in both layers a screen reader read it twice, and with the word
          only in the second layer it arrived after the explanation. */}
      <span className="sr-only">Unavailable: </span>
      <span className="text-xs">{reason ?? "unavailable"}</span>
    </span>
  );
}
