import { useEffect, useMemo, useRef, useState } from "react";

import { cx } from "@/lib/cx";

import {
  areaPath,
  axisIndices,
  extentOf,
  horizontalScale,
  linePath,
  niceTicks,
  padExtent,
  verticalScale,
  type Plot,
} from "./scales";

export interface LineSeries {
  label: string;
  color: string;
  /** One value per label. `null` is a gap, and is drawn as one. */
  values: (number | null)[];
  /** Fill the area between the line and the baseline. For drawdown. */
  fill?: boolean;
}

export interface LineChartProps {
  /** ISO dates, one per point. */
  labels: string[];
  series: LineSeries[];
  formatValue: (value: number) => string;
  formatLabel: (label: string) => string;
  /** A horizontal rule at this value, and the floor for any filled area. */
  baseline?: number;
  /** Keep the baseline inside the vertical domain even if no point reaches it. */
  includeBaseline?: boolean;
  /** What the chart shows, for anyone who will not see it. */
  ariaLabel: string;
  height?: number;
  className?: string;
}

/** Until the element has been measured. Also what a server or jsdom renders at. */
const FALLBACK_WIDTH = 720;

/** Below this the axis needs fewer labels and a narrower gutter. */
const NARROW = 460;

/**
 * A time series, or several sharing one axis.
 *
 * Hovering reads the values at a date out above the chart rather than into a
 * floating tooltip: a tooltip has to be positioned, clipped, dismissed and made
 * reachable, and every one of those is a way for it to go wrong. A fixed readout
 * cannot cover the line it describes, and it holds the last point when the
 * pointer is away, so the newest figure is on screen without any interaction.
 *
 * Keyboard and screen-reader users are served by the "view as table" toggle in
 * the frame around this, which exposes the same numbers as a real table.
 */
export function LineChart({
  labels,
  series,
  formatValue,
  formatLabel,
  baseline,
  includeBaseline = false,
  ariaLabel,
  height = 260,
  className,
}: LineChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  const frameRef = useRef<HTMLDivElement | null>(null);

  // The viewBox is the element's own width in CSS pixels, so one user unit is
  // one pixel at every size. A fixed viewBox scaled to fit shrinks the axis text
  // with it: at 720 units in a 343-pixel column, an 11-unit label renders at
  // about five pixels, which is a decoration rather than a label.
  useEffect(() => {
    const node = frameRef.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const measured = entries[0]?.contentRect.width ?? 0;
      if (measured > 0) setWidth(Math.round(measured));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const narrow = width < NARROW;

  const plot: Plot = useMemo(
    () => ({
      width,
      height,
      padding: { top: 14, right: 18, bottom: 30, left: narrow ? 48 : 74 },
    }),
    [height, width, narrow],
  );

  const geometry = useMemo(() => {
    const everyValue = series.flatMap((line) => line.values);
    const raw = extentOf(everyValue);
    if (!raw || labels.length === 0) return null;

    const domain = padExtent(raw, {
      include: includeBaseline && baseline !== undefined ? baseline : undefined,
    });
    const x = horizontalScale(labels.length, plot);
    const y = verticalScale(domain, plot);
    return { domain, x, y, ticks: niceTicks(domain, height < 220 ? 4 : 5) };
  }, [series, labels.length, plot, baseline, includeBaseline, height]);

  if (!geometry) {
    return (
      <p className="text-ink-dim border-line-soft rounded-md border border-dashed px-4 py-10 text-center text-sm">
        No data for this period.
      </p>
    );
  }

  const { x, y, ticks } = geometry;
  const readoutIndex = hovered ?? labels.length - 1;
  const readoutLabel = labels[readoutIndex];
  const left = plot.padding.left;
  const right = plot.width - plot.padding.right;
  const top = plot.padding.top;
  const bottom = plot.height - plot.padding.bottom;

  /** Nearest point to the pointer, in the element's own pixels. */
  const trackPointer = (event: React.PointerEvent<SVGRectElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width <= 0) return;
    const ratio = (event.clientX - box.left) / box.width;
    const index = Math.round(ratio * (labels.length - 1));
    setHovered(Math.min(Math.max(index, 0), labels.length - 1));
  };

  return (
    <div ref={frameRef} className={cx("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-xs">
        <span className="text-ink-dim">
          {readoutLabel ? formatLabel(readoutLabel) : ""}
          {hovered === null && " (latest)"}
        </span>
        {series.map((line) => {
          const value = line.values[readoutIndex];
          return (
            <span key={line.label} className="flex items-baseline gap-2">
              <span aria-hidden="true" style={{ color: line.color }}>
                ●
              </span>
              <span className="text-ink-muted">{line.label}</span>
              <span className="hm-numeric text-ink">
                {value === null || value === undefined ? "—" : formatValue(value)}
              </span>
            </span>
          );
        })}
      </div>

      <svg
        viewBox={`0 0 ${plot.width} ${plot.height}`}
        role="img"
        aria-label={ariaLabel}
        className="h-auto w-full touch-pan-y"
      >
        {/* Horizontal grid only, per DESIGN.md section 6.6. */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={left}
              x2={right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--color-line-soft)"
              strokeWidth={1}
            />
            <text
              x={left - 10}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fill="var(--color-ink-dim)"
              fontSize={11}
              className="hm-numeric"
            >
              {formatValue(tick)}
            </text>
          </g>
        ))}

        {baseline !== undefined && (
          <line
            x1={left}
            x2={right}
            y1={y(baseline)}
            y2={y(baseline)}
            stroke="var(--color-line-strong)"
            strokeWidth={1}
          />
        )}

        {series.map((line) =>
          line.fill ? (
            <path
              key={`${line.label}-fill`}
              d={areaPath(line.values, x, y, baseline ?? geometry.domain.min)}
              fill={line.color}
              opacity={0.14}
            />
          ) : null,
        )}

        {series.map((line) => (
          <path
            key={line.label}
            d={linePath(line.values, x, y)}
            fill="none"
            stroke={line.color}
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {axisIndices(labels.length, narrow ? 3 : 5).map((index) => {
          const label = labels[index];
          if (!label) return null;
          return (
            <text
              key={index}
              x={x(index)}
              y={plot.height - 8}
              textAnchor={
                index === 0 ? "start" : index === labels.length - 1 ? "end" : "middle"
              }
              fill="var(--color-ink-dim)"
              fontSize={11}
            >
              {formatLabel(label)}
            </text>
          );
        })}

        {hovered !== null && (
          <g aria-hidden="true">
            <line
              x1={x(hovered)}
              x2={x(hovered)}
              y1={top}
              y2={bottom}
              stroke="var(--color-line-strong)"
              strokeWidth={1}
            />
            {series.map((line) => {
              const value = line.values[hovered];
              if (value === null || value === undefined) return null;
              return (
                <circle
                  key={`${line.label}-dot`}
                  cx={x(hovered)}
                  cy={y(value)}
                  r={3}
                  fill={line.color}
                />
              );
            })}
          </g>
        )}

        {/* The pointer target. Transparent, and the full plot area, so the
            readout follows the cursor rather than requiring the line be hit. */}
        <rect
          x={left}
          y={top}
          width={Math.max(0, right - left)}
          height={Math.max(0, bottom - top)}
          fill="transparent"
          onPointerMove={trackPointer}
          onPointerLeave={() => setHovered(null)}
        />
      </svg>
    </div>
  );
}
