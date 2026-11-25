// advances.ts — money given to a worker before payday, as the office reads it (WAGE-8, 03 §5.10): the key that opens it,
// the month a page asks for, its place in the store of server answers, and the pages' addresses.
//
// GET /api/v1/staffpay/advances/?month=2026-11 answers the advances of a month, newest first, the crossed-out ones too,
// with the total of those that count and whom one may be typed for. The page only shows them, and adds nothing up.
// Behind money.advance on the whole shop, the owner's and the managers' (Jack: A): the office home offers the button
// only to someone holding it, and the server asks the key again on every read. Nothing of a worker's rate or pay is in
// the answers: those are behind the two keys of pay (maySeePay, features/workers/pay-rates.ts).
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { MONTH_PARAM } from "@/features/attendance/attendance-month";
import { askAgainEvery } from "@/features/attendance/worker-month";
import type { WhoIsHere } from "@/features/people/who-is-here";

export type AdvancesMonth = components["schemas"]["AdvancesMonthAnswer"];
export type AdvanceLine = components["schemas"]["AdvanceLine"];
export type AdvancePage = components["schemas"]["AdvancePageAnswer"];

/** The key its routes ask, on the whole shop: in the owner's role and the manager's (Jack: A). */
export const GIVES_ADVANCES = "money.advance";

/** The advances' place in the store of server answers: each month, and each one's own, under it, so a save asks them
 * all again. */
export const ADVANCES = ["staffpay", "advances"] as const;

/** The list's own address, and the office home's button's. */
export const ADVANCES_PAGE = "/advances/";

/** The list on one month, or on this one when none is known yet. */
export function advancesPage(month: string | null): string {
  return month === null
    ? ADVANCES_PAGE
    : `${ADVANCES_PAGE}?${new URLSearchParams({ [MONTH_PARAM]: month }).toString()}`;
}

/** The address's name for one's own page: /advances/view/?id=…. */
export const ADVANCE_PARAM = "id";

/** One advance's own page. */
export function advancePage(id: string): string {
  return `${ADVANCES_PAGE}view/?${new URLSearchParams({ [ADVANCE_PARAM]: id }).toString()}`;
}

/** Whether the person may open them: money.advance on the whole shop, not on one side, as a worker's pay is the whole
 * shop's. */
export function mayGiveAdvances(me: WhoIsHere): boolean {
  return me.permissions.whole_shop.includes(GIVES_ADVANCES);
}

/** A month's advances, from the store of server answers; nothing is asked until the page knows which (`null`). Asked
 * again as the page comes back, as any read is: it works nothing out and locks nothing. And this month each minute by
 * itself, while the page is on the screen, so one kept in view past midnight learns the shop's new today, which the sheet
 * asks for, and what another manager typed (the review). */
export function useAdvances(month: string | null) {
  return useQuery({
    queryKey: [...ADVANCES, "month", month],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/advances/", {
          // Never null here: the query runs only once `enabled`.
          params: { query: { month: month ?? "" } },
        }),
      ),
    enabled: month !== null,
    refetchInterval: (query) => askAgainEvery(query.state.data),
  });
}

/** One advance, from the store of server answers; nothing is asked when the address names none (`null`). */
export function useAdvance(id: string | null) {
  return useQuery({
    queryKey: [...ADVANCES, "one", id],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/advances/{id}/", {
          // Never null here: the query runs only once `enabled`.
          params: { path: { id: id ?? "" } },
        }),
      ),
    enabled: id !== null,
  });
}
