// worker-month.ts — a worker's month as the office reads it (ATT-12, 03 §5.10): its address, with the day open under
// the calendar, its place in the store of server answers, and the month's weeks as the calendar draws them, Monday
// first.
//
// GET /api/v1/staffpay/attendance-worker/{id}/?month=2026-11 answers one worker's month: their days as the book keeps
// them, their counts, and every tap of the month, today's too. The server works it all out; the page only shows it.
// Behind attendance.manage on the whole shop, as the month page: someone without it is refused by the server.
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { weekdayOf } from "@/lib/format";

import { MONTH_PARAM, monthOf, STALE_AFTER } from "./attendance-month";

export type WorkerAttendance = components["schemas"]["WorkerAttendanceAnswer"];
export type WorkerDay = components["schemas"]["WorkerDay"];
export type AttendanceTap = components["schemas"]["AttendanceTap"];

/** The workers' months' place in the store of server answers, each worker's month under its own key. */
export const WORKER_MONTHS = ["staffpay", "attendance-worker"] as const;

/** The address's name for the worker: /attendance-month/worker/?staff=…&month=2026-11. */
export const STAFF_PARAM = "staff";

/** The address's name for the day open under the calendar: …&day=2026-11-12. */
export const DAY_PARAM = "day";

/** The address of a worker's month, as a name on the month page opens it: their job's id, and the month shown; and a
 * day of it, open under the calendar, as a line of Zinahitaji uamuzi opens one. */
export function workerMonthAddress(
  staff: string,
  month: string,
  day?: string,
): string {
  const query = new URLSearchParams({
    [STAFF_PARAM]: staff,
    [MONTH_PARAM]: month,
  });
  if (day !== undefined) query.set(DAY_PARAM, day);
  return `/attendance-month/worker/?${query.toString()}`;
}

/** One worker's month, from the store of server answers; nothing is asked until the page knows whose and which. */
export function useWorkerMonth(staff: string | null, month: string | null) {
  return useQuery({
    queryKey: [...WORKER_MONTHS, staff, month],
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/attendance-worker/{id}/", {
          // Never null here: the query runs only once `enabled`.
          params: { path: { id: staff ?? "" }, query: { month: month ?? "" } },
        }),
      ),
    enabled: staff !== null && month !== null,
    // As the month page's: each ask works the whole month out and locks every worker's row a moment
    // (work_out_days), so it is asked again only once a minute old; a tap that came late may change a day.
    staleTime: STALE_AFTER,
    // And while it shows this month, asked again each minute by itself, so today's taps come as they are made
    // (ATT-12's review): only while the page is on the screen, as TanStack stops counting in a hidden tab.
    refetchInterval: (query) => askAgainEvery(query.state.data),
  });
}

/**
 * How often a worker's month is asked again by itself: each minute while it is this month, by the server's own today,
 * as today's taps come during the day; never for a month gone by, whose days are over, nor before the first answer.
 */
export function askAgainEvery(
  answer: WorkerAttendance | undefined,
): number | false {
  return answer !== undefined && monthOf(answer.today) === answer.month
    ? STALE_AFTER
    : false;
}

/**
 * The weeks of `month`, "2026-11", as the calendar draws them: a row per week, Monday first, each day as the address
 * writes one ("2026-11-12"), and null for a place before the 1st or after the last. From the month's own numbers and
 * weekdayOf, never through the phone's zone, which could move a midnight into the day before.
 */
export function calendarWeeks(month: string): (string | null)[][] {
  const [year, number] = month.split("-").map(Number) as [number, number];
  // Day 0 of the month after is the last of this one: 30, 31, 28 or 29. In UTC, so no zone moves it.
  const length = new Date(Date.UTC(year, number, 0)).getUTCDate();
  // Places before the 1st: none on a Monday, six on a Sunday (weekdayOf counts Sunday 0, Monday 1).
  const before = (weekdayOf(`${month}-01`) + 6) % 7;
  const places: (string | null)[] = [
    ...Array.from({ length: before }, () => null),
    ...Array.from(
      { length },
      (_, index) => `${month}-${String(index + 1).padStart(2, "0")}`,
    ),
  ];
  // The last week filled to Sunday with empty places, so every row has seven.
  while (places.length % 7 !== 0) places.push(null);
  return Array.from({ length: places.length / 7 }, (_, week) =>
    places.slice(week * 7, week * 7 + 7),
  );
}
