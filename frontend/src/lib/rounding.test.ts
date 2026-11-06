// rounding.test.ts — roundMoney refuses what the server's round_money refuses (ADR-0024). The answers
// themselves are in the shared answer book (vectors.rounding.test.ts).
import Big from "big.js";
import { describe, expect, it } from "vitest";

import { Decimal, moneyText } from "./decimal";
import { roundMoney } from "./rounding";

const one = new Decimal("1");

describe("roundMoney", () => {
  it.each(["0", "-50"])("refuses a step of %s", (step) => {
    expect(() => roundMoney(new Decimal("100"), new Decimal(step))).toThrow(
      "above zero",
    );
  });

  it("refuses a step that leaves more than two places", () => {
    // 0.001 would give 458.499, which no money column holds.
    expect(() =>
      roundMoney(new Decimal("458.4987"), new Decimal("0.001")),
    ).toThrow("more places");
  });

  it("works the same on a value from another copy of big.js", () => {
    // big.js's own copy cuts a division at 20 places and rounds it its own way; roundMoney uses ours.
    expect(moneyText(roundMoney(new Big("458.5"), one))).toBe("459.00");
  });
});
