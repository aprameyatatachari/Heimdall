import { useId, useState } from "react";
import { Link } from "react-router-dom";

import type { RiskResult } from "@/api/analytics";
import { cx } from "@/lib/cx";
import { formatDate } from "@/lib/format";
import {
  basisWord,
  formatResult,
  METRICS,
  metricLabel,
  metricWindow,
  resultSign,
  unavailableReason,
  type MetricDescriptor,
} from "@/lib/metrics";

import { Unavailable } from "./Unavailable";

const TONE = {
  positive: "text-positive",
  negative: "text-negative",
  flat: "text-ink",
} as const;

export interface MetricTileProps {
  /** A key of `METRICS`. An unknown metric renders nothing rather than guessing. */
  metric: string;
  /** The run's result for it, or undefined when the run did not produce it. */
  result: RiskResult | undefined;
  currency: string;
  locale?: string;
  className?: string;
}

/**
 * One metric, with everything needed to read it correctly.
 *
 * The unit is in the value, the basis is in the label and repeated in words
 * below it, the period and the observation count are the provenance, and the
 * definition is one click away — never a hover-only tooltip, which a touch
 * device cannot open and a keyboard cannot reach.
 *
 * A metric with no value shows the backend's own reason. There is no fallback
 * zero anywhere in this component, by design: on a risk screen a zero and an
 * unknown look identical and mean opposite things. DESIGN.md section 6.3.
 */
export function MetricTile({ metric, result, currency, locale, className }: MetricTileProps) {
  const [showDefinition, setShowDefinition] = useState(false);
  const definitionId = useId();
  const descriptor: MetricDescriptor | undefined = METRICS[metric];
  if (!descriptor) return null;

  const value = formatResult(result, descriptor, { currency, locale });
  const { start, end, observations } = metricWindow(result);
  const caption = result ? descriptor.caption?.(result) : undefined;
  const tone = descriptor.tone ? TONE[resultSign(result)] : "text-ink";

  const period = start && end ? `${formatDate(start)} → ${formatDate(end)}` : null;

  return (
    <div className={cx("hm-panel flex flex-col p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="hm-eyebrow">{metricLabel(descriptor)}</p>
        <button
          type="button"
          onClick={() => setShowDefinition((open) => !open)}
          aria-expanded={showDefinition}
          aria-controls={definitionId}
          className="text-ink-faint hover:text-gold -me-1 -mt-1 flex size-7 shrink-0 items-center justify-center rounded-full text-xs transition-colors"
        >
          <span aria-hidden="true">i</span>
          <span className="sr-only">What {descriptor.label} means</span>
        </button>
      </div>

      <p className={cx("hm-numeric mt-3 text-xl", tone)}>
        {value === null ? <Unavailable reason={unavailableReason(result)} /> : value}
      </p>

      <p className="text-ink-dim mt-2 text-xs">
        {basisWord(descriptor)}
        {period && (
          <>
            <span aria-hidden="true"> · </span>
            {period}
          </>
        )}
      </p>

      {observations !== null && (
        <p className="text-ink-dim text-xs">
          {new Intl.NumberFormat(locale).format(observations)} observations
        </p>
      )}

      {caption && <p className="text-ink-dim mt-1 text-xs leading-relaxed">{caption}</p>}

      {showDefinition && (
        <div
          id={definitionId}
          className="border-line-soft text-ink-muted mt-4 border-t pt-3 text-xs leading-relaxed"
        >
          <p>{descriptor.definition}</p>
          <Link to="/methodology" className="text-gold mt-2 inline-block hover:underline">
            How this is calculated
          </Link>
        </div>
      )}
    </div>
  );
}
