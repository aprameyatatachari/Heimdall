import { cx } from "@/lib/cx";
import { daysSince, formatDate } from "@/lib/format";

/**
 * When the prices behind a figure were last updated.
 *
 * Always visible, never only in a tooltip. Stale data is stated as stale rather
 * than presented as current: a number from 2023 on a 2026 screen is wrong in a
 * way the number itself cannot show. AGENTS.md section 6.5.
 */
export function DataAsOf({
  date,
  staleAfterDays = 5,
  action,
  className,
}: {
  date: string | null | undefined;
  staleAfterDays?: number;
  action?: React.ReactNode;
  className?: string;
}) {
  const age = daysSince(date);
  const stale = age !== null && age > staleAfterDays;

  if (!date) {
    return (
      <div className={cx("flex flex-wrap items-center gap-3 text-sm", className)}>
        <span className="text-caution flex items-center gap-2">
          <span aria-hidden="true">◆</span>
          No market data yet. Refresh to fetch prices.
        </span>
        {action}
      </div>
    );
  }

  return (
    <div className={cx("flex flex-wrap items-center gap-3 text-sm", className)}>
      <span className={stale ? "text-caution" : "text-ink-dim"}>
        {stale && (
          <span aria-hidden="true" className="me-2">
            ◆
          </span>
        )}
        Prices as of {formatDate(date)}
        {stale && age !== null && ` — ${age} days old`}
      </span>
      {action}
    </div>
  );
}
