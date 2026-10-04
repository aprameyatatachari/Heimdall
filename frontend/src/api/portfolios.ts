/**
 * Portfolio, position, import and market-data queries.
 *
 * Every mutation names the queries it invalidates. Getting that wrong is how a
 * table keeps showing a holding the user just deleted, so the invalidations are
 * deliberately broad: importing positions changes the summary, the holdings and
 * the portfolio's own position count.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api, request } from "./client";
import type { components } from "./schema";
import { invalidateSignals, signalKeys } from "./signals";
import type { PortfolioResponse, PortfolioSummaryResponse, PositionResponse } from "./types";

type Schemas = components["schemas"];

export type PortfolioPage = Schemas["Page_PortfolioResponse_"];
export type PortfolioCreateRequest = Schemas["PortfolioCreateRequest"];
export type PortfolioUpdateRequest = Schemas["PortfolioUpdateRequest"];
export type PositionCreateRequest = Schemas["PositionCreateRequest"];
export type PositionUpdateRequest = Schemas["PositionUpdateRequest"];
export type ImportSummaryResponse = Schemas["ImportSummaryResponse"];
export type ImportMode = Schemas["ImportMode"];
export type MarketDataRefreshResponse = Schemas["MarketDataRefreshResponse"];
export type AssetSearchResponse = Schemas["AssetSearchResponse"];
export type AssetSearchItem = Schemas["AssetSearchItem"];
export type HoldingSummary = Schemas["HoldingSummaryResponse"];
export type CoverageResponse = Schemas["CoverageResponse"];
export type HoldingCoverage = Schemas["HoldingCoverage"];

export const portfolioKeys = {
  all: ["portfolios"] as const,
  list: (limit: number, offset: number) => ["portfolios", "list", limit, offset] as const,
  detail: (id: string) => ["portfolios", "detail", id] as const,
  summary: (id: string) => ["portfolios", "summary", id] as const,
  positions: (id: string) => ["portfolios", "positions", id] as const,
  assetSearch: (query: string, currency?: string) =>
    ["assets", "search", query, currency ?? "any"] as const,
  popularAssets: (currency: string) => ["assets", "popular", currency] as const,
  refresh: (id: string) => ["portfolios", "refresh", id] as const,
};

/* -------------------------------------------------------------------------- */
/* Queries                                                                     */
/* -------------------------------------------------------------------------- */

export function usePortfolios(limit = 50, offset = 0) {
  return useQuery({
    queryKey: portfolioKeys.list(limit, offset),
    queryFn: () => api.get<PortfolioPage>("/portfolios", { params: { limit, offset } }),
  });
}

export function usePortfolio(id: string) {
  return useQuery({
    queryKey: portfolioKeys.detail(id),
    queryFn: () => api.get<PortfolioResponse>(`/portfolios/${id}`),
    enabled: Boolean(id),
  });
}

export function usePortfolioSummary(id: string) {
  return useQuery({
    queryKey: portfolioKeys.summary(id),
    queryFn: () => api.get<PortfolioSummaryResponse>(`/portfolios/${id}/summary`),
    enabled: Boolean(id),
  });
}

export function usePositions(id: string) {
  return useQuery({
    queryKey: portfolioKeys.positions(id),
    queryFn: () => api.get<PositionResponse[]>(`/portfolios/${id}/positions`),
    enabled: Boolean(id),
  });
}

/**
 * Symbol lookup for the position form.
 *
 * Disabled below two characters: a one-character query matches most of the
 * catalogue and tells the user nothing.
 */
export function useAssetSearch(
  query: string,
  currency?: string,
  options?: Partial<UseQueryOptions<AssetSearchResponse>>,
) {
  return useQuery({
    queryKey: portfolioKeys.assetSearch(query, currency),
    queryFn: () =>
      api.get<AssetSearchResponse>("/assets/search", {
        params: { query, currency, limit: 12 },
      }),
    enabled: query.trim().length >= 2,
    staleTime: 5 * 60_000,
    ...options,
  });
}

/**
 * Instruments to offer before anything has been typed.
 *
 * The same endpoint with no query. Ordered by size, which is what makes it a
 * place to start browsing and not a recommendation — the screen says so.
 * Cached for an hour: the largest companies in a market do not reshuffle
 * between one dropdown and the next.
 */
export function usePopularAssets(currency: string, enabled = true) {
  return useQuery({
    queryKey: portfolioKeys.popularAssets(currency),
    queryFn: () =>
      api.get<AssetSearchResponse>("/assets/search", { params: { currency, limit: 20 } }),
    enabled: enabled && Boolean(currency),
    staleTime: 60 * 60_000,
    refetchOnWindowFocus: false,
  });
}

/* -------------------------------------------------------------------------- */
/* Mutations                                                                   */
/* -------------------------------------------------------------------------- */

export function useCreatePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PortfolioCreateRequest) =>
      api.post<PortfolioResponse>("/portfolios", body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}

export function useUpdatePortfolio(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PortfolioUpdateRequest) =>
      api.patch<PortfolioResponse>(`/portfolios/${id}`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}

export function useDeletePortfolio() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/portfolios/${id}`),
    onSuccess: (_result, id) => {
      // Drop the deleted portfolio's own caches outright; invalidating would
      // refetch them and get a 404.
      queryClient.removeQueries({ queryKey: portfolioKeys.detail(id) });
      queryClient.removeQueries({ queryKey: portfolioKeys.summary(id) });
      queryClient.removeQueries({ queryKey: portfolioKeys.positions(id) });
      void queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
    },
  });
}

/** Everything a holdings change touches. */
function invalidateHoldings(queryClient: ReturnType<typeof useQueryClient>, id: string) {
  void queryClient.invalidateQueries({ queryKey: portfolioKeys.positions(id) });
  void queryClient.invalidateQueries({ queryKey: portfolioKeys.summary(id) });
  void queryClient.invalidateQueries({ queryKey: portfolioKeys.detail(id) });
  // The list shows each portfolio's position count.
  void queryClient.invalidateQueries({ queryKey: portfolioKeys.all });
}

export function useCreatePosition(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PositionCreateRequest) =>
      api.post<PositionResponse>(`/portfolios/${portfolioId}/positions`, body),
    onSuccess: () => invalidateHoldings(queryClient, portfolioId),
  });
}

export function useUpdatePosition(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ positionId, body }: { positionId: string; body: PositionUpdateRequest }) =>
      api.patch<PositionResponse>(`/portfolios/${portfolioId}/positions/${positionId}`, body),
    onSuccess: () => invalidateHoldings(queryClient, portfolioId),
  });
}

export function useDeletePosition(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (positionId: string) =>
      api.delete<void>(`/portfolios/${portfolioId}/positions/${positionId}`),
    onSuccess: () => invalidateHoldings(queryClient, portfolioId),
  });
}

export function useImportPositions(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, mode }: { file: File; mode: ImportMode }) => {
      const form = new FormData();
      form.append("file", file);
      form.append("mode", mode);
      // No Content-Type header: the browser sets it with the multipart boundary,
      // and setting it by hand produces a body the server cannot parse.
      return request<ImportSummaryResponse>(`/portfolios/${portfolioId}/positions/import`, {
        method: "POST",
        formData: form,
      });
    },
    onSuccess: () => invalidateHoldings(queryClient, portfolioId),
  });
}

export function useRefreshMarketData(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    // Keyed, so the page-load refresh and the button share one pending state:
    // pressing the button while the automatic one is in flight must not start a
    // second request for the same prices.
    mutationKey: portfolioKeys.refresh(portfolioId),
    mutationFn: (range: {
      start?: string;
      end?: string;
      quick?: boolean;
      /** Evaluate the Early Warning rules against the prices just read. */
      monitor?: boolean;
    }) =>
      api.post<MarketDataRefreshResponse>(
        `/portfolios/${portfolioId}/market-data/refresh`,
        undefined,
        {
          params: {
            start: range.start,
            end: range.end,
            quick: range.quick || undefined,
            monitor: range.monitor || undefined,
          },
        },
      ),
    onSuccess: (data) => {
      // New prices change every derived figure, not just the holdings table.
      invalidateHoldings(queryClient, portfolioId);
      void queryClient.invalidateQueries({ queryKey: ["price-coverage", portfolioId] });
      if (data.monitoring) {
        // The rules were evaluated against these prices, so every signal on
        // screen may have moved with them.
        invalidateSignals(queryClient, portfolioId);
        void queryClient.invalidateQueries({
          queryKey: signalKeys.monitoringRuns(portfolioId),
        });
      }
    },
  });
}

/**
 * How much of a window each holding's stored prices cover.
 *
 * Asked before an analysis or a scenario runs, so the screen can say which
 * holdings have nothing for the period while there is still a decision to make.
 * It fetches no prices, which is the point: a warning produced by fixing the
 * problem would never be seen.
 */
export function usePriceCoverage(
  portfolioId: string,
  window: { start: string; end: string } | null,
) {
  return useQuery({
    queryKey: ["price-coverage", portfolioId, window?.start ?? "", window?.end ?? ""],
    queryFn: () =>
      api.get<CoverageResponse>(`/portfolios/${portfolioId}/market-data/coverage`, {
        params: { start: window?.start, end: window?.end },
      }),
    enabled: Boolean(portfolioId) && window !== null && window.start <= window.end,
    staleTime: 15_000,
  });
}
