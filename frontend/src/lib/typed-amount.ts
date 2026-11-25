// typed-amount.ts — an amount of money as a person types it into a box (WAGE-1): a worker's daily rate, and the day's meal
// money (WAGE-7). One reading, so every box takes the same shapes.
import { Decimal } from "./decimal";

/** Whole shillings, as Baba types them, "10,000", "10 000" or "10000": the digits, as the server takes them, or null
 * for anything else. The same shapes as a money rule's box (setting-form.tsx): a point and cents are refused, as the
 * shop's money has none (Jack, 16 Nov 2026). */
const WHOLE = /^(\d+|[1-9]\d{0,2}([, ]\d{3})+)$/;
export function typedAmount(typed: string): string | null {
  const trimmed = typed.trim();
  if (!WHOLE.test(trimmed)) return null;
  const digits = trimmed.replace(/[, ]/g, "");
  // Above nothing, as the server asks: "0" and "000" are no amount. "0" as text: the shared Decimal is strict, and refuses
  // a plain number, so no float ever reaches money (rule 3).
  return new Decimal(digits).gt("0") ? digits : null;
}
