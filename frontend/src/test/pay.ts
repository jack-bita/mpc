// pay.ts — a made-up shop's pay of a month, for tests: what the server answers for everyone's and for one worker's
// (WAGE-2), and who may open it. Tests only. Fake data: every name, amount and id is made up (rule 10).
import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer } from "@/test/fake-server";

export type Pay = components["schemas"]["Pay"];
export type PayMonth = components["schemas"]["PayMonthAnswer"];
export type WorkerPay = components["schemas"]["WorkerPay"];
export type WorkerPayMonth = components["schemas"]["WorkerPayMonthAnswer"];

/** The routes, as the pages call them (?month=… comes on top). */
export const PAY_ROUTE = "/api/v1/staffpay/pay/";
export const payRoute = (staff: string) => `${PAY_ROUTE}${staff}/`;

/** The shop's today in these tests: Wednesday 25 November 2026. */
export const TODAY = "2026-11-25";

/** The two keys of pay, as the owner holds them on the whole shop, and the server counts them on every side too. */
const KEYS = ["settings.manage", "staff.manage"];
export const OWNER: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: KEYS,
    sides: [
      { ...DAWA, permissions: KEYS },
      { ...VYAKULA, permissions: KEYS },
    ],
  },
};

/** The sum of some days: Juma's November as Jack drew it, 14 × 10,000 and 2 × 5,000, less 2,000 of fines and 16,000 of
 * meals, unless told otherwise. */
export function pay(fields: Partial<Pay> = {}): Pay {
  return {
    lines: [
      { paid_as: "full", days: 14, each: "10000.00", amount: "140000.00" },
      { paid_as: "half", days: 2, each: "5000.00", amount: "10000.00" },
    ],
    fined_days: 2,
    fines: "2000.00",
    meal_days: 16,
    meals: "16000.00",
    advances: "0.00",
    waiting: 0,
    no_rate: 0,
    total: "132000.00",
    ...fields,
  };
}

/** No days: nothing to pay. */
export const NO_PAY: Pay = {
  lines: [],
  fined_days: 0,
  fines: "0.00",
  meal_days: 0,
  meals: "0.00",
  advances: "0.00",
  waiting: 0,
  no_rate: 0,
  total: "0.00",
};

let made = 0;

/** A worker's line: Juma's 132,000, unless told otherwise. Each its own job. */
export function workerPay(fields: Partial<WorkerPay> = {}): WorkerPay {
  made += 1;
  return {
    staff: `019a8600-0000-7000-8000-${String(made).padStart(12, "0")}`,
    display_name: "Juma",
    left_on: null,
    pay: pay(),
    today: null,
    total: "132000.00",
    ...fields,
  };
}

/** Everyone's pay of November, counted up to yesterday, unless told otherwise. */
export function payMonth(
  workers: WorkerPay[],
  fields: Partial<PayMonth> = {},
): PayMonth {
  return {
    month: "2026-11",
    today: TODAY,
    counted_to: "2026-11-24",
    total: "0.00",
    workers,
    ...fields,
  };
}

/** One worker's pay of November, counted up to yesterday, unless told otherwise. */
export function workerPayMonth(
  worker: WorkerPay,
  fields: Partial<WorkerPayMonth> = {},
): WorkerPayMonth {
  return {
    month: "2026-11",
    today: TODAY,
    counted_to: "2026-11-24",
    paid_by_day: true,
    worker,
    ...fields,
  };
}

/** The server says the shop doesn't pay this worker by the day, for a test of something else on their page: whoever may
 * see pay has the page ask it (WAGE-2). */
export function notPaidByDay(staff: string): void {
  answer("GET", payRoute(staff), {
    status: 200,
    body: workerPayMonth(workerPay({ staff, pay: NO_PAY, total: "0.00" }), {
      paid_by_day: false,
    }),
  });
}
