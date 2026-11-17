// decimal.ts — the one way the app holds money and quantities: exact decimals, never JavaScript numbers
// (ADR-0024). It holds what rounding.ts and units.ts share with their twins in
// backend/apps/core/numbers.py: our copy of big.js, the column check (Python's _fit), and the text a
// value is stored and sent as.
//
// A JavaScript number is a float: 0.1 + 0.2 gives 0.30000000000000004, and 0.35 kg × 1,310 gives
// 458.4999…, which rounds to 458, not 459. A counter device works out a sale offline and the server
// works it out again, and the two must agree to the shilling, or the sale is flagged as a total
// mismatch. So every amount and quantity here is a big.js decimal, read from text, as the server reads
// it into a Python Decimal from text. Both sides pass the same answer book, shared/test-vectors/.
//
// Money has two places and quantities three, as the database stores them: numeric(14,2) and
// numeric(14,3) (03 §9).
import Big from "big.js";

/**
 * Our own big.js, with settings no other code can change: big.js lets each copy keep its own. Use it
 * for every amount and quantity: new Decimal("1335.5"), never new Decimal(1335.5).
 */
export const Decimal = Big();

// Refuses a JavaScript number anywhere a decimal is made, and refuses to turn a decimal back into one.
// So new Decimal(0.1), price.times(2), Number(price) and price < total all fail at once, in tests,
// instead of losing a shilling quietly in the shop. Numbers travel as text: new Decimal("0.1").
Decimal.strict = true;

// Places kept when dividing. A division is the only sum that can go on forever (1 ÷ 3), so big.js cuts
// it at DP places. 40 is far more than any rounding here needs: with two places and 14 digits, a share
// that isn't exactly a half sits at least 0.000000000000005 away from one (15 places), and an amount
// with a few more places (a price × kg) moves that only a few places further. Python's _EXACT keeps 40
// digits in all, not 40 places after the point, so the two sides don't cut in the same place; both cut
// far past the place that decides the rounding, so they give the same answer.
Decimal.DP = 40;
// How the cut at DP places rounds: half away from zero, the one rounding rule (03 §8).
Decimal.RM = Decimal.roundHalfUp;

export const MONEY_PLACES = 2;
export const QUANTITY_PLACES = 3;

// Every money and quantity column holds 14 digits in all (numeric(14,2), numeric(14,3)) (03 §9).
const COLUMN_DIGITS = 14;

/**
 * Checks that a value fits its column, `places` places and 14 digits in all, and gives it back. It
 * only checks: a value it would have to round is refused, so roundMoney stays the one place that rounds
 * (ADR-0024). A refused value is a bug in the sum that made it, not something to show a person.
 */
export function fit(value: Big, places: number): Big {
  // new Decimal(value): a value made by another copy of big.js gets our settings too.
  const exact = new Decimal(value);
  if (!exact.round(places, Decimal.roundDown).eq(exact))
    throw new RangeError(`${exact.toString()} has more places than ${places}.`);
  // A result the column can't hold is refused here, not by the database when the server saves it.
  const whole = exact.abs().round(0, Decimal.roundDown).toFixed(0);
  if (whole.length > COLUMN_DIGITS - places)
    throw new RangeError(
      `${exact.toString()} has more digits than a column holds.`,
    );
  // -0 equals 0, but big.js can write it as "-0.00": never on a receipt.
  return exact.eq("0") ? new Decimal("0") : exact;
}

/** Money as it is stored, sent and checked against the answer book: "459.00". */
export function moneyText(value: Big): string {
  return fit(value, MONEY_PLACES).toFixed(MONEY_PLACES);
}

/** A quantity as it is stored, sent and checked against the answer book: "35.500". */
export function quantityText(value: Big): string {
  return fit(value, QUANTITY_PLACES).toFixed(QUANTITY_PLACES);
}
