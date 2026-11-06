// vectors.units.test.ts — splitIntoUnits gives every answer in shared/test-vectors/units.json, the same
// file backend/tests/test_vectors.py runs against Python's split_into_units (02 §15, item 1, 03 §8).
//
// The file pins the traps where a JavaScript version goes wrong: -120 kg is -2 bags and -20 kg
// (Math.floor gives -3 bags and +30 kg), and 0.3 L in bottles of 0.1, which floats make 2.9999…
// bottles.
import { describe, expect, it } from "vitest";

import { casesIn } from "@/test/vectors";

import { Decimal, quantityText } from "./decimal";
import { splitIntoUnits } from "./units";

interface UnitsCase {
  name: string;
  unit: string;
  quantity: string;
  factors: string[];
  expect: { counts: string[]; rest: string };
}

describe("the shared units answers", () => {
  it.each(casesIn<UnitsCase>("units.json"))("$name", (vector) => {
    const { counts, rest } = splitIntoUnits(
      new Decimal(vector.quantity),
      vector.factors.map((factor) => new Decimal(factor)),
    );

    // As text, as Python does: whole counts, and the rest with three places.
    expect(counts.map((count) => count.toFixed(0))).toEqual(
      vector.expect.counts,
    );
    expect(quantityText(rest)).toBe(vector.expect.rest);
  });
});
