import { useState } from "react";

import { useAnalysisRuns } from "@/api/analytics";
import { useCreateReport, useDownloadReport, useReports } from "@/api/reports";
import type { ReportResponse } from "@/api/types";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Disclaimer } from "@/components/Disclaimer";
import { Field } from "@/components/Field";
import { Select } from "@/components/Select";
import { Panel } from "@/components/Panel";
import { Empty, Failed, Loading } from "@/components/states";
import { cx } from "@/lib/cx";
import { formatDateTime } from "@/lib/format";

import { usePortfolioContext } from "./parts/portfolioContext";

const STATUS: Record<string, { word: string; tone: string }> = {
  pending: { word: "Pending", tone: "text-ink-muted" },
  generating: { word: "Generating", tone: "text-ink-muted" },
  succeeded: { word: "Ready", tone: "text-positive" },
  failed: { word: "Failed", tone: "text-negative" },
};

function kilobytes(size: number | null | undefined): string {
  if (size === null || size === undefined) return "";
  return `${Math.max(1, Math.round(size / 1024)).toLocaleString()} KB`;
}

/**
 * Report generation and history.
 *
 * PDF is the only format the backend produces, and there is no scheduling, so
 * neither is offered: an option that does nothing is worse than an absent one.
 *
 * A report is generated from a **stored analysis run**, so the figures in the
 * file are the same figures the analytics screen showed for that run. Leaving
 * the run unchosen uses the most recent one.
 */
export function PortfolioReportsTab() {
  const { portfolioId } = usePortfolioContext();
  const reports = useReports(portfolioId);
  const runs = useAnalysisRuns(portfolioId);
  const create = useCreateReport(portfolioId);
  const download = useDownloadReport();

  const [title, setTitle] = useState("");
  const [analysisRunId, setAnalysisRunId] = useState("");
  const [includeStress, setIncludeStress] = useState(true);
  const [includeSignals, setIncludeSignals] = useState(true);

  const generate = () => {
    create.mutate({
      title: title.trim() || null,
      analysis_run_id: analysisRunId || null,
      include_stress_tests: includeStress,
      include_signals: includeSignals,
    });
  };

  return (
    <div className="flex flex-col gap-8">
      <Panel className="flex flex-col gap-5">
        <div>
          <h2 className="font-display text-ink text-lg font-light">Generate a report</h2>
          <p className="text-ink-muted mt-1 max-w-prose text-xs leading-relaxed">
            A PDF of a stored analysis run, with the assumptions and limitations that belong to
            it. The figures are the ones that run produced, not a fresh calculation.
          </p>
        </div>

        {create.isError && (
          <Alert title="The report could not be started">
            {create.error instanceof Error
              ? create.error.message
              : "Something went wrong. Nothing was generated."}
          </Alert>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            maxLength={200}
            placeholder="Portfolio risk report"
            hint="Optional. A default is used if empty."
          />

          <Select
            label="Analysis run"
            value={analysisRunId}
            onChange={(event) => setAnalysisRunId(event.target.value)}
            hint="The report quotes this run, so it can be checked against the dashboard."
          >
            <option value="">Most recent</option>
            {(runs.data?.items ?? []).map((run) => (
              <option key={run.id} value={run.id}>
                {formatDateTime(run.created_at)} — {run.status}
              </option>
            ))}
          </Select>
        </div>

        <fieldset className="flex flex-col gap-3">
          <legend className="hm-eyebrow mb-1">Include</legend>
          <label className="text-ink-muted flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeStress}
              onChange={(event) => setIncludeStress(event.target.checked)}
              className="accent-gold size-4"
            />
            The most recent stress tests
          </label>
          <label className="text-ink-muted flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={includeSignals}
              onChange={(event) => setIncludeSignals(event.target.checked)}
              className="accent-gold size-4"
            />
            Gjallarhorn Early Warning Signals
          </label>
        </fieldset>

        <div>
          <Button onClick={generate} loading={create.isPending}>
            Generate report
          </Button>
        </div>
      </Panel>

      {download.isError && (
        <Alert title="The report could not be downloaded">
          {download.error instanceof Error
            ? download.error.message
            : "The file could not be fetched."}
        </Alert>
      )}

      {reports.isPending ? (
        <Loading label="Loading reports" />
      ) : reports.isError ? (
        <Failed error={reports.error} onRetry={() => void reports.refetch()} />
      ) : reports.data.items.length === 0 ? (
        <Panel>
          <Empty
            title="No reports yet"
            body="A generated report is a snapshot of one analysis: what it measured, over what window, and under which assumptions."
          />
        </Panel>
      ) : (
        <ul className="flex flex-col gap-3">
          {reports.data.items.map((report) => (
            <ReportRow
              key={report.id}
              report={report}
              downloading={download.isPending && download.variables?.reportId === report.id}
              onDownload={() =>
                download.mutate({
                  reportId: report.id,
                  fallbackName: report.filename ?? `${report.title}.pdf`,
                })
              }
              onRetry={() =>
                create.mutate({
                  title: report.title,
                  analysis_run_id: report.analysis_run_id,
                  include_stress_tests: includeStress,
                  include_signals: includeSignals,
                })
              }
              retrying={create.isPending}
            />
          ))}
        </ul>
      )}

      <Disclaimer />
    </div>
  );
}

function ReportRow({
  report,
  downloading,
  onDownload,
  onRetry,
  retrying,
}: {
  report: ReportResponse;
  downloading: boolean;
  onDownload: () => void;
  onRetry: () => void;
  retrying: boolean;
}) {
  const status = STATUS[report.status] ?? { word: report.status, tone: "text-ink-muted" };
  const working = report.status === "pending" || report.status === "generating";

  return (
    <li className="hm-panel flex flex-wrap items-center justify-between gap-4 p-5">
      <div>
        <p className="text-ink text-sm">{report.title}</p>
        <p className="text-ink-dim mt-1 text-xs">
          {formatDateTime(report.created_at)}
          <span aria-hidden="true"> · </span>
          <span className={cx("uppercase", status.tone)}>{status.word}</span>
          {report.size_bytes ? (
            <>
              <span aria-hidden="true"> · </span>
              {kilobytes(report.size_bytes)}
            </>
          ) : null}
          <span aria-hidden="true"> · </span>
          PDF
        </p>
        {report.status === "failed" && (
          <p className="text-negative mt-2 max-w-prose text-xs">
            {report.error_message ?? "The report could not be generated."}
          </p>
        )}
        {working && (
          <p className="text-ink-dim mt-2 text-xs" role="status">
            Still being generated. This page updates when it is ready.
          </p>
        )}
      </div>

      <div className="flex gap-3">
        {report.status === "succeeded" && (
          <Button variant="secondary" size="sm" onClick={onDownload} loading={downloading}>
            Download
            <span className="sr-only"> {report.title}</span>
          </Button>
        )}
        {report.status === "failed" && (
          <Button variant="ghost" size="sm" onClick={onRetry} loading={retrying}>
            Try again
          </Button>
        )}
      </div>
    </li>
  );
}
