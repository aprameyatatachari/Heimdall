import { useEffect, useRef, useState } from "react";

import { useSignals, type SignalFilters } from "@/api/signals";
import type { WarningSignalResponse } from "@/api/types";

/** How often an open portfolio asks whether anything new has been observed. */
export const SIGNAL_POLL_MS = 60_000;

const ACTIVE: SignalFilters = { status: ["active"] };
/**
 * Signals that became active while this portfolio was open.
 *
 * The first answer is the baseline and announces nothing: a signal that was
 * already there when the page opened is not news, and the Signals tab already
 * counts it. Only a signal that appears afterwards is reported, whoever found
 * it — the check this page ran when it refreshed prices, or the scheduler
 * running on the server.
 */
export function useNewSignals(portfolioId: string) {
  const active = useSignals(portfolioId, ACTIVE, 50, { refetchInterval: SIGNAL_POLL_MS });
  const known = useRef<{ portfolioId: string; ids: Set<string> } | null>(null);
  const [fresh, setFresh] = useState<WarningSignalResponse[]>([]);

  useEffect(() => {
    const items = active.data?.items;
    if (!items) return;

    if (known.current?.portfolioId !== portfolioId) {
      known.current = { portfolioId, ids: new Set(items.map((item) => item.id)) };
      setFresh([]);
      return;
    }

    const ids = known.current.ids;
    const arrived = items.filter((item) => !ids.has(item.id));
    if (arrived.length === 0) return;
    for (const item of arrived) ids.add(item.id);
    setFresh((current) => [...current, ...arrived]);
  }, [active.data, portfolioId]);

  return { fresh, clear: () => setFresh([]) };
}
