// rounding.ts — the one rounding rule for money, on the device (03 §8, ADR-0024). The TypeScript twin of
// round_money in backend/apps/core/numbers.py: both pass shared/test-vectors/rounding.json, so a sale
// worked out offline and again on the server comes to the same shilling.
//
// Nothing else rounds money. Screens and sums that need a rounded amount call roundMoney.
import type Big from "big.js";

import { Decimal, fit, MONEY_PLACES } from "./decimal";

/**
 * Rounds an amount half-up to a multiple of the shop's step (the setting money.rounding_step, default
 * 1 shilling): 458.5 → 459, 13,762 with a step of 50 → 13,750. Count the steps, round that count to a
 * whole number, turn it back into money, as the server does.
 *
 * Half-up sends a half away from zero: -2.5 → -3, so a refund rounds like the sale it reverses.
 * JavaScript's Math.round(-2.5) gives -2, and Math.round works on floats anyway: never use it on money.
 */
export function roundMoney(amount: Big, step: Big): Big {
  if (step.lte("0"))
    throw new RangeError(
      `A rounding step must be above zero, not ${step.toString()}.`,
    );
  // new Decimal(amount): the division uses our 40 places, even for a value made by another copy of
  // big.js, which would cut at its own (decimal.ts).
  const steps = new Decimal(amount).div(step).round(0, Decimal.roundHalfUp);
  // fit refuses a step that leaves more than two places (0.001), as the server does.
  return fit(steps.times(step), MONEY_PLACES);
}
