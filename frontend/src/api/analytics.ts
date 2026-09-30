/**
 * Analysis-run queries.
 *
 * A run is immutable once it has completed, so a fetched run is cached
 * indefinitely and never refetched on focus. Changing a parameter creates a new
 * run rather than mutating the one on screen — the dashboard always shows a
 * stored analysis, which is what a report would contain. AGENTS.md section 6.7.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";
import type { AnalysisRunResponse, AnalysisRunSummary } from "./types";

type Schemas = components["schemas"];

export type AnalysisRunRequest = Schemas["AnalysisRunRequest"];
export type AnalysisRunPage = Schemas["Page_AnalysisRunSummary_"];
export type RiskResult = Schemas["RiskResultResponse"];
export type MetricUnit = Schemas["MetricUnit"];
export type RunStatus = Schemas["RunStatus"];
export type VarMethod = Schemas["VarMethod"];
export type ReturnFrequency = Schemas["ReturnFrequency"];

export const analyticsKeys = {
  all: ["analysis-runs"] as const,
  list: (portfolioId: string) => ["analysis-runs", "list", portfolioId] as const,
  run: (runId: string) => ["analysis-runs", "detail", runId] as const,
};

/** A portfolio's stored runs, newest first. */
export function useAnalysisRuns(portfolioId: string, limit = 20) {
  return useQuery({
    queryKey: analyticsKeys.list(portfolioId),
    queryFn: () =>
      api.get<AnalysisRunPage>(`/portfolios/${portfolioId}/analysis-runs`, {
        params: { limit, offset: 0 },
      }),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
  });
}

/**
 * One stored run, with every metric.
 *
 * A completed run cannot change, so refetching it can only cost a request and
 * return the same bytes.
 */
export function useAnalysisRun(runId: string | null) {
  return useQuery({
    queryKey: analyticsKeys.run(runId ?? ""),
    queryFn: () => api.get<AnalysisRunResponse>(`/analysis-runs/${runId ?? ""}`),
    enabled: Boolean(runId),
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useCreateAnalysisRun(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AnalysisRunRequest) =>
      api.post<AnalysisRunResponse>(`/portfolios/${portfolioId}/analysis-runs`, body),
    onSuccess: (run) => {
      // The response is the whole run, so seeding the cache means selecting the
      // new run in the picker does not fetch what we already hold.
      queryClient.setQueryData(analyticsKeys.run(run.id), run);
      void queryClient.invalidateQueries({ queryKey: analyticsKeys.list(portfolioId) });
    },
  });
}

/** The newest run in a page, or null when the portfolio has never been analysed. */
export function newestRunId(page: AnalysisRunPage | undefined): string | null {
  const items: AnalysisRunSummary[] = page?.items ?? [];
  return items[0]?.id ?? null;
}
