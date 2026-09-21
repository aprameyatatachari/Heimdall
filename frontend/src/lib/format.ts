/**
 * Formatting for values that arrive from the API.
 *
 * Money arrives as a decimal string and stays one. `Intl.NumberFormat.format`
 * accepts a string and formats it exactly; converting through a JavaScript
 * number silently corrupts large values, so nothing here does that.
 * See AGENTS.md section 7.1.
 */

/** What to show when the backend could not produce a value. Never "0". */
export const UNAVAILABLE = "—"; // em dash

/**
 * Grouping and separators follow the reader's own locale by default. Tests pass
 * one explicitly so their expectations do not depend on the machine running them.
 */
export interface FormatOptions {
  locale?: string;
}

export function formatMoney(
  value: string | null | undefined,
  currency: string,
  options: FormatOptions & { signed?: boolean; maximumFractionDigits?: number } = {},
): string {
  if (value === null || value === undefined || value === "") return UNAVAILABLE;

  try {
    // The constructor is inside the try as well: an unrecognised currency code
    // throws there, not at format time, and a bad code must not take a page down.
    const formatter = new Intl.NumberFormat(options.locale, {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: options.maximumFractionDigits ?? 2,
      signDisplay: options.signed ? "exceptZero" : "auto",
    });
    // Passing the decimal string straight through keeps every digit.
    return formatter.format(value as unknown as number);
  } catch {
    return UNAVAILABLE;
  }
}

/**
 * A fraction from the API (0.084) rendered as a percentage (8.40%).
 *
 * Percentages arrive as JSON numbers rather than decimal strings because they
 * are ratios, not amounts of money.
 */
export function formatPercent(
  value: number | null | undefined,
  options: FormatOptions & { signed?: boolean; digits?: number } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return UNAVAILABLE;

  return new Intl.NumberFormat(options.locale, {
    style: "percent",
    minimumFractionDigits: options.digits ?? 2,
    maximumFractionDigits: options.digits ?? 2,
    signDisplay: options.signed ? "exceptZero" : "auto",
  }).format(value);
}

/** A share quantity. Trailing zeros are dropped; the digits that matter stay. */
export function formatQuantity(
  value: string | null | undefined,
  options: FormatOptions = {},
): string {
  if (value === null || value === undefined || value === "") return UNAVAILABLE;
  try {
    return new Intl.NumberFormat(options.locale, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 8,
    }).format(value as unknown as number);
  } catch {
    return UNAVAILABLE;
  }
}

/** An ISO date (2026-09-18) as a readable date. Dates are never localised away. */
export function formatDate(
  value: string | null | undefined,
  options: FormatOptions = {},
): string {
  if (!value) return UNAVAILABLE;
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return UNAVAILABLE;
  return new Intl.DateTimeFormat(options.locale, {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}

/** An ISO timestamp as a readable date and time. */
export function formatDateTime(
  value: string | null | undefined,
  options: FormatOptions = {},
): string {
  if (!value) return UNAVAILABLE;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return UNAVAILABLE;
  return new Intl.DateTimeFormat(options.locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

/**
 * The sign of a decimal string, without converting it to a number.
 *
 * Used to choose a colour and a caption. "0.00" and "-0.00" are both flat.
 */
export function signOf(value: string | null | undefined): "positive" | "negative" | "flat" {
  if (value === null || value === undefined || value === "") return "flat";
  const trimmed = value.trim();
  if (/^-?0*\.?0*$/.test(trimmed)) return "flat";
  return trimmed.startsWith("-") ? "negative" : "positive";
}

/** How many trading days old a date is, in whole days, or null when unknown. */
export function daysSince(
  value: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!value) return null;
  const then = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(then.getTime())) return null;
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  return Math.max(0, Math.round((today.getTime() - then.getTime()) / 86_400_000));
}
