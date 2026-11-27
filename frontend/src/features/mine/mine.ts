// mine.ts — a worker's own days and pay as Siku na malipo yangu reads them (WAGE-4, 02 A4; 03 §5.10): the page's address,
// its place in the store of server answers, and its reads.
//
// GET /api/v1/staffpay/mine/attendance/?month=2026-11 answers the month of the job the login names, whoever is logged in,
// with no key: a PIN's at the shop's laptop, or a password's on a phone. No id is sent, so nobody can ask for anyone
// else's. The server works it all out, by the manager's very services; the page only shows it.
//
// Never kept on the laptop (03 §6.1, payslips never on shared devices): the server says no-store, so the browser keeps
// no copy; the service worker keeps none of /api (src/sw.ts); and the store of server answers, in the tab's memory
// only, lets each answer go the moment no page shows it (`gcTime: 0`), and forgets them all at each login, Toka and
// switch (forgetTheLastPerson, src/api/query-client.ts), so the next person at the laptop finds none.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { STALE_AFTER } from "@/features/attendance/attendance-month";
import { askAgainEvery } from "@/features/attendance/worker-month";

export type OwnAttendance = components["schemas"]["OwnAttendanceAnswer"];
export type OwnDay = components["schemas"]["OwnDay"];
export type OwnTap = components["schemas"]["OwnTap"];

/** The page, from the PIN's welcome and the office's home: /my-days-and-pay/?month=2026-11. */
export const MY_DAYS_AND_PAY_PAGE = "/my-days-and-pay/";

/** The worker's own answers' place in the store of server answers. */
export const MINE = ["staffpay", "mine"] as const;

/** The worker's own month, from the store of server answers; nothing is asked until the page knows which month. */
export function useMyDays(month: string | null) {
  return useQuery({
    queryKey: [...MINE, "attendance", month],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/mine/attendance/", {
          // Never null here: the query runs only once `enabled`.
          params: { query: { month: month ?? "" } },
        }),
      ),
    enabled: month !== null,
    // As the manager's calendar of a worker (worker-month.ts): each ask works the shop's month out, so it is asked
    // again only once a minute old, and each minute by itself while it shows this month, as today's taps come.
    staleTime: STALE_AFTER,
    refetchInterval: (query) => askAgainEvery(query.state.data),
    // Let go the moment the page is gone, never kept for a later page: a worker's own days and pay stay in the laptop's
    // memory only while they are on its screen. So ‹ back to a month read before asks it again.
    gcTime: 0,
  });
}
