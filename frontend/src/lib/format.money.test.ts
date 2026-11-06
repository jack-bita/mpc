// format.money.test.ts — money and quantities are written the Tanzanian way, exactly, and never rounded
// on the quiet (03 §7.4, ADR-0024).
//
// The strings are what Node's own copy of the browser's number writer gives. Chrome uses the same data
// (CLDR), so a device shows the same; the eye checks it on /design.
import { describe, expect, it } from "vitest";

import { Decimal } from "./decimal";
import { formatMoney, formatQuantity } from "./format";

const tsh = (text: string) => formatMoney(new Decimal(text));

describe("formatMoney", () => {
  it("writes shillings with a comma between thousands and no cents", () => {
    //  : a space that never breaks, so "TSh" and its amount stay on one line.
    expect(tsh("41000")).toBe("TSh 41,000");
    expect(tsh("1234560.00")).toBe("TSh 1,234,560");
  });

  it("writes zero, and never a minus on it", () => {
    expect(tsh("0")).toBe("TSh 0");
    expect(tsh("-0.00")).toBe("TSh 0");
  });

  it("writes money below zero, as a refund is", () => {
    expect(tsh("-3000")).toBe("-TSh 3,000");
  });

  it("writes the biggest amount a column holds, to the shilling", () => {
    // Handed over as text: as a JavaScript number this one is still exact, but nothing here leans on it.
    expect(tsh("999999999999")).toBe("TSh 999,999,999,999");
  });

  it("refuses cents instead of rounding them away", () => {
    // Only roundMoney rounds money (ADR-0024).
    expect(() => tsh("458.50")).toThrow("roundMoney");
  });
});

describe("formatQuantity", () => {
  it("leaves off the zeros at the end", () => {
    expect(formatQuantity(new Decimal("35.500"))).toBe("35.5");
    expect(formatQuantity(new Decimal("0.050"))).toBe("0.05");
    expect(formatQuantity(new Decimal("20.000"))).toBe("20");
  });

  it("writes a comma between thousands", () => {
    expect(formatQuantity(new Decimal("1335.5"))).toBe("1,335.5");
  });

  it("refuses a quantity with more places than a column holds", () => {
    expect(() => formatQuantity(new Decimal("35.5001"))).toThrow("more places");
  });
});
