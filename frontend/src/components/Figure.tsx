import { cx } from "@/lib/cx";
import { formatMoney, formatPercent, signOf } from "@/lib/format";

import { Unavailable } from "./Unavailable";

const TONE = {
  positive: "text-positive",
  negative: "text-negative",
  flat: "text-ink",
} as const;

/**
 * A monetary amount.
 *
 * Colour never carries the meaning alone: a signed amount always shows its own
 * `+` or `-`, so the figure survives greyscale and colour blindness.
 * DESIGN.md section 2.2 rule 4.
 */
export function Money({
  value,
  currency,
  signed = false,
  tone = false,
  reason,
  className,
}: {
  value: string | null | undefined;
  currency: string;
  signed?: boolean;
  /** Colour by sign. Only for figures where gain and loss are the point. */
  tone?: boolean;
  reason?: string;
  className?: string;
}) {
  if (value === null || value === undefined || value === "") {
    return <Unavailable reason={reason} className={className} />;
  }
  return (
    <span className={cx("hm-numeric", tone && TONE[signOf(value)], className)}>
      {formatMoney(value, currency, { signed })}
    </span>
  );
}

/** A ratio rendered as a percentage. */
export function Percent({
  value,
  signed = false,
  tone = false,
  reason,
  className,
}: {
  value: number | null | undefined;
  signed?: boolean;
  tone?: boolean;
  reason?: string;
  className?: string;
}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <Unavailable reason={reason} className={className} />;
  }
  const sign = value > 0 ? "positive" : value < 0 ? "negative" : "flat";
  return (
    <span className={cx("hm-numeric", tone && TONE[sign], className)}>
      {formatPercent(value, { signed })}
    </span>
  );
}
