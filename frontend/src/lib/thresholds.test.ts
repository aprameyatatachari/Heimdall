import { describe, expect, it } from "vitest";

import { toThresholds, validateThresholds } from "./thresholds";

const PERCENT = "percent_of_portfolio_value";

function check(
  values: Partial<Record<"elevated" | "high" | "critical", string>>,
  unit = PERCENT,
) {
  return validateThresholds(
    {
      elevated: values.elevated ?? "",
      high: values.high ?? "",
      critical: values.critical ?? "",
    },
    unit,
  );
}

describe("threshold validation", () => {
  it("accepts thresholds that increase with severity", () => {
    expect(check({ elevated: "0.2", high: "0.3", critical: "0.4" })).toEqual({ ok: true });
  });

  it("accepts a partial set", () => {
    // The backend requires at least one, not all three: someone who only cares
    // about the critical case should not have to invent the other two.
    expect(check({ critical: "0.5" })).toEqual({ ok: true });
  });

  it("rejects a set where a more serious threshold is lower", () => {
    const result = check({ elevated: "0.3", high: "0.2" });
    expect(result.ok).toBe(false);
    expect(result.ok === false && result.message).toMatch(/high threshold must be greater/i);
  });

  it("rejects equal thresholds, which would make one unreachable", () => {
    expect(check({ elevated: "0.3", high: "0.3" }).ok).toBe(false);
  });

  it("rejects an empty set rather than saving a rule that can never fire", () => {
    const result = check({});
    expect(result.ok).toBe(false);
    expect(result.ok === false && result.message).toMatch(/disable the rule instead/i);
  });

  it("catches a share entered as a percentage", () => {
    // 30 means thirty times the portfolio, so the rule would never fire again.
    const result = check({ high: "30" });
    expect(result.ok).toBe(false);
    expect(result.ok === false && result.message).toMatch(/use 0.3 for 30%/i);
  });

  it("allows a multiple above 1 where the unit is a ratio", () => {
    expect(check({ elevated: "1.25", high: "1.5" }, "ratio_to_baseline")).toEqual({ ok: true });
  });

  it("keeps a correlation inside its range", () => {
    expect(check({ high: "1.4" }, "correlation_coefficient").ok).toBe(false);
  });

  it("rejects a threshold that is not a number", () => {
    expect(check({ high: "soon" }).ok).toBe(false);
  });

  it("rejects zero and negative thresholds", () => {
    expect(check({ high: "0" }).ok).toBe(false);
    expect(check({ high: "-0.2" }).ok).toBe(false);
  });
});

describe("reading a rule's stored configuration", () => {
  it("fills the form from what is stored", () => {
    expect(toThresholds({ elevated: 0.2, critical: 0.4 })).toEqual({
      elevated: "0.2",
      high: "",
      critical: "0.4",
    });
  });

  it("copes with a rule that has no configuration at all", () => {
    expect(toThresholds(undefined)).toEqual({ elevated: "", high: "", critical: "" });
  });
});
