import { describe, expect, it } from "vitest";

// A fixed locale keeps these expectations the same on every machine; the
// application itself follows the reader's locale.
const EN = { locale: "en-US" } as const;

import {
  daysSince,
  formatDate,
  formatMoney,
  formatPercent,
  formatQuantity,
  signOf,
  UNAVAILABLE,
} from "./format";

describe("formatMoney", () => {
  it("formats a decimal string in the given currency", () => {
    expect(formatMoney("1248320.5", "USD", EN)).toBe("$1,248,320.50");
  });

  it("keeps every digit of a large amount", () => {
    // The point of passing the string through: Number() loses the last digits
    // of this value and would render ...680.00.
    expect(formatMoney("123456789012345678.99", "USD", EN)).toContain("678.99");
  });

  it("honours the portfolio's own currency", () => {
    expect(formatMoney("100", "EUR", EN)).toContain("€");
    expect(formatMoney("100", "GBP", EN)).toContain("£");
  });

  it("shows a missing amount as unavailable, never as zero", () => {
    expect(formatMoney(null, "USD", EN)).toBe(UNAVAILABLE);
    expect(formatMoney(undefined, "USD", EN)).toBe(UNAVAILABLE);
    expect(formatMoney("", "USD", EN)).toBe(UNAVAILABLE);
    expect(formatMoney(null, "USD", EN)).not.toContain("0");
  });

  it("can sign a positive amount explicitly", () => {
    expect(formatMoney("42", "USD", { ...EN, signed: true })).toContain("+");
    expect(formatMoney("-42", "USD", { ...EN, signed: true })).toContain("-");
  });

  it("does not sign zero", () => {
    expect(formatMoney("0", "USD", { ...EN, signed: true })).not.toContain("+");
  });

  it("degrades rather than throwing on an unknown currency", () => {
    expect(formatMoney("10", "NOTACURRENCY", EN)).toBe(UNAVAILABLE);
  });
});

describe("formatPercent", () => {
  it("scales a fraction to a percentage", () => {
    expect(formatPercent(0.084, EN)).toBe("8.40%");
  });

  it("keeps the sign on a loss", () => {
    expect(formatPercent(-0.3174, EN)).toBe("-31.74%");
  });

  it("shows a missing ratio as unavailable", () => {
    expect(formatPercent(null, EN)).toBe(UNAVAILABLE);
    expect(formatPercent(Number.NaN, EN)).toBe(UNAVAILABLE);
  });

  it("does not treat zero as missing", () => {
    expect(formatPercent(0, EN)).toBe("0.00%");
  });
});

describe("formatQuantity", () => {
  it("keeps fractional shares", () => {
    expect(formatQuantity("12.5", EN)).toBe("12.5");
  });

  it("drops meaningless trailing zeros", () => {
    expect(formatQuantity("100.00", EN)).toBe("100");
  });

  it("shows a missing quantity as unavailable", () => {
    expect(formatQuantity(null, EN)).toBe(UNAVAILABLE);
  });
});

describe("formatDate", () => {
  it("renders an ISO date", () => {
    expect(formatDate("2023-12-29", EN)).toMatch(/Dec/);
  });

  it("does not shift the day across time zones", () => {
    // A naive `new Date("2023-12-29")` in a negative-offset zone renders the
    // 28th. Market data dates must not drift.
    expect(formatDate("2023-12-29", EN)).toMatch(/29/);
  });

  it("shows a missing date as unavailable", () => {
    expect(formatDate(null, EN)).toBe(UNAVAILABLE);
    expect(formatDate("not a date", EN)).toBe(UNAVAILABLE);
  });
});

describe("signOf", () => {
  it("reads the sign without converting to a number", () => {
    expect(signOf("1234.56")).toBe("positive");
    expect(signOf("-1234.56")).toBe("negative");
  });

  it("treats every spelling of zero as flat", () => {
    expect(signOf("0")).toBe("flat");
    expect(signOf("0.00")).toBe("flat");
    expect(signOf("-0.00")).toBe("flat");
  });

  it("treats a missing value as flat rather than guessing", () => {
    expect(signOf(null)).toBe("flat");
  });
});

describe("daysSince", () => {
  const now = new Date("2026-09-21T10:00:00Z");

  it("counts whole days", () => {
    expect(daysSince("2026-09-18", now)).toBe(3);
  });

  it("is zero for today", () => {
    expect(daysSince("2026-09-21", now)).toBe(0);
  });

  it("returns null when there is no date, rather than zero", () => {
    expect(daysSince(null, now)).toBeNull();
  });
});
