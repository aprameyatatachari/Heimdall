import { useQueries } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { components } from "@/api/schema";
import type { PortfolioResponse } from "@/api/types";

export type ReturnHistory = components["schemas"]["ReturnHistoryResponse"];

export interface PortfolioReturnHistory {
  portfolio: PortfolioResponse;
  history: ReturnHistory | undefined;
  pending: boolean;
  failed: boolean;
}

/**
 * Each portfolio's cumulative return path over the same number of days.
 *
 * Read from stored prices on the server; nothing here is computed in the
 * browser. Cached for a few minutes, because a daily return path does not move
 * between one visit to the home page and the next.
 */
export function useReturnHistories(
  portfolios: PortfolioResponse[],
  days: number,
): PortfolioReturnHistory[] {
  const results = useQueries({
    queries: portfolios.map((portfolio) => ({
      queryKey: ["return-history", portfolio.id, days] as const,
      queryFn: () =>
        api.get<ReturnHistory>(`/portfolios/${portfolio.id}/return-history`, {
          params: { days },
        }),
      staleTime: 5 * 60_000,
    })),
  });

  return portfolios.map((portfolio, index) => ({
    portfolio,
    history: results[index]?.data,
    pending: results[index]?.isPending ?? true,
    failed: results[index]?.isError ?? false,
  }));
}
