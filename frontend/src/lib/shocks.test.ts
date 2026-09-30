import { describe, expect, it } from "vitest";

import { duplicateTargets, resolveShock, shockSource, type Shock } from "./shocks";

const marketWide: Shock = { target_type: "portfolio", value: -0.1 };
const technology: Shock = { target_type: "sector", target: "Technology", value: -0.2 };
const apple: Shock = { target_type: "symbol", target: "AAPL", value: -0.35 };

describe("shock precedence", () => {
  it("lets a symbol shock beat its sector and the market", () => {
    // The whole point of the preview: someone who sets all three has to be able
    // to see that AAPL takes -35%, not -20% and not the sum of anything.
    expect(resolveShock("AAPL", "Technology", [marketWide, technology, apple])).toBe(apple);
  });

  it("lets a sector shock beat a market-wide one", () => {
    expect(resolveShock("MSFT", "Technology", [marketWide, technology])).toBe(technology);
  });

  it("falls back to the market-wide shock", () => {
    expect(resolveShock("XOM", "Energy", [marketWide, technology, apple])).toBe(marketWide);
  });

  it("leaves a holding untouched when nothing targets it", () => {
    expect(resolveShock("XOM", "Energy", [technology, apple])).toBeNull();
  });

  it("matches a symbol regardless of case", () => {
    expect(resolveShock("aapl", "Technology", [apple])).toBe(apple);
  });

  it("matches a sector regardless of case", () => {
    expect(resolveShock("MSFT", "TECHNOLOGY", [technology])).toBe(technology);
  });

  it("ignores a targeted shock with no target", () => {
    const broken: Shock = { target_type: "sector", target: null, value: -0.5 };
    expect(resolveShock("MSFT", "Technology", [broken])).toBeNull();
  });

  it("prefers the later of two equally specific shocks", () => {
    const first: Shock = { target_type: "sector", target: "Technology", value: -0.2 };
    const second: Shock = { target_type: "sector", target: "technology", value: -0.4 };
    expect(resolveShock("MSFT", "Technology", [first, second])).toBe(second);
  });
});

describe("naming a shock", () => {
  it("names the target a reader would recognise", () => {
    expect(shockSource(apple)).toBe("AAPL");
    expect(shockSource(technology)).toBe("Technology");
    expect(shockSource(marketWide)).toBe("whole portfolio");
  });
});

describe("duplicate targets", () => {
  it("finds a target shocked twice, whatever its case", () => {
    // The API refuses the scenario outright, so the builder has to catch it
    // first or the user loses the run to a validation error.
    expect(
      duplicateTargets([
        technology,
        { target_type: "sector", target: "technology", value: -0.4 },
      ]),
    ).toEqual(["technology"]);
  });

  it("is happy with distinct targets", () => {
    expect(duplicateTargets([marketWide, technology, apple])).toEqual([]);
  });
});
