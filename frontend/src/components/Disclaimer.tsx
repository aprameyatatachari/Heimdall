import { cx } from "@/lib/cx";

export const DISCLAIMER =
  "Heimdall is an educational portfolio-analysis tool. Its calculations are estimates " +
  "based on historical data and model assumptions and do not constitute financial " +
  "advice or guarantee future results.";

/**
 * The standing disclaimer. Present and readable on every page — never collapsed
 * behind an accordion, never grey-on-grey at 4px. DESIGN.md section 6.7.
 */
export function Disclaimer({ className }: { className?: string }) {
  return (
    <p className={cx("text-ink-dim max-w-prose text-xs leading-relaxed", className)}>
      {DISCLAIMER}
    </p>
  );
}
