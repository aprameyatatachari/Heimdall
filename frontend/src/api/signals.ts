/**
 * Gjallarhorn: signals, alert rules and monitoring runs.
 *
 * Signals are living state rather than a stored computation — the same signal
 * changes severity, gets acknowledged, and is resolved by the engine when its
 * condition clears — so nothing here is cached indefinitely the way an analysis
 * run is. Every action invalidates the summary as well as the list, because the
 * counts by severity are what a reader looks at first.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";
import type {
  AlertRuleResponse,
  MonitoringRunResponse,
  SignalSummaryResponse,
  WarningSignalResponse,
} from "./types";

type Schemas = components["schemas"];

export type AlertRuleCatalogue = Schemas["AlertRuleCatalogueResponse"];
export type AlertRuleCatalogueItem = Schemas["AlertRuleCatalogueItem"];
export type AlertRuleCreateRequest = Schemas["AlertRuleCreateRequest"];
export type AlertRuleUpdateRequest = Schemas["AlertRuleUpdateRequest"];
export type SignalPage = Schemas["Page_WarningSignalResponse_"];
export type MonitoringRunPage = Schemas["Page_MonitoringRunSummary_"];
export type MonitoringRunSummary = Schemas["MonitoringRunSummary"];
export type SignalSeverity = Schemas["SignalSeverity"];
export type SignalStatus = Schemas["SignalStatus"];
export type SignalEvent = Schemas["SignalEventResponse"];
export type RuleType = Schemas["RuleType"];

export interface SignalFilters {
  status?: SignalStatus[];
  severity?: SignalSeverity[];
  type?: RuleType[];
}

export const signalKeys = {
  all: ["signals"] as const,
  summary: (portfolioId: string) => ["signals", "summary", portfolioId] as const,
  list: (portfolioId: string, filters: SignalFilters) =>
    ["signals", "list", portfolioId, filters] as const,
  detail: (signalId: string) => ["signals", "detail", signalId] as const,
  ruleTypes: ["alert-rule-types"] as const,
  rules: (portfolioId: string) => ["alert-rules", portfolioId] as const,
  monitoringRuns: (portfolioId: string) => ["monitoring-runs", portfolioId] as const,
};

/* -------------------------------------------------------------------------- */
/* Signals                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Polling, for the screens that stay open.
 *
 * A check can be made by something other than this page — the scheduler on the
 * server, or the same portfolio open in another tab — so an open screen asks
 * again on an interval instead of assuming it is the only thing that can change
 * a signal. Paused while the tab is hidden, which is React Query's default.
 */
export interface LiveOptions {
  refetchInterval?: number;
}

export function useSignalSummary(portfolioId: string, live: LiveOptions = {}) {
  return useQuery({
    queryKey: signalKeys.summary(portfolioId),
    queryFn: () => api.get<SignalSummaryResponse>(`/portfolios/${portfolioId}/signals/summary`),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
    refetchInterval: live.refetchInterval,
  });
}

export function useSignals(
  portfolioId: string,
  filters: SignalFilters = {},
  limit = 50,
  live: LiveOptions = {},
) {
  return useQuery({
    queryKey: signalKeys.list(portfolioId, filters),
    queryFn: () =>
      api.get<SignalPage>(`/portfolios/${portfolioId}/signals`, {
        params: {
          signal_status: filters.status,
          severity: filters.severity,
          signal_type: filters.type,
          limit,
          offset: 0,
        },
      }),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
    refetchInterval: live.refetchInterval,
  });
}

/** One signal, with its full event trail. */
export function useSignal(signalId: string | null) {
  return useQuery({
    queryKey: signalKeys.detail(signalId ?? ""),
    queryFn: () => api.get<WarningSignalResponse>(`/signals/${signalId ?? ""}`),
    enabled: Boolean(signalId),
  });
}

/** Everything a change to one signal could be visible in. */
export function invalidateSignals(
  queryClient: ReturnType<typeof useQueryClient>,
  portfolioId: string,
) {
  void queryClient.invalidateQueries({ queryKey: signalKeys.all });
  void queryClient.invalidateQueries({ queryKey: signalKeys.summary(portfolioId) });
}

export function useAcknowledgeSignal(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) =>
      api.post<WarningSignalResponse>(`/signals/${signalId}/acknowledge`),
    onSuccess: (signal) => {
      queryClient.setQueryData(signalKeys.detail(signal.id), signal);
      invalidateSignals(queryClient, portfolioId);
    },
  });
}

export function useDismissSignal(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (signalId: string) =>
      api.post<WarningSignalResponse>(`/signals/${signalId}/dismiss`),
    onSuccess: (signal) => {
      queryClient.setQueryData(signalKeys.detail(signal.id), signal);
      invalidateSignals(queryClient, portfolioId);
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Alert rules                                                                 */
/* -------------------------------------------------------------------------- */

/** The nine rule types and their documented defaults. Fixed per release. */
export function useAlertRuleTypes() {
  return useQuery({
    queryKey: signalKeys.ruleTypes,
    queryFn: () => api.get<AlertRuleCatalogue>("/alert-rule-types"),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export function useAlertRules(portfolioId: string) {
  return useQuery({
    queryKey: signalKeys.rules(portfolioId),
    queryFn: () => api.get<AlertRuleResponse[]>(`/portfolios/${portfolioId}/alert-rules`),
    enabled: Boolean(portfolioId),
  });
}

export function useCreateAlertRule(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AlertRuleCreateRequest) =>
      api.post<AlertRuleResponse>(`/portfolios/${portfolioId}/alert-rules`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signalKeys.rules(portfolioId) });
    },
  });
}

export function useUpdateAlertRule(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ruleId, body }: { ruleId: string; body: AlertRuleUpdateRequest }) =>
      api.patch<AlertRuleResponse>(`/portfolios/${portfolioId}/alert-rules/${ruleId}`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signalKeys.rules(portfolioId) });
    },
  });
}

export function useDeleteAlertRule(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) =>
      api.delete<void>(`/portfolios/${portfolioId}/alert-rules/${ruleId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signalKeys.rules(portfolioId) });
    },
  });
}

/**
 * Provision the documented rule set, or reset every rule to it.
 *
 * Without `restore` the call only fills in rule types that are missing, so it is
 * safe to run on a portfolio that already has rules.
 */
export function useProvisionDefaultRules(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (restore: boolean) =>
      api.post<AlertRuleResponse[]>(
        `/portfolios/${portfolioId}/alert-rules/defaults`,
        undefined,
        { params: { restore } },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signalKeys.rules(portfolioId) });
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Monitoring runs                                                             */
/* -------------------------------------------------------------------------- */

export function useMonitoringRuns(portfolioId: string, limit = 10, live: LiveOptions = {}) {
  return useQuery({
    queryKey: signalKeys.monitoringRuns(portfolioId),
    queryFn: () =>
      api.get<MonitoringRunPage>(`/portfolios/${portfolioId}/monitoring-runs`, {
        params: { limit, offset: 0 },
      }),
    enabled: Boolean(portfolioId),
    staleTime: 30_000,
    refetchInterval: live.refetchInterval,
  });
}

export function useRunMonitoring(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.post<MonitoringRunResponse>(`/portfolios/${portfolioId}/monitoring-runs`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: signalKeys.monitoringRuns(portfolioId) });
      invalidateSignals(queryClient, portfolioId);
    },
  });
}
