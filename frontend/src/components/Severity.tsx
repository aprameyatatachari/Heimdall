import { cx } from "@/lib/cx";

/**
 * Severity, as colour **and** icon **and** word.
 *
 * Never colour alone: the four severities are four dusty tones that a
 * colour-blind reader, a greyscale print or a bad monitor can flatten into one.
 * The shapes differ as well as the hues — circle, pennant, triangle, octagon —
 * so the icon carries the reading even when the colour does not.
 *
 * The backend names the icon for each severity in `SEVERITY_ICONS` and sends it
 * on every signal. These shapes map to those names rather than inventing a
 * parallel scheme, so a new severity cannot appear with no icon.
 *
 * Nothing here blinks, pulses or animates. DESIGN.md section 6.4.
 */

type Severity = "informational" | "elevated" | "high" | "critical";

interface Style {
  word: string;
  color: string;
  icon: "info-circle" | "flag" | "alert-triangle" | "alert-octagon";
}

const STYLES: Record<Severity, Style> = {
  informational: {
    word: "Informational",
    color: "var(--color-sev-info)",
    icon: "info-circle",
  },
  elevated: { word: "Elevated", color: "var(--color-sev-elevated)", icon: "flag" },
  high: { word: "High", color: "var(--color-sev-high)", icon: "alert-triangle" },
  critical: { word: "Critical", color: "var(--color-sev-critical)", icon: "alert-octagon" },
};

function isSeverity(value: string): value is Severity {
  return value in STYLES;
}

/** Distinct outlines, so severity survives greyscale. */
function SeverityIcon({ icon, className }: { icon: Style["icon"]; className?: string }) {
  const shared = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className={className}>
      {icon === "info-circle" && (
        <>
          <circle cx="12" cy="12" r="8.5" {...shared} />
          <path d="M12 11v5M12 8h.01" {...shared} />
        </>
      )}
      {icon === "flag" && (
        <>
          <path d="M6 21V4" {...shared} />
          <path d="M6 4.5h11l-2.5 4 2.5 4H6" {...shared} />
        </>
      )}
      {icon === "alert-triangle" && (
        <>
          <path d="M12 4.5 21 19.5H3z" {...shared} />
          <path d="M12 10v4M12 17h.01" {...shared} />
        </>
      )}
      {icon === "alert-octagon" && (
        <>
          <path d="M8.5 3.5h7L20.5 8.5v7L15.5 20.5h-7L3.5 15.5v-7z" {...shared} />
          <path d="M12 8v5M12 16h.01" {...shared} />
        </>
      )}
    </svg>
  );
}

export function SeverityBadge({
  severity,
  className,
  showWord = true,
}: {
  severity: string;
  className?: string;
  showWord?: boolean;
}) {
  const style = isSeverity(severity) ? STYLES[severity] : null;

  if (!style) {
    // An unknown severity is rendered as itself rather than dropped: a signal
    // with no badge would read as no severity at all.
    return <span className={cx("text-ink-muted text-xs", className)}>{severity}</span>;
  }

  return (
    <span
      className={cx("inline-flex items-center gap-2 text-xs", className)}
      style={{ color: style.color }}
    >
      <SeverityIcon icon={style.icon} className="size-4 shrink-0" />
      {showWord ? <span>{style.word}</span> : <span className="sr-only">{style.word}</span>}
    </span>
  );
}

/** The count of open signals at one severity, for the summary panel. */
export function SeverityCount({
  severity,
  count,
  selected = false,
  onClick,
}: {
  severity: string;
  count: number;
  selected?: boolean;
  onClick?: () => void;
}) {
  const color = isSeverity(severity) ? STYLES[severity].color : "var(--color-neutral)";
  const content = (
    <>
      <SeverityBadge severity={severity} />
      <span className="hm-numeric text-ink mt-2 block text-2xl">{count}</span>
      <span className="text-ink-dim text-2xs mt-1 block uppercase">
        {count === 1 ? "open signal" : "open signals"}
      </span>
    </>
  );

  if (!onClick) {
    return (
      <div
        className="border-line-soft rounded-md border p-4"
        style={{ borderInlineStartColor: color, borderInlineStartWidth: 3 }}
      >
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cx(
        "rounded-md border p-4 text-start transition-colors",
        selected ? "border-gold bg-surface-2" : "border-line-soft hover:border-line-strong",
      )}
      style={{ borderInlineStartColor: color, borderInlineStartWidth: 3 }}
    >
      {content}
    </button>
  );
}
