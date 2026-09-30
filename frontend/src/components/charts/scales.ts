/**
 * The arithmetic behind the charts.
 *
 * Kept apart from the components so the parts that are easy to get wrong — tick
 * selection, empty and single-point domains, gaps in a series — can be tested
 * without rendering anything.
 *
 * Charts here are hand-drawn SVG rather than a charting library. Four reasons,
 * in order: a library's tooltips and legends are rarely accessible and cannot be
 * made so from outside; the "view as table" alternative has to read the same
 * numbers the chart drew; a gap must stay a gap, and most libraries interpolate
 * across one by default; and the whole of this file plus its components is
 * smaller than any library's runtime.
 */

export interface Extent {
  min: number;
  max: number;
}

/** The span of every number present, ignoring gaps. Null when all are gaps. */
export function extentOf(values: readonly (number | null)[]): Extent | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (value === null || !Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (min === Number.POSITIVE_INFINITY) return null;
  return { min, max };
}

/**
 * Widen a domain so the plot has room and a flat series still has an axis.
 *
 * A series that never moves has zero span; without padding it would be drawn on
 * top of the axis, and its ticks would all carry the same number.
 */
export function padExtent(extent: Extent, { include }: { include?: number } = {}): Extent {
  let { min, max } = extent;
  if (include !== undefined) {
    min = Math.min(min, include);
    max = Math.max(max, include);
  }
  if (min === max) {
    const nudge = Math.abs(min) > 0 ? Math.abs(min) * 0.05 : 1;
    return { min: min - nudge, max: max + nudge };
  }
  const padding = (max - min) * 0.08;
  return { min: min - padding, max: max + padding };
}

/**
 * Round tick values, covering the domain.
 *
 * The step is one of these factors times a power of ten, which is what makes an
 * axis readable: 0.05, 0.1, 0.15 rather than 0.0473, 0.0946.
 *
 * The ladder includes 1.5 and 3 rather than jumping 1 → 2 → 5. On a real value
 * series the ideal step landed just above 1, and rounding it to 2 nearly halved
 * the number of ticks: a chart spanning 12,000 to 15,200 drew two of them.
 */
const STEP_FACTORS = [1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10];

export function niceTicks(extent: Extent, count = 5): number[] {
  const span = extent.max - extent.min;
  if (!Number.isFinite(span) || span <= 0) return [extent.min];

  const rough = span / Math.max(1, count - 1);
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)));
  const normalized = rough / magnitude;
  const stepFactor = STEP_FACTORS.find((factor) => normalized <= factor) ?? 10;
  const step = stepFactor * magnitude;

  const first = Math.ceil(extent.min / step) * step;
  const ticks: number[] = [];
  // Rounding keeps 0.30000000000000004 out of the axis labels.
  for (let tick = first; tick <= extent.max + step / 1000; tick += step) {
    ticks.push(Number(tick.toFixed(10)));
  }
  return ticks.length > 0 ? ticks : [extent.min];
}

export interface Plot {
  width: number;
  height: number;
  padding: { top: number; right: number; bottom: number; left: number };
}

/** Maps a value in `domain` onto its vertical pixel position inside `plot`. */
export function verticalScale(domain: Extent, plot: Plot): (value: number) => number {
  const top = plot.padding.top;
  const bottom = plot.height - plot.padding.bottom;
  const span = domain.max - domain.min || 1;
  return (value) => bottom - ((value - domain.min) / span) * (bottom - top);
}

/** Maps an index in a series of `count` points onto its horizontal position. */
export function horizontalScale(count: number, plot: Plot): (index: number) => number {
  const left = plot.padding.left;
  const right = plot.width - plot.padding.right;
  if (count <= 1) return () => (left + right) / 2;
  return (index) => left + (index / (count - 1)) * (right - left);
}

/**
 * An SVG path for a series, broken wherever a point is missing.
 *
 * Every gap starts a new subpath, so a missing observation shows as a break in
 * the line. Interpolating across one would invent data the analysis never had,
 * and dropping it to zero would invent a crash. DESIGN.md section 6.6.
 */
export function linePath(
  values: readonly (number | null)[],
  x: (index: number) => number,
  y: (value: number) => number,
): string {
  let path = "";
  let penDown = false;
  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      penDown = false;
      return;
    }
    const command = penDown ? "L" : "M";
    path += `${command}${x(index).toFixed(2)},${y(value).toFixed(2)} `;
    penDown = true;
  });
  return path.trim();
}

/**
 * An SVG path filling the area between a series and a baseline.
 *
 * Each run of consecutive points is closed on its own, so a gap leaves a gap in
 * the fill rather than a wedge spanning it.
 */
export function areaPath(
  values: readonly (number | null)[],
  x: (index: number) => number,
  y: (value: number) => number,
  baseline: number,
): string {
  const floor = y(baseline).toFixed(2);
  let path = "";
  let run: { index: number; value: number }[] = [];

  const flush = () => {
    if (run.length === 0) return;
    const first = run[0];
    const last = run[run.length - 1];
    if (!first || !last) return;
    path += `M${x(first.index).toFixed(2)},${floor} `;
    for (const point of run) {
      path += `L${x(point.index).toFixed(2)},${y(point.value).toFixed(2)} `;
    }
    path += `L${x(last.index).toFixed(2)},${floor} Z `;
    run = [];
  };

  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      flush();
      return;
    }
    run.push({ index, value });
  });
  flush();
  return path.trim();
}

/**
 * Which points to label on the horizontal axis.
 *
 * Always the first and the last, then evenly spaced indices between them, so
 * the axis states the range it covers however many points there are.
 */
export function axisIndices(count: number, wanted = 5): number[] {
  if (count <= 0) return [];
  if (count <= wanted) return Array.from({ length: count }, (_, index) => index);
  const step = (count - 1) / (wanted - 1);
  const indices = new Set<number>();
  for (let tick = 0; tick < wanted; tick += 1) {
    indices.add(Math.round(tick * step));
  }
  return [...indices].sort((first, second) => first - second);
}
