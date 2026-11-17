// units.ts — stock as people count it: whole bags (or boxes, bottles) and the rest in kg (02 §15, item 1).
// The TypeScript twin of split_into_units in backend/apps/core/numbers.py: both pass
// shared/test-vectors/units.json, so a device and the server show the same stock.
//
// format.ts writes the result as words: "mifuko 26 + kilo 35.5".
import type Big from "big.js";

import { Decimal, fit, QUANTITY_PLACES } from "./decimal";

export interface Split {
  /** How many whole units of each size, biggest first, in the order of the factors. */
  counts: Big[];
  /** What is left in the base unit (kg, L, pcs or m). */
  rest: Big;
}

/**
 * Splits a quantity in the base unit into whole selling units, biggest first, and the rest:
 * 1,335.5 kg with bags of 50 → 26 bags and 35.5 kg. A factor is a selling unit's size in the base unit
 * (CAT-2); its name doesn't matter here.
 *
 * Below zero (ADR-0010), it counts toward zero: -120 kg is -2 bags and -20 kg, not -3 bags and +30 kg
 * (what Math.floor would give), so stock below zero reads like the same stock above zero, with a minus.
 */
export function splitIntoUnits(quantity: Big, factors: readonly Big[]): Split {
  if (factors.some((factor) => factor.lte("0")))
    throw new RangeError("A selling unit's factor must be above zero.");
  // The base unit's own selling unit (E1's Kilo, factor 1) is the rest itself: passed in, 35.5 kg
  // would show as 35 kilos + 0.5 kg. Callers leave it out.
  if (factors.some((factor) => factor.eq("1")))
    throw new RangeError(
      "Leave out the base unit itself (factor 1): it is the rest.",
    );
  // Smallest first would count everything in the small unit; the same size twice always shows 0.
  if (
    factors.some((factor, at) => at > 0 && factor.gte(factors[at - 1] ?? "0"))
  )
    throw new RangeError("Factors go biggest first, each size once.");

  const counts: Big[] = [];
  // new Decimal: the sums use our settings, even for a value made by another copy of big.js.
  let rest = new Decimal(quantity);
  for (const factor of factors) {
    // mod is what is left after taking out whole factors, with the same sign as rest: -120 mod 50 is
    // -20. big.js works it out with no rounding at all, so rest - left is an exact number of whole
    // factors, and the division below comes out whole. A plain division, then rounding down, would
    // be cut at 40 places first (decimal.ts) and lean on that being enough; this way nothing is cut.
    const left = rest.mod(factor);
    counts.push(rest.minus(left).div(factor));
    rest = left;
  }
  return { counts, rest: fit(rest, QUANTITY_PLACES) };
}
