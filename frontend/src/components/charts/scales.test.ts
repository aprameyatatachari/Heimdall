import { describe, expect, it } from "vitest";

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

const plot: Plot = {
  width: 100,
  height: 100,
  padding: { top: 0, right: 0, bottom: 0, left: 0 },
};

describe("extentOf", () => {
  it("spans only the values that exist", () => {
    expect(extentOf([3, null, -1, 7, null])).toEqual({ min: -1, max: 7 });
  });

  it("is null when every point is a gap", () => {
    // Not {min: 0, max: 0}: a chart of nothing must not look like a chart of zero.
    expect(extentOf([null, null])).toBeNull();
    expect(extentOf([])).toBeNull();
  });

  it("ignores values that are not finite", () => {
    expect(extentOf([1, Number.NaN, Number.POSITIVE_INFINITY, 2])).toEqual({ min: 1, max: 2 });
  });
});

describe("padExtent", () => {
  it("gives a flat series an axis to sit on", () => {
    const padded = padExtent({ min: 0.2, max: 0.2 });

    expect(padded.min).toBeLessThan(0.2);
    expect(padded.max).toBeGreaterThan(0.2);
  });

  it("can be forced to include a baseline the data never reaches", () => {
    // Drawdown is always negative, but the chart has to show the zero line it is
    // measured from.
    const padded = padExtent({ min: -0.3, max: -0.05 }, { include: 0 });

    expect(padded.max).toBeGreaterThanOrEqual(0);
  });
});

describe("niceTicks", () => {
  it("chooses round steps", () => {
    const ticks = niceTicks({ min: 0, max: 0.47 }, 5);

    expect(ticks.length).toBeGreaterThan(2);
    // Every gap is the same, and it is a number a reader recognises.
    const steps = ticks.slice(1).map((tick, index) => tick - (ticks[index] ?? 0));
    for (const step of steps) expect(step).toBeCloseTo(steps[0] ?? 0, 10);
  });

  it("does not leave floating-point dust in the labels", () => {
    for (const tick of niceTicks({ min: 0, max: 1 }, 5)) {
      expect(String(tick).length).toBeLessThan(8);
    }
  });

  it("does not halve the tick count to keep a round number", () => {
    // The case that prompted the step ladder: a value chart spanning 12,000 to
    // 15,200 drew two ticks, because the ideal step sat just above 1,000 and was
    // rounded up to 2,000.
    expect(niceTicks({ min: 12_000, max: 15_200 }, 5).length).toBeGreaterThanOrEqual(4);
  });

  it("survives a domain with no span", () => {
    expect(niceTicks({ min: 5, max: 5 })).toEqual([5]);
  });
});

describe("linePath", () => {
  const x = horizontalScale(4, plot);
  const y = verticalScale({ min: 0, max: 10 }, plot);

  it("draws one subpath through consecutive points", () => {
    const path = linePath([1, 2, 3, 4], x, y);

    expect(path.match(/M/g)).toHaveLength(1);
  });

  it("breaks the line at a gap rather than bridging it", () => {
    // Two runs, so two "move to" commands: the missing observation leaves a hole
    // instead of a straight line across it. DESIGN.md section 6.6.
    const path = linePath([1, 2, null, 4], x, y);

    expect(path.match(/M/g)).toHaveLength(2);
  });

  it("is empty when there is nothing to draw", () => {
    expect(linePath([null, null], x, y)).toBe("");
  });
});

describe("areaPath", () => {
  const x = horizontalScale(4, plot);
  const y = verticalScale({ min: -1, max: 0 }, plot);

  it("closes each run of points on its own", () => {
    const path = areaPath([-0.1, -0.2, null, -0.4], x, y, 0);

    expect(path.match(/Z/g)).toHaveLength(2);
  });

  it("fills nothing when every point is a gap", () => {
    expect(areaPath([null], x, y, 0)).toBe("");
  });
});

describe("axisIndices", () => {
  it("always labels the first and last point", () => {
    const indices = axisIndices(100, 5);

    expect(indices[0]).toBe(0);
    expect(indices[indices.length - 1]).toBe(99);
  });

  it("labels every point when there are few", () => {
    expect(axisIndices(3, 5)).toEqual([0, 1, 2]);
  });

  it("has nothing to label for an empty series", () => {
    expect(axisIndices(0)).toEqual([]);
  });
});

describe("the scales", () => {
  it("puts a single point in the middle rather than at the edge", () => {
    expect(horizontalScale(1, plot)(0)).toBe(50);
  });

  it("maps the top of the domain to the top of the plot", () => {
    const y = verticalScale({ min: 0, max: 10 }, plot);

    expect(y(10)).toBe(0);
    expect(y(0)).toBe(100);
  });
});
