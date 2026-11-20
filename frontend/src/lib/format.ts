// format.ts — money, stock, times of day, dates and phones as people read them: "TSh 41,000", "mifuko 26 + kilo
// 35.5", "07:55", "13/11/2026" and "0712 345 678" (03 §7.4). A rule's own values too (SHOP-5): an amount written
// exactly as saved, a day with no time, "2026-12-01", and the part of the day of a clock time, "07:35". And a day's
// own sums, kept beside how a day is written: the day before it (ATT-9), its day and month alone, "12/11", and its
// weekday (ATT-5), each read from the day's own parts, so no zone moves it.
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
 * so a rounded amount has no cents. A step with cents, like 2.50, can't be set: a money rule is whole
 * shillings (Jack, 16 Nov 2026, the server's Money kind), so cents here mean a missed rounding, said loudly.
 */
export function formatMoney(amount: Big): string {
  const fitted = fit(amount, MONEY_PLACES);
  if (!fitted.round(0, Decimal.roundDown).eq(fitted))
    throw new RangeError(
      `${fitted.toString()} has cents: round it with roundMoney first.`,
    );
  return MONEY.format(asText(fitted, 0));
}

// Money with its cents, for a rule's amount (SHOP-5). A money rule is whole shillings since Jack's choice (16 Nov
// 2026), but a row saved before it keeps what it holds, and the rules page must show what is saved, never round it
// away or fail on it.
const MONEY_WITH_CENTS = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "TZS",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Money exactly as it is, for a rule's amount: "TSh 1,000" when it is whole shillings, as formatMoney writes
 * it, and "TSh 0.50" for a row saved with cents before money rules were whole shillings. Never rounds. Only the settings page uses it: everywhere else an
 * amount is rounded first, and formatMoney refuses cents so a missed rounding shows (SHOP-5).
 */
export function formatMoneyExact(amount: Big): string {
  const fitted = fit(amount, MONEY_PLACES);
  return fitted.round(0, Decimal.roundDown).eq(fitted)
    ? MONEY.format(asText(fitted, 0))
    : MONEY_WITH_CENTS.format(asText(fitted, MONEY_PLACES));
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

/**
 * A date as the shop reads it: "13/11/2026", day, month, year, the order Tanzania writes a date in, in the
 * shop's own zone. With no month name, so it reads the same in both languages. `at` is an ISO time with its
 * zone, as a record's client_time.
 */
export function formatDate(at: string, timezone: string): string {
  // Each part read by name, as for a time of day.
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).formatToParts(Date.parse(at));
  const part = (type: string) =>
    parts.find((each) => each.type === type)?.value ?? "";
  return `${part("day")}/${part("month")}/${part("year")}`;
}

/**
 * A day with no time, as a rule's new value starts on (`effective_from`, "2026-12-01"), written as formatDate
 * writes one: "01/12/2026". Read from its own parts, never through a Date: a day has no zone, and a Date
 * would put it at midnight UTC, the day before in a zone behind UTC.
 */
export function formatDay(day: string): string {
  const [year, month, date] = day.split("-");
  return `${date}/${month}/${year}`;
}

/**
 * A day's day and month alone, "12/11" of "2026-11-12", as a line of the month page writes it, its year said above
 * the list (ATT-5). From its own parts, as formatDay.
 */
export function formatDayMonth(day: string): string {
  const [, month, date] = day.split("-");
  return `${date}/${month}`;
}

/**
 * The day before `day`, both as a date box writes them: "2027-01-01" → "2026-12-31". Days only, read and written in
 * UTC, so no zone, nor a clock change, moves it (ATT-9: a closure's last day moved back to yesterday).
 */
export function dayBefore(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

/**
 * The weekday of a day, as JavaScript numbers them, Sunday 0 to Saturday 6, which the word books name (ATT-5). Read at
 * noon UTC, never through the phone's own zone: midnight UTC of the 12th is still the 11th in a zone behind UTC.
 */
export function weekdayOf(day: string): number {
  const [year, month, date] = day.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  return new Date(Date.UTC(year, month - 1, date, 12)).getUTCDay();
}

/** The part of the day a time falls in, by the shop's clock: what a Swahili screen names after the time. */
export type DayPart = "morning" | "afternoon" | "evening" | "night";

/**
 * The part of the day of `at`, in the shop's own zone: asubuhi from 05:00, mchana from 12:00, jioni from
 * 16:00, usiku from 19:00 to 04:59. A Swahili screen writes it after the time, "saa 07:55 asubuhi", so
 * nobody reads 07:55 as Swahili time, where saa saba is 13:00 (Jack, SYNC-11). Its words are in the books
 * (attendance.timeOfDay); English shows the time alone, its sentence naming the part with nothing for it, as
 * both books must fill in the same blanks (messages.test.ts).
 */
export function dayPart(at: string, timezone: string): DayPart {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      hour: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(Date.parse(at))
      .find((each) => each.type === "hour")?.value,
  );
  return partOfHour(hour);
}

/**
 * The part of the day of a clock time with no date, "07:35", as a rule of the shop's holds one
 * (attendance.on_time_until): the same parts as dayPart, so "07:35 asubuhi" reads the same on the rules
 * page as on a clock-in (SHOP-5). It is already the shop's clock, so no zone.
 */
export function clockPart(clock: string): DayPart {
  return partOfHour(Number(clock.split(":")[0]));
}

// The hours of each part, for both: asubuhi from 05:00, mchana from 12:00, jioni from 16:00, usiku the rest.
function partOfHour(hour: number): DayPart {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 16) return "afternoon";
  if (hour >= 16 && hour < 19) return "evening";
  return "night";
}

/**
 * A phone as the shop writes and says it: "+255712345678", the one form the server stores (apps/core/phones.py), is
 * "0712 345 678" on screen, the way the owner typed it in and the way a worker reads their own number back (PPL-10).
 * The server takes it back in that form too, as it cleans whatever was typed. A number of another country keeps its
 * stored form, its country code with it, as the leading 0 is Tanzania's own.
 */
export function formatPhone(phone: string): string {
  const tanzanian = /^\+255(\d{3})(\d{3})(\d{3})$/.exec(phone);
  return tanzanian ? `0${tanzanian[1]} ${tanzanian[2]} ${tanzanian[3]}` : phone;
}
