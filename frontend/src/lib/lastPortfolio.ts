/**
 * The portfolio the reader was last looking at.
 *
 * Analytics, stress tests, signals and reports all belong to one portfolio, so
 * a link to "Analytics" from a page that is not inside a portfolio has to mean
 * some portfolio's analytics. The one last opened is the least surprising
 * answer. It is a convenience, kept in this browser only; without it the first
 * portfolio is used.
 */

const KEY = "heimdall.lastPortfolio";

export function rememberPortfolio(id: string): void {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    // Storage unavailable: the first portfolio is used instead.
  }
}

export function lastPortfolio(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** The sections of a portfolio that the main navigation links to. */
export const PORTFOLIO_SECTIONS = ["analytics", "stress", "signals", "reports"] as const;
export type PortfolioSection = (typeof PORTFOLIO_SECTIONS)[number];

/** `/app/portfolios/:id/:section?`, taken apart. Null outside a portfolio. */
export function portfolioRoute(
  pathname: string,
): { id: string; section: string | null } | null {
  const match = /^\/app\/portfolios\/([^/]+)(?:\/([^/]+))?/.exec(pathname);
  if (!match?.[1]) return null;
  return { id: match[1], section: match[2] ?? null };
}
