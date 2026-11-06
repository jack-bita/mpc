// vectors.rounding.test.ts — roundMoney gives every answer in shared/test-vectors/rounding.json, the
// same file backend/tests/test_vectors.py runs against Python's round_money (ADR-0024, 03 §8).
//
// The file pins the traps where a JavaScript version goes wrong: -2.5 → -3 (Math.round gives -2),
// never "-0.00", and 1.65 ÷ 1.10, which floats make 1.4999….
import { describe, expect, it } from "vitest";

import { casesIn } from "@/test/vectors";

import { Decimal, moneyText } from "./decimal";
import { roundMoney } from "./rounding";

interface RoundingCase {
  name: string;
  amount: string;
  step: string;
  expect: string;
}

describe("the shared rounding answers", () => {
  // $name: each case's name becomes its test's name, so a failure names the case.
  it.each(casesIn<RoundingCase>("rounding.json"))("$name", (vector) => {
    const result = roundMoney(
      new Decimal(vector.amount),
      new Decimal(vector.step),
    );

    // Compared as text, as Python does: the text is what is stored and shown, two places, no minus
    // on a zero.
    expect(moneyText(result)).toBe(vector.expect);
  });
});
