// decimal.test.ts — money and quantities stay exact: no JavaScript number gets in or out, and a value
// that doesn't fit its column is refused, never rounded on the quiet (ADR-0024).
import { describe, expect, it } from "vitest";

import { Decimal, fit, moneyText, quantityText } from "./decimal";

describe("the app's decimals", () => {
  it("add up exactly, where floats don't", () => {
    // 0.1 + 0.2 is 0.30000000000000004 in JavaScript numbers.
    expect(new Decimal("0.1").plus("0.2").toString()).toBe("0.3");
  });

  it("refuse a JavaScript number", () => {
    // A float has already lost the exact value: it is refused, not converted, as the server does.
    expect(() => new Decimal(0.1)).toThrow();
    expect(() => new Decimal("2").times(0.5)).toThrow();
  });

  it("refuse to become a JavaScript number", () => {
    const price = new Decimal("12000");
    // < and + call valueOf. On two decimals, < would compare them as text ("9" > "10") if it ran.
    expect(() => Number(price)).toThrow();
    expect(() => price.valueOf()).toThrow();
  });

  it("keep their own settings, whatever another copy of big.js sets", () => {
    expect(Decimal.DP).toBe(40);
    expect(Decimal.RM).toBe(Decimal.roundHalfUp);
    expect(Decimal.strict).toBe(true);
  });
});

describe("moneyText and quantityText", () => {
  it("write the column's places", () => {
    expect(moneyText(new Decimal("459"))).toBe("459.00");
    expect(quantityText(new Decimal("35.5"))).toBe("35.500");
  });

  it("never write a minus on zero", () => {
    expect(moneyText(new Decimal("-0"))).toBe("0.00");
    expect(quantityText(new Decimal("-0.000"))).toBe("0.000");
  });

  it("refuse a value they would have to round", () => {
    // Only roundMoney rounds money (ADR-0024).
    expect(() => moneyText(new Decimal("458.499"))).toThrow("more places");
    expect(() => quantityText(new Decimal("35.5001"))).toThrow("more places");
  });

  it("refuse a value too big for its column", () => {
    // numeric(14,2) holds 12 digits before the point, numeric(14,3) holds 11.
    expect(moneyText(new Decimal("999999999999.99"))).toBe("999999999999.99");
    expect(() => moneyText(new Decimal("1000000000000"))).toThrow(
      "more digits",
    );
    expect(quantityText(new Decimal("-99999999999.999"))).toBe(
      "-99999999999.999",
    );
    expect(() => fit(new Decimal("100000000000"), 3)).toThrow("more digits");
  });
});
