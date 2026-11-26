// pay.ts — a made-up shop's pay of a month, for tests: what the server answers for everyone's and for one worker's
// (WAGE-2), and who may open it. Tests only. Fake data: every name, amount and id is made up (rule 10).
import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { usePayMonth, useWorkerPay } from "@/features/pay/pay";
import { answer, sent } from "@/test/fake-server";

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

/** The owner who may approve the pay too: the approval's own key, on the whole shop (WAGE-3). */
export const APPROVER: components["schemas"]["WhoIsHere"] = {
  ...OWNER,
  permissions: { ...OWNER.permissions, whole_shop: [...KEYS, "pay.approve"] },
};

export type ToApprove = components["schemas"]["ToApprove"];

/** What an approval waits for and warns of: nothing, unless told otherwise. */
export function nothingStops(fields: Partial<ToApprove> = {}): ToApprove {
  return {
    earlier: null,
    waiting: [],
    no_rate: [],
    still_clocked_in: false,
    quiet_laptops: [],
    came_unpaid: [],
    ...fields,
  };
}

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
    carried: "0.00",
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
  carried: "0.00",
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
    carried_from: null,
    approval: null,
    // A draft: no payslip keeps it yet, so nothing is handed out, and it is nobody's own (WAGE-9).
    payslip: null,
    payments: [],
    to_hand_out: "0.00",
    own: false,
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
    no_day_yet: false,
    total: "0.00",
    workers,
    approval: null,
    to_approve: null,
    // Open: no Bado kulipa until it is approved (WAGE-9).
    still_to_pay: null,
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
    no_day_yet: false,
    worker,
    to_approve: null,
    // No ready reason to cross a payment out with, as off the demo it is typed (WAGE-9).
    void_reasons: [],
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

const SOMEONE = "019a8600-0000-7000-8000-0000000000ff";

/** Everyone's pay and one worker's, open somewhere else on the page's store, as a tab's are: for a test of what asks them
 * again. */
export function PayAsked() {
  usePayMonth("2026-11");
  useWorkerPay(SOMEONE, "2026-11");
  return null;
}

/** The server answers PayAsked's two questions, and how many times each was asked so far. A month gone by, so neither
 * asks again by itself. */
export function payIsAnswered(): () => [month: number, worker: number] {
  const body = { month: "2026-10", today: TODAY };
  answer("GET", PAY_ROUTE, { status: 200, body });
  answer("GET", payRoute(SOMEONE), { status: 200, body });
  const asked = (path: string) =>
    sent.filter((request) => new URL(request.url).pathname === path).length;
  return () => [asked(PAY_ROUTE), asked(payRoute(SOMEONE))];
}
