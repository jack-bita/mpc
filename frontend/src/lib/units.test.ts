// units.test.ts — splitIntoUnits refuses what the server's split_into_units refuses (02 §15, item 1). The
// answers themselves are in the shared answer book (vectors.units.test.ts).
import { describe, expect, it } from "vitest";

import { Decimal } from "./decimal";
import { splitIntoUnits } from "./units";

const kg = (text: string) => new Decimal(text);
const sizes = (...texts: string[]) => texts.map((text) => new Decimal(text));

describe("splitIntoUnits", () => {
  it.each(["0", "-50"])("refuses a factor of %s", (factor) => {
    expect(() => splitIntoUnits(kg("100"), sizes(factor))).toThrow(
      "above zero",
    );
  });

  it("refuses the base unit's own selling unit, factor 1", () => {
    // E1's Kilo: the rest is already counted in kg.
    expect(() => splitIntoUnits(kg("35.5"), sizes("50", "1"))).toThrow(
      "factor 1",
    );
  });

  it.each([
    ["smallest first", ["25", "50"]],
    ["the same size twice", ["50", "50"]],
  ])("refuses factors given %s", (_, factors) => {
    expect(() => splitIntoUnits(kg("100"), sizes(...factors))).toThrow(
      "biggest first",
    );
  });

  it("refuses a quantity with more places than a quantity column holds", () => {
    expect(() => splitIntoUnits(kg("35.5001"), sizes("50"))).toThrow(
      "more places",
    );
  });
});
