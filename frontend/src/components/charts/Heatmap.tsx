import { cx } from "@/lib/cx";

export interface HeatmapProps {
  /** Row and column labels. The matrix is square and shares them. */
  symbols: string[];
  /** Row-major cells. `null` where the pair could not be measured. */
  cells: (number | null)[][];
  formatValue: (value: number) => string;
  ariaLabel: string;
  className?: string;
}

/**
 * A correlation matrix.
 *
 * Rendered as a real table with real header cells, because that is what it is:
 * every cell has a row and a column that name it, and a screen reader can then
 * say "AAPL, MSFT, 0.62" instead of reading a wall of numbers. It needs no
 * separate table alternative for the same reason.
 *
 * Colour is never the only signal — every cell prints its own number. Colour
 * carries sign and strength: gold for positive, blue for negative, intensity
 * with magnitude. DESIGN.md section 2.2.
 */
export function Heatmap({ symbols, cells, formatValue, ariaLabel, className }: HeatmapProps) {
  if (symbols.length === 0) {
    return (
      <p className="text-ink-dim border-line-soft rounded-md border border-dashed px-4 py-10 text-center text-sm">
        No correlation matrix for this period.
      </p>
    );
  }

  // Beyond this many holdings the cells are too small for a legible number, and
  // the colour plus the row and column headers carry the reading.
  const showNumbers = symbols.length <= 9;

  return (
    <div className={cx("overflow-auto", className)}>
      <table className="border-collapse text-xs">
        <caption className="sr-only">{ariaLabel}</caption>
        <thead>
          <tr>
            <td />
            {symbols.map((symbol) => (
              <th
                key={symbol}
                scope="col"
                className="text-ink-dim px-1 pb-2 text-center font-normal"
              >
                {symbol}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((rowSymbol, row) => (
            <tr key={rowSymbol}>
              <th scope="row" className="text-ink-dim pe-3 text-end font-normal">
                {rowSymbol}
              </th>
              {symbols.map((columnSymbol, column) => {
                const value = cells[row]?.[column] ?? null;
                return (
                  <td key={columnSymbol} className="p-0.5">
                    <div
                      className={cx(
                        "hm-numeric flex items-center justify-center rounded-sm",
                        showNumbers ? "size-11 text-xs" : "size-6",
                      )}
                      style={cellStyle(value)}
                    >
                      {value === null ? (
                        <span aria-label="not measured">—</span>
                      ) : showNumbers ? (
                        formatValue(value)
                      ) : (
                        // The number is still announced; only the drawing of it
                        // is dropped, because it would not fit the cell.
                        <span className="sr-only">{formatValue(value)}</span>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function cellStyle(value: number | null): React.CSSProperties {
  if (value === null) {
    return { backgroundColor: "var(--color-surface-2)", color: "var(--color-ink-faint)" };
  }
  const magnitude = Math.min(Math.abs(value), 1);
  const hue = value >= 0 ? "253, 216, 157" : "143, 180, 217";
  return {
    backgroundColor: `rgba(${hue}, ${(0.1 + magnitude * 0.72).toFixed(3)})`,
    // Above roughly half intensity the wash is light enough that white text on
    // it fails contrast, so the text flips rather than the colour being weakened.
    color: magnitude > 0.5 ? "var(--color-void)" : "var(--color-ink)",
  };
}
