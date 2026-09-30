/**
 * Stress-test queries.
 *
 * Like an analysis run, a completed stress test is immutable: it records what a
 * scenario implied for the holdings as they stood, and re-running it later
 * against different prices would be a different test. Runs are therefore cached
 * indefinitely and never refetched on focus. AGENTS.md section 6.8.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";
import type { StressTestRunResponse } from "./types";

type Schemas = components["schemas"];

export type ScenarioCatalogue = Schemas["ScenarioCatalogueResponse"];
export type ScenarioCatalogueItem = Schemas["ScenarioCatalogueItem"];
export type StressTestRequest = Schemas["StressTestRequest"];
export type StressTestRunSummary = Schemas["StressTestRunSummary"];
export type StressTestPage = Schemas["Page_StressTestRunSummary_"];
export type PositionImpact = Schemas["PositionImpactResponse"];
export type ShockRequest = Schemas["ShockRequest"];
export type ShockTargetType = Schemas["ShockTargetType"];

export const stressKeys = {
  all: ["stress-tests"] as const,
  catalogue: ["stress-scenarios"] as const,
  list: (portfolioId: string) => ["stress-tests", "list", portfolioId] as const,
  run: (runId: string) => ["stress-tests", "detail", runId] as const,
};

/**
 * The historical scenario catalogue.
 *
 * Fixed for the life of a release, so it is fetched once and kept.
 */
export function useScenarioCatalogue() {
  return useQuery({
    queryKey: stressKeys.catalogue,
    queryFn: () => api.get<ScenarioCatalogue>("/stress-scenarios"),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function useStressRuns(portfolioId: string, limit = 20) {
  return useQuery({
    queryKey: stressKeys.list(portfolioId),
    queryFn: () =>
      api.get<StressTestPage>(`/portfolios/${portfolioId}/stress-tests`, {
        params: { limit, offset: 0 },
      }),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
  });
}

export function useStressRun(runId: string | null) {
  return useQuery({
    queryKey: stressKeys.run(runId ?? ""),
    queryFn: () => api.get<StressTestRunResponse>(`/stress-tests/${runId ?? ""}`),
    enabled: Boolean(runId),
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useRunStressTest(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StressTestRequest) =>
      api.post<StressTestRunResponse>(`/portfolios/${portfolioId}/stress-tests`, body),
    onSuccess: (run) => {
      queryClient.setQueryData(stressKeys.run(run.id), run);
      void queryClient.invalidateQueries({ queryKey: stressKeys.list(portfolioId) });
    },
  });
}

export function newestStressRunId(page: StressTestPage | undefined): string | null {
  const items: StressTestRunSummary[] = page?.items ?? [];
  return items[0]?.id ?? null;
}
