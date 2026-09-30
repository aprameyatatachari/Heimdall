import { cx } from "@/lib/cx";

export interface BarDatum {
  label: string;
  /** `null` is drawn as an absent bar with its reason, never as a zero-length one. */
  value: number | null;
  reason?: string;
  color?: string;
}

export interface BarChartProps {
  data: BarDatum[];
  formatValue: (value: number) => string;
  /** Right-hand column: a second figure per row, already formatted. */
  secondary?: (datum: BarDatum) => string | undefined;
  ariaLabel: string;
  className?: string;
}

const DEFAULT_COLOR = "var(--color-series-1)";

/**
 * Horizontal bars, one per row.
 *
 * Horizontal rather than vertical because the labels are symbols and sector
 * names: vertical bars would need them rotated, truncated, or dropped, and a
 * chart whose labels cannot be read is a decoration.
 *
 * Bars are proportioned against the largest magnitude present, so the longest
 * bar fills the row. Each row also prints its own value, so the chart is
 * readable without measuring anything against an axis.
 */
export function BarChart({
  data,
  formatValue,
  secondary,
  ariaLabel,
  className,
}: BarChartProps) {
  const magnitudes = data.flatMap((datum) =>
    datum.value === null ? [] : [Math.abs(datum.value)],
  );
  const largest = magnitudes.length > 0 ? Math.max(...magnitudes) : 0;

  if (data.length === 0) {
    return (
      <p className="text-ink-dim border-line-soft rounded-md border border-dashed px-4 py-10 text-center text-sm">
        No data for this period.
      </p>
    );
  }

  return (
    <ul className={cx("flex flex-col gap-3", className)} aria-label={ariaLabel}>
      {data.map((datum) => {
        const share =
          datum.value === null || largest === 0 ? 0 : Math.abs(datum.value) / largest;
        const extra = secondary?.(datum);
        return (
          <li key={datum.label} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-4 text-xs">
              <span className="text-ink-muted">{datum.label}</span>
              <span className="flex items-baseline gap-3">
                {extra && <span className="text-ink-dim">{extra}</span>}
                <span className="hm-numeric text-ink">
                  {datum.value === null ? (
                    <span className="text-ink-faint">— {datum.reason ?? "unavailable"}</span>
                  ) : (
                    formatValue(datum.value)
                  )}
                </span>
              </span>
            </div>
            <div className="bg-surface-2 h-2 overflow-hidden rounded-full" aria-hidden="true">
              {datum.value !== null && (
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.max(share * 100, share > 0 ? 1 : 0)}%`,
                    backgroundColor: datum.color ?? DEFAULT_COLOR,
                    opacity: datum.value < 0 ? 0.6 : 1,
                  }}
                />
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
