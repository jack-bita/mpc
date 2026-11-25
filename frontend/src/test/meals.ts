// meals.ts — a made-up shop's meal money, for tests: days and rows as the server answers them (WAGE-7), and who may
// open them. Tests only. Fake data: every name, amount and id is made up.
import type { components } from "@/api/schema";
import { useAttendanceMonth } from "@/features/attendance/attendance-month";
import { useWorkerMonth } from "@/features/attendance/worker-month";
import { useMealMoney } from "@/features/meals/meal-money";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, sent } from "@/test/fake-server";

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

const MEAL_MONEY = "/api/v1/staffpay/meal-money/";

/** Hela ya chakula open somewhere else on the page's store, as a tab's list is: for a test of what asks it again. */
export function MealMoneyAsked() {
  useMealMoney({ first: "2026-11-01", last: "2026-11-30" });
  return null;
}

/** The server answers MealMoneyAsked's question, and how many times it was asked so far. */
export function mealMoneyIsAnswered(): () => number {
  answer("GET", MEAL_MONEY, { status: 200, body: mealDays([]) });
  return () =>
    sent.filter((request) => new URL(request.url).pathname === MEAL_MONEY)
      .length;
}

const WORKER = "019a8400-0000-7000-8000-0000000000aa";
const MONTH = "/api/v1/staffpay/attendance-month/";
const WORKER_MONTH = `/api/v1/staffpay/attendance-worker/${WORKER}/`;

/** The month of attendance and one worker's month, open somewhere else on the page's store, as MealMoneyAsked is. */
export function MonthsAsked() {
  useAttendanceMonth("2026-11");
  useWorkerMonth(WORKER, "2026-11");
  return null;
}

/** The server answers MonthsAsked's two questions, and how many times each was asked so far. Nothing shows the answers; a
 * worker's month says which month it is, and today, as its own read asks, a month gone by here, so it never asks again by
 * itself. */
export function monthsAreAnswered(): () => { month: number; worker: number } {
  answer("GET", MONTH, { status: 200, body: {} });
  answer("GET", WORKER_MONTH, {
    status: 200,
    body: { month: "2026-10", today: TODAY },
  });
  const asked = (path: string) =>
    sent.filter((request) => new URL(request.url).pathname === path).length;
  return () => ({ month: asked(MONTH), worker: asked(WORKER_MONTH) });
}
