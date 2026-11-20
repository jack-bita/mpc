// attendance-month.ts — the month page's month as the office reads it (ATT-5, 03 §5.10): the key that opens it, the
// month's place in the store of server answers, and the months as the address writes them ("2026-11").
//
// GET /api/v1/staffpay/attendance-month/?month=2026-11 answers one month: the shop's today, a line per worker paid by
// the day with the month's counts, and the days a person must decide, each with why. The server works the month out
// from the book of days; the page only shows it. Behind attendance.manage on the whole shop: the office home offers
// the button only to someone holding it, and the server asks the key again on every read.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import type { WhoIsHere } from "@/features/people/who-is-here";

export type AttendanceMonth = components["schemas"]["AttendanceMonthAnswer"];
export type WorkerMonth = components["schemas"]["WorkerMonth"];

/** The key the month's route asks, on the whole shop: the Owner's and the Manager's (03 §5.8). */
export const MANAGES_ATTENDANCE = "attendance.manage";

/** The months' place in the store of server answers, each month under its own key. */
export const ATTENDANCE_MONTHS = ["staffpay", "attendance-month"] as const;

/** The address's name for the month: /attendance-month/?month=2026-11. */
export const MONTH_PARAM = "month";

/** Whether the person may open the month page: attendance.manage on the whole shop, not on one side, as attendance
 * belongs to the whole shop: Asha of Dawa and Baraka of Vyakula are on one list. */
export function mayManageAttendance(me: WhoIsHere): boolean {
  return me.permissions.whole_shop.includes(MANAGES_ATTENDANCE);
}

/** One month, from the store of server answers; nothing is asked until the page knows which (`null`). */
export function useAttendanceMonth(month: string | null) {
  return useQuery({
    queryKey: [...ATTENDANCE_MONTHS, month],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/attendance-month/", {
          // Never null here: the query runs only once `enabled`.
          params: { query: { month: month ?? "" } },
        }),
      ),
    enabled: month !== null,
    // Asked again only once a minute old. Each ask works the whole month out again and locks every worker's row a
    // moment (work_out_days), so a phone switched back to the page within a minute shows what it has (the review);
    // after a minute it asks again, as a tap that came late from an offline laptop may change a day. A month gone by
    // too: a late tap, or a void (ATT-6), can still change one of its days until its pay run is approved (WAGE-3).
    staleTime: STALE_AFTER,
  });
}

/** How long a month's answer is kept before the page asks for it again: a minute. */
export const STALE_AFTER = 60_000;

/** The month of a day, as the address writes it: "2026-11" of "2026-11-20". */
export function monthOf(day: string): string {
  return day.slice(0, 7);
}

/** Whether `text` is a month as the address writes one, "2026-11": anything else in the address is ignored, and the
 * page opens this month. */
export function isMonth(text: string): boolean {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(text);
}

/** The month before `month`: "2025-12" before "2026-01". Counted on its two numbers, never through a Date, which has a
 * zone and a day: the 31st of a month moved back a month would land in the wrong one. */
export function monthBefore(month: string): string {
  const [year, number] = month.split("-").map(Number) as [number, number];
  return number === 1 ? written(year - 1, 12) : written(year, number - 1);
}

/** The month after `month`: "2027-01" after "2026-12". */
export function monthAfter(month: string): string {
  const [year, number] = month.split("-").map(Number) as [number, number];
  return number === 12 ? written(year + 1, 1) : written(year, number + 1);
}

function written(year: number, number: number): string {
  return `${year}-${String(number).padStart(2, "0")}`;
}
