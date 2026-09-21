import { useEffect, useId, useState } from "react";

import { ApiError, type ApiErrorDetail } from "@/api/errors";
import { useImportPositions, type ImportMode } from "@/api/portfolios";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";
import { Money } from "@/components/Figure";
import { cx } from "@/lib/cx";

const MODES: { value: ImportMode; label: string; description: string }[] = [
  {
    value: "merge",
    label: "Merge",
    description: "Add new holdings and combine with any the portfolio already has.",
  },
  {
    value: "replace",
    label: "Replace",
    description: "Remove every existing holding first, then import the file.",
  },
  {
    value: "reject",
    label: "Reject duplicates",
    description: "Fail the import if the file names a holding already in the portfolio.",
  },
];

/**
 * Row-level import errors.
 *
 * The backend reports the line, the field and the reason. Showing them as a
 * table rather than one sentence is the difference between a user fixing their
 * file and guessing at it. AGENTS.md section 6.6.
 */
function RowErrors({ details }: { details: ApiErrorDetail[] }) {
  const rows = details.filter((detail) => detail.row !== null && detail.row !== undefined);
  const other = details.filter((detail) => detail.row === null || detail.row === undefined);

  return (
    <div className="flex flex-col gap-4">
      {rows.length > 0 && (
        <div className="border-negative overflow-hidden rounded-md border">
          <table className="w-full text-sm">
            <caption className="sr-only">Rows that could not be imported</caption>
            <thead>
              <tr className="bg-negative-dim text-ink">
                <th
                  scope="col"
                  className="px-3 py-2 text-start text-2xs font-medium tracking-wider uppercase"
                >
                  Line
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-start text-2xs font-medium tracking-wider uppercase"
                >
                  Column
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-start text-2xs font-medium tracking-wider uppercase"
                >
                  Problem
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((detail, index) => (
                <tr key={`${detail.row}-${index}`} className="border-line-soft border-t">
                  <td className="hm-numeric text-ink px-3 py-2 align-top">{detail.row}</td>
                  <td className="text-ink-muted px-3 py-2 align-top">{detail.field ?? "—"}</td>
                  <td className="text-ink-muted px-3 py-2">{detail.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {other.length > 0 && (
        <ul className="text-ink-muted flex flex-col gap-1 text-sm">
          {other.map((detail, index) => (
            <li key={index}>{detail.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CsvImportDialog({
  open,
  onClose,
  portfolioId,
}: {
  open: boolean;
  onClose: () => void;
  portfolioId: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<ImportMode>("merge");
  const modeGroupId = useId();
  const importPositions = useImportPositions(portfolioId);

  useEffect(() => {
    if (open) return;
    setFile(null);
    setMode("merge");
    importPositions.reset();
    // `importPositions` is stable for the lifetime of the dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const error = importPositions.error;
  const apiError = error instanceof ApiError ? error : null;
  const result = importPositions.data;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Import holdings"
      description="A UTF-8 CSV with one row per holding."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={importPositions.isPending}>
            {result ? "Done" : "Cancel"}
          </Button>
          {!result && (
            <Button
              loading={importPositions.isPending}
              disabled={!file}
              onClick={() => file && importPositions.mutate({ file, mode })}
            >
              Import
            </Button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-6">
        {apiError && (
          <div>
            <Alert tone="error" title="This file was not imported">
              {apiError.message}
              {apiError.details.length > 0 && (
                <span className="mt-1 block">
                  Nothing was changed. Correct the rows below and import again.
                </span>
              )}
            </Alert>
            {apiError.details.length > 0 && (
              <div className="mt-4">
                <RowErrors details={apiError.details} />
              </div>
            )}
          </div>
        )}

        {error && !apiError && (
          <Alert tone="error">Could not reach Heimdall. Nothing was imported.</Alert>
        )}

        {!result && (
          <>
            <div>
              <p className="text-ink-muted text-sm">
                Expected columns: <code className="text-ink">symbol</code>,{" "}
                <code className="text-ink">quantity</code>,{" "}
                <code className="text-ink">average_cost</code>, and optionally{" "}
                <code className="text-ink">purchase_date</code>. Column order does not matter.
              </p>

              <label className="border-line hover:border-gold mt-4 flex cursor-pointer flex-col items-center rounded-md border border-dashed px-6 py-8 text-center transition-colors">
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="sr-only"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
                <span className="text-ink text-sm font-medium">
                  {file ? file.name : "Choose a CSV file"}
                </span>
                <span className="text-ink-dim mt-1 text-xs">
                  {file ? `${(file.size / 1024).toFixed(1)} KB` : "or drag one onto this area"}
                </span>
              </label>
            </div>

            <fieldset>
              <legend className="text-ink-muted mb-3 text-sm font-medium">
                How should this file meet what is already here?
              </legend>
              <div className="flex flex-col gap-2">
                {MODES.map((option) => (
                  // Grid rather than nested spans so the label's own text sits
                  // one level down, which is what a label needs to be readable.
                  <label
                    key={option.value}
                    htmlFor={`${modeGroupId}-${option.value}`}
                    className={cx(
                      "grid cursor-pointer grid-cols-[auto_1fr] items-start gap-x-3 rounded-md border p-3 transition-colors",
                      mode === option.value
                        ? "border-gold bg-surface-2"
                        : "border-line hover:border-line-strong",
                    )}
                  >
                    <input
                      id={`${modeGroupId}-${option.value}`}
                      type="radio"
                      name="import-mode"
                      value={option.value}
                      checked={mode === option.value}
                      onChange={() => setMode(option.value)}
                      className="accent-gold row-span-2 mt-1"
                    />
                    <span className="text-ink text-sm font-medium">{option.label}</span>
                    <span className="text-ink-dim text-xs">{option.description}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          </>
        )}

        {result && (
          <div className="border-line rounded-md border p-4">
            <p className="text-ink font-medium">Imported</p>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              {[
                ["Rows read", result.rows_read],
                ["Holdings created", result.positions_created],
                ["Holdings merged", result.positions_merged],
                ["Holdings removed", result.positions_removed],
              ].map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-4 text-sm">
                  <dt className="text-ink-muted">{label}</dt>
                  <dd className="hm-numeric text-ink">{value}</dd>
                </div>
              ))}
              <div className="flex items-baseline justify-between gap-4 text-sm sm:col-span-2">
                <dt className="text-ink-muted">Total cost basis</dt>
                <dd>
                  <Money
                    value={result.total_cost_basis}
                    currency={result.positions[0]?.currency ?? "USD"}
                    className="text-ink"
                  />
                </dd>
              </div>
            </dl>
            <p className="text-ink-dim mt-4 text-xs">
              This portfolio now holds {result.position_count}{" "}
              {result.position_count === 1 ? "position" : "positions"}. Refresh prices to value
              them.
            </p>
          </div>
        )}
      </div>
    </Dialog>
  );
}
