/**
 * Alert-rule thresholds.
 *
 * Kept out of the form component so the rule that matters — thresholds increase
 * with severity, and each one is in range for its unit — can be tested without
 * rendering anything, and so the form file exports only a component.
 */

/** The three configurable severities, in the order they must increase. */
export const SEVERITIES = ["elevated", "high", "critical"] as const;
export type ConfigurableSeverity = (typeof SEVERITIES)[number];

export type Thresholds = Record<ConfigurableSeverity, string>;

export function toThresholds(configuration: Record<string, number> | undefined): Thresholds {
  return {
    elevated:
      configuration?.["elevated"] !== undefined ? String(configuration["elevated"]) : "",
    high: configuration?.["high"] !== undefined ? String(configuration["high"]) : "",
    critical:
      configuration?.["critical"] !== undefined ? String(configuration["critical"]) : "",
  };
}

/**
 * Check a threshold set the way the backend will.
 *
 * Client-side for immediate feedback, never as the authority: the same rules are
 * enforced server-side and a rejected update attaches the backend's message.
 * Mirrored from `SeverityThresholds` — at least one set, each in range, and
 * increasing with severity, since every rule measures a quantity where larger is
 * worse.
 */
export function validateThresholds(
  thresholds: Thresholds,
  unit: string,
): { ok: true } | { ok: false; message: string } {
  const entries: [ConfigurableSeverity, number][] = [];

  for (const severity of SEVERITIES) {
    const raw = thresholds[severity].trim();
    if (raw === "") continue;
    const value = Number(raw);
    if (!Number.isFinite(value)) {
      return { ok: false, message: `The ${severity} threshold must be a number.` };
    }
    if (value <= 0) {
      return { ok: false, message: `The ${severity} threshold must be greater than zero.` };
    }
    if (unit.startsWith("percent_") && value > 1) {
      return {
        ok: false,
        message: `A share is a fraction between 0 and 1, so ${value} is out of range. Use 0.3 for 30%.`,
      };
    }
    if (unit === "correlation_coefficient" && value > 1) {
      return { ok: false, message: "A correlation cannot exceed 1." };
    }
    entries.push([severity, value]);
  }

  if (entries.length === 0) {
    return { ok: false, message: "Set at least one threshold, or disable the rule instead." };
  }

  for (let index = 1; index < entries.length; index += 1) {
    const previous = entries[index - 1];
    const current = entries[index];
    if (!previous || !current) continue;
    if (current[1] <= previous[1]) {
      return {
        ok: false,
        message: `The ${current[0]} threshold must be greater than the ${previous[0]} one.`,
      };
    }
  }

  return { ok: true };
}
