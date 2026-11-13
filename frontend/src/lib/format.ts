// format.ts — money, stock and times of day as people read them: "TSh 41,000", "mifuko 26 + kilo 35.5"
// and "07:55" (03 §7.4).
//
// Every screen and slip writes numbers through here, so 41000 never shows as "41000.00" on one screen
// and "TSh 41,000" on another. Writing never rounds: a value that would need rounding is refused, so
// roundMoney stays the one place that rounds money (ADR-0024).
//
// Numbers are written the Tanzanian way (sw-TZ), in both languages: a comma between thousands and a
// point before decimals. Intl.NumberFormat is the browser's own number writer. It is handed the
// number as text, which it reads exactly, never as a JavaScript number (a float).
import type Big from "big.js";

import { Decimal, fit, MONEY_PLACES, QUANTITY_PLACES } from "./decimal";
import { splitIntoUnits } from "./units";

const LOCALE = "sw-TZ";

// Money: Tanzanian shillings, with no cents, as prices and receipts show them.
const MONEY = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "TZS",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

// Quantities: up to three places, with the zeros at the end left off (35.500 → 35.5).
const QUANTITY = new Intl.NumberFormat(LOCALE, {
  maximumFractionDigits: QUANTITY_PLACES,
});

// The minus sign sw-TZ writes before a number, so stock below zero and money below zero carry the same.
const MINUS =
  QUANTITY.formatToParts(-1).find((part) => part.type === "minusSign")?.value ??
  "-";

/** A decimal's text in the form Intl.NumberFormat reads exactly: "1335.5". */
const asText = (value: Big, places: number) =>
  value.toFixed(places) as `${number}`;

/**
 * Money as people read it: "TSh 41,000". Only whole shillings: an amount with cents is refused, not
 * rounded. Round first with roundMoney: the shop's step (money.rounding_step) is at least 1 shilling,
 * so a rounded amount has no cents. A step with cents, like 2.50, would need cents on screen; that is
 * a decision for the day a shop asks for one, so it fails loudly here instead of hiding them.
 */
export function formatMoney(amount: Big): string {
  const fitted = fit(amount, MONEY_PLACES);
  if (!fitted.round(0, Decimal.roundDown).eq(fitted))
    throw new RangeError(
      `${fitted.toString()} has cents: round it with roundMoney first.`,
    );
  return MONEY.format(asText(fitted, 0));
}

/** A quantity as people read it: "1,335.5". */
export function formatQuantity(quantity: Big): string {
  return QUANTITY.format(
    asText(fit(quantity, QUANTITY_PLACES), QUANTITY_PLACES),
  );
}

/** A selling unit, for writing stock: its size in the base unit, and the word the catalog gives it. */
export interface UnitName {
  factor: Big;
  name: string;
}

/**
 * Writes one part of the stock, a count with its unit, in the open book's order: Swahili puts the word
 * first ("mifuko 26"), English the number ("26 mifuko"). A screen passes
 * ({ count, unit }) => t("stock.part", { count, unit }).
 */
export type WritePart = (part: { count: string; unit: string }) => string;

/**
 * Stock as people count it: 1,335.5 kg in bags of 50 is "mifuko 26 + kilo 35.5". Units go biggest
 * first; `base` is the base unit's word ("kilo"). A part that is zero is left out ("kilo 35.5",
 * "mifuko 20"); nothing at all is "kilo 0". Below zero (ADR-0010) the minus is written once, before
 * the whole: "-(mifuko 2 + kilo 20)", as a minus on each part would read as a sum.
 */
export function formatStock(
  quantity: Big,
  units: readonly UnitName[],
  base: string,
  writePart: WritePart,
): string {
  const { counts, rest } = splitIntoUnits(
    quantity.abs(),
    units.map((unit) => unit.factor),
  );
  const parts = counts
    .map((count, at) => ({ count, unit: units[at]?.name ?? "" }))
    .filter((part) => !part.count.eq("0"))
    .map((part) =>
      writePart({ count: formatQuantity(part.count), unit: part.unit }),
    );
  if (!rest.eq("0") || parts.length === 0)
    parts.push(writePart({ count: formatQuantity(rest), unit: base }));
  const stock = parts.join(" + ");
  return quantity.lt("0") ? `${MINUS}(${stock})` : stock;
}

/**
 * A time of day as the shop reads it: "07:55", 24 hours, in the shop's own zone, like a phone's clock and
 * the shop's rules ("late after 08:00"), never Swahili time, "saa 1:55 asubuhi" (Jack, SYNC-11). `at` is
 * an ISO time with its zone, as a record's client_time ("2026-11-13T04:55:00.000Z"). Read in `timezone`,
 * as a laptop's own zone may be anything.
 */
export function formatTime(at: string, timezone: string): string {
  // h23 counts the hours 0 to 23: with a plain 24-hour clock some browsers write five past midnight as
  // 24:05. Each part is read by name, as shopToday reads a date's, so no locale's own order leaks in.
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(Date.parse(at));
  const part = (type: string) =>
    parts.find((each) => each.type === type)?.value ?? "";
  return `${part("hour")}:${part("minute")}`;
}
