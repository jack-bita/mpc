// pay.ts — the month's pay as the office reads it (WAGE-2, 03 §5.10): the pages' addresses, and the answers' places in
// the store of server answers.
//
// GET /api/v1/staffpay/pay/?month=2026-11 answers everyone's pay of one month, and …/pay/{id}/ one worker's, each line by
// line: the days that are over, and today apart, once the worker tapped Toka (Leo, Jack: A). The server works it all out
// each time it is asked, from the book of days, the rates and the meals, and saves none of it (Jack); the page only shows
// it, and never adds up or multiplies anything itself. Both behind the two keys of pay, settings.manage and staff.manage
// on the whole shop (maySeePay, features/workers/pay-rates.ts), which the server asks on every read.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { STALE_AFTER } from "@/features/attendance/attendance-month";
import { askAgainEvery } from "@/features/attendance/worker-month";

export type PayMonth = components["schemas"]["PayMonthAnswer"];
export type WorkerPay = components["schemas"]["WorkerPay"];

/** Mishahara's own address, and the office home's button's. */
export const PAY_PAGE = "/pay/";

/** The pay's place in the store of server answers: every month of everyone's, and of each worker's, under it, so a save
 * that moves the pay asks them all again. */
export const PAY = ["staffpay", "pay"] as const;

/** Everyone's pay of one month, from the store of server answers; nothing is asked until the page knows which. */
export function usePayMonth(month: string | null) {
  return useQuery({
    queryKey: [...PAY, "month", month],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/pay/", {
          // Never null here: the query runs only once `enabled`.
          params: { query: { month: month ?? "" } },
        }),
      ),
    enabled: month !== null,
    // As the attendance month's: each ask works the whole month out and locks every worker's row a moment
    // (work_out_days), so it is asked again only once a minute old.
    staleTime: STALE_AFTER,
    // And while it shows this month, each minute by itself, only while the page is on the screen: Baba opens the page at
    // 18:40, and Asha's Toka at 18:45 brings her Leo (askAgainEvery).
    refetchInterval: (query) => askAgainEvery(query.state.data),
  });
}
