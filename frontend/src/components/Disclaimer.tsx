import { cx } from "@/lib/cx";

export const DISCLAIMER =
  "Heimdall is an educational portfolio-analysis tool. Its calculations are estimates " +
  "based on historical data and model assumptions and do not constitute financial " +
  "advice or guarantee future results.";

/**
 * The standing disclaimer. Present and readable on every page — never collapsed
 * behind an accordion, never grey-on-grey at 4px. DESIGN.md section 6.7.
 */
export function Disclaimer({
  className,
  onImage = false,
}: {
  className?: string;
  /** Set when this sits over photography rather than a solid surface. */
  onImage?: boolean;
}) {
  return (
    <p
      className={cx(
        "max-w-prose text-xs leading-relaxed",
        // Tertiary ink is legible on a solid panel but not over a photograph,
        // where even a heavy scrim leaves it around 2.5:1.
        onImage ? "text-ink-muted" : "text-ink-dim",
        className,
      )}
    >
      {DISCLAIMER}
    </p>
  );
}
