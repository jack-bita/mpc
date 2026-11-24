// meals.ts — a made-up shop's meal money, for tests: days and rows as the server answers them (WAGE-7), and who may
// open them. Tests only. Fake data: every name, amount and id is made up.
import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";

export type MealMoneyDays = components["schemas"]["MealMoneyDaysAnswer"];
export type MealDay = components["schemas"]["MealDay"];
export type MealMoneyLine = components["schemas"]["MealMoneyLine"];

/** The shop's today in these tests: Tuesday 24 November 2026. */
export const TODAY = "2026-11-24";

/** Meneja, whom the owner gave the key: meals.record on the whole shop, as the server counts it on every side too. */
export const WITH_THE_KEY: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: ["meals.record"],
    sides: [
      { ...DAWA, permissions: ["meals.record"] },
      { ...VYAKULA, permissions: ["meals.record"] },
    ],
  },
};

let made = 0;

/** A row of a day's money: 5,000 of flour, typed by Asha on Monday morning, unless told otherwise. */
export function row(fields: Partial<MealMoneyLine> = {}): MealMoneyLine {
  made += 1;
  return {
    id: `019a8500-0000-7000-8000-${String(made).padStart(12, "0")}`,
    date: "2026-11-23",
    amount: "5000.00",
    note: "Unga na maharage",
    by: "Asha",
    at: "2026-11-23T05:10:00Z",
    voided: null,
    ...fields,
  };
}

/** One day: Monday's 8,000 among 8, unless told otherwise. */
export function mealDay(fields: Partial<MealDay> = {}): MealDay {
  return {
    date: "2026-11-23",
    amount: "8000.00",
    over: true,
    sharers: 8,
    share: "1000.00",
    waiting: 0,
    rows: [],
    ...fields,
  };
}

/** The server's answer for these days, newest first, its total as given. */
export function mealDays(
  days: MealDay[],
  fields: Partial<MealMoneyDays> = {},
): MealMoneyDays {
  return {
    first: "2026-11-01",
    last: TODAY,
    today: TODAY,
    total: "0.00",
    days,
    ready_void_reasons: [],
    ...fields,
  };
}
