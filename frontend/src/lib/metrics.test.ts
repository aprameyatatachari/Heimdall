import { describe, expect, it } from "vitest";

import type { RiskResult } from "@/api/analytics";
import { analysisRun, result } from "@/test/analytics";

import {
  formatResult,
  indexResults,
  METRICS,
  metricLabel,
  metricWindow,
  readCorrelationMatrix,
  readRiskAssets,
  readSectorWeights,
  readValueSeries,
  resultSign,
  runParameters,
  TILE_GROUPS,
  unavailableReason,
  unavailableResults,
} from "./metrics";

const CONTEXT = { currency: "USD", locale: "en-US" };

function descriptor(key: string) {
  const found = METRICS[key];
  if (!found) throw new Error(`No descriptor for ${key}`);
  return found;
}

describe("the catalogue", () => {
  it("defines every metric the tile groups ask for", () => {
    for (const group of TILE_GROUPS) {
      for (const metric of group.metrics) {
        expect(METRICS[metric], `${metric} has no descriptor`).toBeDefined();
      }
    }
  });

  it("gives every metric a definition and a basis", () => {
    for (const [key, entry] of Object.entries(METRICS)) {
      expect(entry.definition.length, `${key} has no definition`).toBeGreaterThan(20);
      expect(entry.label.length, `${key} has no label`).toBeGreaterThan(0);
    }
  });

  it("never renders a daily and an annualized label identically", () => {
    // The rule this enforces: neither figure is ever bare, so the two cannot be
    // confused for one another. DESIGN.md section 6.3.
    expect(metricLabel(descriptor("volatility_daily"))).toBe("Volatility (daily)");
    expect(metricLabel(descriptor("volatility_annualized"))).toBe("Volatility (annualized)");
  });

  it("names alpha as the annualized figure the backend actually computes", () => {
    // There is no bare "alpha" and no Sortino ratio. DESIGN.md section 11.
    expect(METRICS["benchmark_alpha_annualized"]?.label).toMatch(/alpha versus benchmark/i);
    expect(METRICS["sortino_ratio"]).toBeUndefined();
    expect(METRICS["alpha"]).toBeUndefined();
  });

  it("carries the estimate caveat on every tail measure", () => {
    for (const key of [
      "value_at_risk_historical",
      "value_at_risk_parametric",
      "expected_shortfall",
    ]) {
      const caption = descriptor(key).caption?.(
        result(key, "100", "currency", { confidence: 0.95 }),
      );
      expect(caption, key).toMatch(/not a maximum possible loss/i);
      expect(caption, key).toMatch(/95%/);
    }
  });
});

describe("formatResult", () => {
  it("formats money in the portfolio's own currency", () => {
    expect(
      formatResult(
        result("portfolio_value", "12480.55", "currency"),
        descriptor("portfolio_value"),
        CONTEXT,
      ),
    ).toBe("$12,480.55");
  });

  it("keeps every digit of a large amount", () => {
    // The value stays a decimal string the whole way through; parsed into a
    // JavaScript number this would lose its last digits.
    expect(
      formatResult(
        result("portfolio_value", "9007199254740993.21", "currency"),
        descriptor("portfolio_value"),
        CONTEXT,
      ),
    ).toContain("9,007,199,254,740,993.21");
  });

  it("renders a ratio metric as a percentage", () => {
    expect(
      formatResult(
        result("volatility_annualized", "0.1492", "ratio"),
        descriptor("volatility_annualized"),
        CONTEXT,
      ),
    ).toBe("14.92%");
  });

  it("renders a plain ratio as a number, not a percentage", () => {
    // A Sharpe ratio of 0.49 is not "49%", and a beta of 0.87 is not "87%".
    expect(
      formatResult(
        result("sharpe_ratio", "0.4926", "ratio"),
        descriptor("sharpe_ratio"),
        CONTEXT,
      ),
    ).toBe("0.49");
    expect(
      formatResult(
        result("benchmark_beta", "0.8742", "ratio"),
        descriptor("benchmark_beta"),
        CONTEXT,
      ),
    ).toBe("0.87");
  });

  it("shows the sign on a profit or loss", () => {
    expect(
      formatResult(
        result("unrealized_profit_loss", "2480.55", "currency"),
        descriptor("unrealized_profit_loss"),
        CONTEXT,
      ),
    ).toBe("+$2,480.55");
  });

  it("counts whole things", () => {
    expect(
      formatResult(
        result("holdings_count", "3", "count"),
        descriptor("holdings_count"),
        CONTEXT,
      ),
    ).toBe("3");
  });

  it("returns null rather than a zero when there is no value", () => {
    // The single most important rule in the product: an unknown is not a zero.
    expect(formatResult(undefined, descriptor("sharpe_ratio"), CONTEXT)).toBeNull();
    expect(
      formatResult(
        result("sharpe_ratio", null, "ratio", {}, "Undefined."),
        descriptor("sharpe_ratio"),
        CONTEXT,
      ),
    ).toBeNull();
  });

  it("returns null for a value that is not a number", () => {
    const broken = {
      metric: "sharpe_ratio",
      value: "not a number",
      unit: "ratio",
    } as RiskResult;
    expect(formatResult(broken, descriptor("sharpe_ratio"), CONTEXT)).toBeNull();
  });
});

describe("unavailability", () => {
  it("distinguishes a metric the run never produced from one it could not compute", () => {
    expect(unavailableReason(undefined)).toBe("not produced by this run");
    expect(unavailableReason(result("x", null, "ratio", {}, "Only 12 observations."))).toBe(
      "Only 12 observations.",
    );
  });

  it("collects every unavailable metric from a run", () => {
    const run = analysisRun();
    const missing = unavailableResults(run);

    expect(missing.map((item) => item.metric)).toContain("information_ratio");
    expect(missing.every((item) => item.value === null)).toBe(true);
  });
});

describe("metadata readers", () => {
  it("reads the window a metric was computed over", () => {
    expect(metricWindow(result("total_return", "0.1", "ratio"))).toEqual({
      start: "2022-01-03",
      end: "2023-12-29",
      observations: 30,
    });
  });

  it("keeps a gap in a series as a gap", () => {
    const series = readValueSeries(
      result("portfolio_value_series", "1", "currency", {
        points: [
          { date: "2022-01-03", value: 100, drawdown: 0 },
          { date: "2022-01-04", value: null, drawdown: null },
        ],
      }),
    );

    expect(series).toHaveLength(2);
    expect(series[1]?.value).toBeNull();
  });

  it("drops a point with no date rather than plotting it somewhere", () => {
    const series = readValueSeries(
      result("portfolio_value_series", "1", "currency", {
        points: [{ value: 100 }, { date: "2022-01-04", value: 101 }],
      }),
    );

    expect(series).toHaveLength(1);
  });

  it("refuses a correlation matrix that does not match its symbols", () => {
    expect(
      readCorrelationMatrix(
        result("average_pairwise_correlation", "0.4", "ratio", {
          symbols: ["AAPL", "SPY"],
          matrix: [[1, 0.5]],
        }),
      ),
    ).toBeNull();
  });

  it("reads a correlation matrix and keeps unmeasured pairs null", () => {
    const matrix = readCorrelationMatrix(
      result("average_pairwise_correlation", "0.4", "ratio", {
        symbols: ["AAPL", "SPY"],
        matrix: [
          [1, null],
          [null, 1],
        ],
      }),
    );

    expect(matrix?.symbols).toEqual(["AAPL", "SPY"]);
    expect(matrix?.cells[0]?.[1]).toBeNull();
  });

  it("orders sector weights by size and ignores anything that is not a number", () => {
    const sectors = readSectorWeights(
      result("largest_sector_weight", "0.5", "ratio", {
        sector_weights: { Bonds: 0.1747, Technology: 0.5241, Broken: "0.3" },
      }),
    );

    expect(sectors.map((entry) => entry.sector)).toEqual(["Technology", "Bonds"]);
  });

  it("requires a symbol on every risk contribution", () => {
    const assets = readRiskAssets(
      result("risk_contribution", "0.14", "ratio", {
        assets: [{ weight: 0.5 }, { symbol: "AAPL", weight: 0.5, share_of_risk: 0.67 }],
      }),
    );

    expect(assets).toHaveLength(1);
    expect(assets[0]?.symbol).toBe("AAPL");
  });

  it("survives metadata that is missing entirely", () => {
    const bare = { metric: "sharpe_ratio", value: "1", unit: "ratio" } as RiskResult;

    expect(readValueSeries(bare)).toEqual([]);
    expect(readCorrelationMatrix(bare)).toBeNull();
    expect(readSectorWeights(bare)).toEqual([]);
    expect(metricWindow(bare)).toEqual({ start: null, end: null, observations: null });
  });
});

describe("run helpers", () => {
  it("indexes a run's results by metric", () => {
    const index = indexResults(analysisRun());

    expect(index["sharpe_ratio"]?.value).toBe("0.4926");
    expect(index["nonexistent_metric"]).toBeUndefined();
  });

  it("reads back the parameters a run was executed with", () => {
    expect(runParameters(analysisRun())).toEqual({
      start: "2022-01-03",
      end: "2023-12-29",
      confidence: 0.95,
      varMethod: "historical",
      frequency: "daily",
      annualRiskFreeRate: 0.045,
      benchmarkSymbol: "SPY",
      minimumObservations: 30,
    });
  });

  it("reports the sign of a value without parsing it as money", () => {
    expect(resultSign(result("x", "-0.12", "ratio"))).toBe("negative");
    expect(resultSign(result("x", "0", "ratio"))).toBe("flat");
    expect(resultSign(undefined)).toBe("flat");
  });
});
