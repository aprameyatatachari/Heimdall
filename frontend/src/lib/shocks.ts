/**
 * Which shock applies to which holding.
 *
 * This mirrors `resolve_shock` in the backend engine so the builder can show a
 * user the shock that will actually hit each holding **before** they run
 * anything. Precedence is otherwise invisible: someone who shocks Technology by
 * -20% and AAPL by -35% has to be able to see that AAPL takes -35% and not both.
 *
 * Duplicating a rule is a risk, so the duplication is kept to exactly this: a
 * lookup with no arithmetic in it. Nothing here estimates an impact — the run
 * itself does that, on the server, and the preview only names the shock. The
 * rule it mirrors is documented in AGENTS.md section 6.8 and pinned by tests on
 * both sides.
 */

import type { ShockTargetType } from "@/api/stress";

export interface Shock {
  target_type: ShockTargetType;
  target?: string | null;
  /** Relative price change as a decimal: -0.2 is a 20% fall. */
  value: number;
}

/** Lower is more specific, and more specific wins. */
const PRECEDENCE: Record<ShockTargetType, number> = {
  symbol: 0,
  sector: 1,
  portfolio: 2,
};

export const PRECEDENCE_EXPLANATION =
  "A shock on a symbol overrides one on its sector, which overrides a shock on " +
  "the whole portfolio. Where two shocks are equally specific, the later one wins.";

function applies(shock: Shock, symbol: string, sector: string): boolean {
  if (shock.target_type === "portfolio") return true;
  if (!shock.target) return false;
  if (shock.target_type === "symbol") {
    return shock.target.toUpperCase() === symbol.toUpperCase();
  }
  return shock.target.toLowerCase() === sector.toLowerCase();
}

/**
 * The shock a holding will receive, or null when nothing targets it.
 *
 * `<=` rather than `<`: among equally specific shocks the later one wins, which
 * is how the engine resolves it. Two shocks on the same target are refused by
 * the API before a run starts, so the tie-break is defensive rather than
 * something a scenario can rely on — `duplicateTargets` catches that case in the
 * builder, before the request is made.
 */
export function resolveShock(
  symbol: string,
  sector: string,
  shocks: readonly Shock[],
): Shock | null {
  let best: Shock | null = null;
  for (const shock of shocks) {
    if (!applies(shock, symbol, sector)) continue;
    if (best === null || PRECEDENCE[shock.target_type] <= PRECEDENCE[best.target_type]) {
      best = shock;
    }
  }
  return best;
}

/** How a resolved shock reads in the preview: "AAPL" or "Technology" or "whole portfolio". */
export function shockSource(shock: Shock): string {
  if (shock.target_type === "portfolio") return "whole portfolio";
  return shock.target ?? shock.target_type;
}

/** A duplicate target is ambiguous, and the backend refuses the whole scenario. */
export function duplicateTargets(shocks: readonly Shock[]): string[] {
  const seen = new Set<string>();
  const duplicates: string[] = [];
  for (const shock of shocks) {
    const key = `${shock.target_type}:${(shock.target ?? "").toLowerCase()}`;
    if (seen.has(key)) duplicates.push(shockSource(shock));
    seen.add(key);
  }
  return duplicates;
}
