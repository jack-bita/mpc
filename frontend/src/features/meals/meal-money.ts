// meal-money.ts — the day's meal money as the office reads it (WAGE-7, 03 §5.10): the key that opens it, the days a page
// asks for, their place in the store of server answers, and the pages' addresses.
//
// GET /api/v1/staffpay/meal-money/?first=2026-11-01&last=2026-11-30 answers the days of a span, newest first, each with
// its money, how many share it, each one's share and its rows, and the whole of them. The server works them out through
// the book of days; the page only shows them, and never adds up or splits anything itself. Behind meals.record on the
// whole shop, the owner's own key, which he gives to whoever he chooses (Jack, 15 Nov 2026): the office home offers the
// button only to someone holding it, and the server asks the key again on every read.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { STALE_AFTER } from "@/features/attendance/attendance-month";
import type { WhoIsHere } from "@/features/people/who-is-here";

export type MealMoneyDays = components["schemas"]["MealMoneyDaysAnswer"];
export type MealDay = components["schemas"]["MealDay"];
export type MealMoneyLine = components["schemas"]["MealMoneyLine"];

/** The key its routes ask, on the whole shop: the owner's own (spec §6), given to whoever he chooses. */
export const RECORDS_MEALS = "meals.record";

/** The days' place in the store of server answers, each span under its own key. */
export const MEAL_MONEY = ["staffpay", "meal-money"] as const;

/** The list's own address, and the office home's button's. */
export const MEAL_MONEY_PAGE = "/meal-money/";

/** Whether the person may open it: meals.record on the whole shop, not on one side, as the workers of both sides eat
 * together. */
export function mayRecordMeals(me: WhoIsHere): boolean {
  return me.permissions.whole_shop.includes(RECORDS_MEALS);
}

/** Days from one to another, both counted, as the server takes them: "2026-11-20". */
export type Span = { first: string; last: string };

/** A month's first and last day: "2026-11" → 01/11 to 30/11. Day 0 of the month after is this one's last, and Date.UTC
 * counts a leap February by itself; in UTC, so no zone moves it. */
export function monthSpan(month: string): Span {
  const [year, number] = month.split("-").map(Number) as [number, number];
  const last = new Date(Date.UTC(year, number, 0)).toISOString().slice(0, 10);
  return { first: `${month}-01`, last };
}

/** A span's days, from the store of server answers; nothing is asked until the page knows which (`null`). */
export function useMealMoney(span: Span | null) {
  return useQuery({
    queryKey: [...MEAL_MONEY, span?.first, span?.last],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/meal-money/", {
          // Never null here: the query runs only once `enabled`.
          params: {
            query: { first: span?.first ?? "", last: span?.last ?? "" },
          },
        }),
      ),
    enabled: span !== null,
    // As the month of attendance: each ask works the days out again and locks every worker's row a moment
    // (work_out_days), so a phone switched back within a minute shows what it has.
    staleTime: STALE_AFTER,
  });
}
