// advances.ts — a made-up shop's money given before payday, for tests: a month's and one as the server answers them
// (WAGE-8), and who may open them. Tests only. Fake data: every name, amount and id is made up (rule 10).
import type { components } from "@/api/schema";
import { useAdvances } from "@/features/advances/advances";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, sent } from "@/test/fake-server";

export type AdvancesMonth = components["schemas"]["AdvancesMonthAnswer"];
export type AdvanceLine = components["schemas"]["AdvanceLine"];
export type AdvanceWorker = components["schemas"]["AdvanceWorker"];
export type AdvancePage = components["schemas"]["AdvancePageAnswer"];

/** The route, as the pages call it (?month=… comes on top). */
export const ADVANCES_ROUTE = "/api/v1/staffpay/advances/";
export const advanceRoute = (id: string) => `${ADVANCES_ROUTE}${id}/`;

/** The shop's today in these tests: Wednesday 25 November 2026. */
export const TODAY = "2026-11-25";

/** Meneja, a manager of the whole shop: money.advance is in the manager's own role (Jack: A), and the server counts it
 * on every side too. */
export const MENEJA: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: ["money.advance"],
    sides: [
      { ...DAWA, permissions: ["money.advance"] },
      { ...VYAKULA, permissions: ["money.advance"] },
    ],
  },
};

export const JUMA: AdvanceWorker = {
  staff: "019a8700-0000-7000-8000-0000000000a1",
  display_name: "Juma",
  left_on: null,
};
export const ASHA: AdvanceWorker = {
  staff: "019a8700-0000-7000-8000-0000000000a2",
  display_name: "Asha",
  left_on: null,
};

let made = 0;

/** One advance: Juma's 20,000 of the 25th, typed by Meneja, unless told otherwise. Each its own id. */
export function advance(fields: Partial<AdvanceLine> = {}): AdvanceLine {
  made += 1;
  return {
    id: `019a8700-0000-7000-8000-${String(made).padStart(12, "0")}`,
    staff: JUMA.staff,
    display_name: "Juma",
    date: TODAY,
    amount: "20000.00",
    note: "Ada ya shule",
    by: "Meneja",
    at: "2026-11-25T07:42:00Z",
    voided: null,
    ...fields,
  };
}

/** November's, newest first, its total as given. */
export function advancesMonth(
  rows: AdvanceLine[],
  fields: Partial<AdvancesMonth> = {},
): AdvancesMonth {
  return {
    month: "2026-11",
    today: TODAY,
    total: "0.00",
    rows,
    workers: [ASHA, JUMA],
    ...fields,
  };
}

/** The month's advances open somewhere else on the page's store, as a tab's list is: for a test of what asks them
 * again. */
export function AdvancesAsked() {
  useAdvances("2026-11");
  return null;
}

/** The server answers AdvancesAsked's question, and how many times it was asked so far. */
export function advancesAreAnswered(): () => number {
  answer("GET", ADVANCES_ROUTE, { status: 200, body: advancesMonth([]) });
  return () =>
    sent.filter(
      (request) =>
        request.method === "GET" &&
        new URL(request.url).pathname === ADVANCES_ROUTE,
    ).length;
}

/** One advance as its own page reads it, not the asker's own, unless told otherwise. */
export function advancePageOf(
  line: AdvanceLine,
  fields: Partial<AdvancePage> = {},
): AdvancePage {
  return { advance: line, own: false, ready_void_reasons: [], ...fields };
}
