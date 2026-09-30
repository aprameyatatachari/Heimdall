import { useId, useState } from "react";

import { cx } from "@/lib/cx";

/** A row of the table alternative. Cells are already formatted strings. */
export interface TableAlternative {
  columns: string[];
  rows: string[][];
  /** Columns holding figures, right-aligned and tabular. Defaults to all but the first. */
  numericFrom?: number;
  /** Shown when the chart has nothing to draw. */
  emptyLabel?: string;
}

export interface ChartFrameProps {
  title: string;
  /** What the axes measure, including units. Always visible. */
  units: string;
  /** The assumptions and provenance belonging under the chart. */
  caption?: React.ReactNode;
  legend?: { label: string; color: string }[];
  /** The same numbers as a real table. Omitted when the chart is itself a table. */
  table?: TableAlternative;
  /** Rendered instead of the chart when there is nothing to plot. */
  empty?: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * The frame every chart sits in: title, units, legend, and the table toggle.
 *
 * The toggle is not a convenience. A chart is a picture of numbers, and the
 * numbers themselves have to be reachable — by a screen reader, by someone
 * checking a figure, and by anyone who simply reads tables faster than shapes.
 * DESIGN.md section 6.6 and the Phase 10 acceptance criteria.
 *
 * `figure`/`figcaption` rather than a bare div: the caption is tied to the
 * content it describes, so the assumptions travel with the picture.
 */
export function ChartFrame({
  title,
  units,
  caption,
  legend,
  table,
  empty,
  children,
  className,
}: ChartFrameProps) {
  const [asTable, setAsTable] = useState(false);
  const headingId = useId();
  const regionId = useId();
  const numericFrom = table?.numericFrom ?? 1;
  const nothingToDraw = Boolean(empty);
  const showToggle = Boolean(table) && !nothingToDraw;

  return (
    <figure
      className={cx("hm-panel flex flex-col gap-4 p-5 md:p-6", className)}
      aria-labelledby={headingId}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id={headingId} className="text-ink text-sm font-medium">
            {title}
          </h3>
          <p className="text-ink-dim mt-1 text-xs">{units}</p>
        </div>
        {showToggle && (
          <button
            type="button"
            onClick={() => setAsTable((current) => !current)}
            aria-pressed={asTable}
            aria-controls={regionId}
            className="border-line-strong text-ink-muted hover:border-gold hover:text-gold rounded-md border px-3 py-1.5 text-xs transition-colors"
          >
            {asTable ? "View as chart" : "View as table"}
          </button>
        )}
      </div>

      {legend && legend.length > 0 && !nothingToDraw && (
        <ul className="flex flex-wrap gap-x-5 gap-y-2">
          {legend.map((entry) => (
            <li key={entry.label} className="text-ink-muted flex items-center gap-2 text-xs">
              <span
                aria-hidden="true"
                className="h-0.5 w-5 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              {entry.label}
            </li>
          ))}
        </ul>
      )}

      <div id={regionId}>
        {nothingToDraw ? (
          <p className="text-ink-dim border-line-soft rounded-md border border-dashed px-4 py-10 text-center text-sm">
            {empty}
          </p>
        ) : asTable && table ? (
          <div className="max-h-96 overflow-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">
                {title}. {units}
              </caption>
              <thead className="bg-surface sticky top-0">
                <tr className="border-line-strong border-b">
                  {table.columns.map((column, index) => (
                    <th
                      key={column}
                      scope="col"
                      className={cx(
                        "hm-eyebrow px-3 py-2",
                        index >= numericFrom ? "text-end" : "text-start",
                      )}
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={table.columns.length}
                      className="text-ink-dim px-3 py-6 text-center"
                    >
                      {table.emptyLabel ?? "No data for this period."}
                    </td>
                  </tr>
                ) : (
                  table.rows.map((row, rowIndex) => (
                    <tr key={rowIndex} className="border-line-soft border-b last:border-b-0">
                      {row.map((cell, cellIndex) => (
                        <td
                          key={cellIndex}
                          className={cx(
                            "px-3 py-2",
                            cellIndex >= numericFrom
                              ? "hm-numeric text-ink text-end"
                              : "text-ink-muted text-start",
                          )}
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        ) : (
          children
        )}
      </div>

      {caption && (
        <figcaption className="text-ink-dim text-xs leading-relaxed">{caption}</figcaption>
      )}
    </figure>
  );
}
