import { useQueries } from "@tanstack/react-query";

import { api } from "@/api/client";
import { portfolioKeys } from "@/api/portfolios";
import { signalKeys } from "@/api/signals";
import type {
  PortfolioResponse,
  PortfolioSummaryResponse,
  SignalSummaryResponse,
} from "@/api/types";

export interface PortfolioOverview {
  portfolio: PortfolioResponse;
  summary: PortfolioSummaryResponse | undefined;
  summaryPending: boolean;
  signals: SignalSummaryResponse | undefined;
}

/**
 * Each portfolio's summary and open-signal count, fetched side by side.
 *
 * The same query keys as the portfolio's own screens, so opening a portfolio
 * from here shows figures that are already in the cache.
 */
export function usePortfolioOverviews(portfolios: PortfolioResponse[]): PortfolioOverview[] {
  const summaries = useQueries({
    queries: portfolios.map((portfolio) => ({
      queryKey: portfolioKeys.summary(portfolio.id),
      queryFn: () => api.get<PortfolioSummaryResponse>(`/portfolios/${portfolio.id}/summary`),
    })),
  });
  const signals = useQueries({
    queries: portfolios.map((portfolio) => ({
      queryKey: signalKeys.summary(portfolio.id),
      queryFn: () =>
        api.get<SignalSummaryResponse>(`/portfolios/${portfolio.id}/signals/summary`),
      staleTime: 30_000,
    })),
  });

  return portfolios.map((portfolio, index) => ({
    portfolio,
    summary: summaries[index]?.data,
    summaryPending: summaries[index]?.isPending ?? true,
    signals: signals[index]?.data,
  }));
}
