// typed-amount.test.ts — an amount as a person types it, "10,000", "10 000" or "10000", read as whole shillings above 0.
import { describe, expect, it } from "vitest";

import { typedAmount } from "./typed-amount";

describe("an amount as it is typed", () => {
  it.each([
    ["5000", "5000"],
    ["5,000", "5000"],
    ["5 000", "5000"],
    [" 5000 ", "5000"],
    ["1,000,000", "1000000"],
    ["007", "007"],
  ])("takes %s", (typed, digits) => {
    expect(typedAmount(typed)).toBe(digits);
  });

  it.each([
    [""],
    ["0"],
    ["000"],
    ["-500"],
    ["5000.50"],
    ["5.000"],
    ["5,00"],
    ["50,00,000"],
    ["elfu tano"],
    ["5000/="],
  ])("refuses %s", (typed) => {
    expect(typedAmount(typed)).toBeNull();
  });
});
