/**
 * Report generation and download.
 *
 * A report is generated on the server and fetched with the session's own access
 * token. The download URL is **not** a public link: it is an authenticated
 * endpoint, so the file is fetched as a blob and handed to the browser from
 * memory rather than opened as a URL a user might copy and share. AGENTS.md
 * section 6.10.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, requestBlob } from "./client";
import type { components } from "./schema";
import type { ReportResponse } from "./types";

type Schemas = components["schemas"];

export type ReportCreateRequest = Schemas["ReportCreateRequest"];
export type ReportPage = Schemas["Page_ReportResponse_"];
export type ReportStatus = Schemas["ReportStatus"];

export const reportKeys = {
  all: ["reports"] as const,
  list: (portfolioId: string) => ["reports", "list", portfolioId] as const,
  detail: (reportId: string) => ["reports", "detail", reportId] as const,
};

/**
 * A portfolio's reports.
 *
 * Generation happens server-side and finishes without telling the browser, so
 * the list polls — but only while something is actually being generated. Once
 * every report is final, polling stops: a list that refetched every two seconds
 * for the life of the tab would be a background request with nothing to find.
 */
export function useReports(portfolioId: string, limit = 20) {
  return useQuery({
    queryKey: reportKeys.list(portfolioId),
    queryFn: () =>
      api.get<ReportPage>(`/portfolios/${portfolioId}/reports`, {
        params: { limit, offset: 0 },
      }),
    enabled: Boolean(portfolioId),
    staleTime: 15_000,
    refetchInterval: (query) => {
      const working = (query.state.data?.items ?? []).some(
        (report) => report.status === "pending" || report.status === "generating",
      );
      return working ? 2_000 : false;
    },
  });
}

/**
 * One report, polled only while it is still being generated.
 *
 * A succeeded or failed report is final, so the interval drops to nothing. A
 * report that never leaves `pending` would otherwise poll for the life of the
 * tab.
 */
export function useReport(reportId: string | null, { poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: reportKeys.detail(reportId ?? ""),
    queryFn: () => api.get<ReportResponse>(`/reports/${reportId ?? ""}`),
    enabled: Boolean(reportId),
    refetchInterval: (query) => {
      if (!poll) return false;
      const status = query.state.data?.status;
      return status === "pending" || status === "generating" ? 2_000 : false;
    },
  });
}

export function useCreateReport(portfolioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ReportCreateRequest) =>
      api.post<ReportResponse>(`/portfolios/${portfolioId}/reports`, body),
    onSuccess: (report) => {
      queryClient.setQueryData(reportKeys.detail(report.id), report);
      void queryClient.invalidateQueries({ queryKey: reportKeys.list(portfolioId) });
    },
  });
}

/**
 * Fetch the PDF and hand it to the browser.
 *
 * The blob URL is revoked immediately after the click: it is a handle to memory
 * this tab holds, and leaving it alive keeps the whole file resident for as long
 * as the page is open.
 */
export function useDownloadReport() {
  return useMutation({
    mutationFn: async ({
      reportId,
      fallbackName,
    }: {
      reportId: string;
      fallbackName: string;
    }) => {
      const { blob, filename } = await requestBlob(`/reports/${reportId}/download`);
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename ?? fallbackName;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
      return filename ?? fallbackName;
    },
  });
}
