// month-calendar.tsx — a worker's month as a calendar (ATT-12): the month's counts, the month Monday first with each day's
// mark, and what the marks mean. Shared by the manager's page of a worker (worker-month-screen.tsx), where a day tapped
// opens under the calendar, and the worker's own page, Siku na malipo yangu (WAGE-4), where it opens in a sheet: one
// calendar, so the two pages can never mark the same day two ways.
//
//   ✓ 18 · Ch 2 · ½ 1 · H 0 · ! 0
//   Jt  Jn  Jtn  Al  Ij  Jm  Jp
//                            1 –
//   2 ✓  3 ✓  4 Ch  5 ✓  6 ✓  7 ✓  8 –
//   ✓ kwa wakati · Ch amechelewa · …
//
// Each part reads only what both answers have (CalendarMonth, CalendarDay): the worker's own answer is a list of what
// a worker may read, with no day's id or choices (OwnAttendanceAnswer, apps/staffpay/api/serializers.py), so the
// calendar asks for nothing beyond what it draws. The page draws the marks the server gives, never deciding itself
// what a day was.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { Card } from "@/components/design/card";
import { formatDayMonth, weekdayOf } from "@/lib/format";

import { KINDS, type Weekday } from "./attendance-month";
import {
  calendarWeeks,
  type AttendanceTap,
  type WorkerAttendance,
  type WorkerDay,
} from "./worker-month";

/** What the calendar reads of a day: what it was, and a person's decision on it. */
export type CalendarDay = Pick<WorkerDay, "date" | "status" | "decision">;

/** What the calendar reads of a month: which month, today, the job's first and last day, the worker's line of counts,
 * each day, and on which dates there were taps. */
export type CalendarMonth = Pick<
  WorkerAttendance,
  "month" | "today" | "started_on" | "left_on" | "worker"
> & {
  days: CalendarDay[];
  taps: Pick<AttendanceTap, "date">[];
};

/** The weekdays as the calendar's columns run, Monday first, as the word books number them (Sunday "0"). */
const MONDAY_FIRST: Weekday[] = ["1", "2", "3", "4", "5", "6", "0"];

/** The kind of a decided absence (ATT-6): O office duty, paid; R permission; H a no-show, as an absence the book saw. */
type Absence = "office_duty" | "permission" | "no_show";

/** What a day of the calendar shows: one of the five kinds the line counts, a decided absence by its kind, a day the shop
 * was shut, today, a day with taps the book doesn't count, or nothing. */
export type Mark =
  (typeof KINDS)[number] | Absence | "off" | "today" | "tapped" | null;

/** The marks of this page's own book, beside the line's five from the month page's. */
type OwnMark = Absence | "off" | "today" | "tapped";

/** Whether a mark is this page's own, not one of the line's five. */
function isOwn(mark: Exclude<Mark, null>): mark is OwnMark {
  return !(KINDS as readonly string[]).includes(mark);
}

/** "✓ 11 · Ch 2 · ½ 1 · H 1 · ! 1": the worker's line from the month page, as the server counted it. */
export function Counts({ answer }: { answer: CalendarMonth }) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  return (
    // A list, named, so a screen reader says what it counts. role="list" written out, as Safari with VoiceOver stops
    // calling a styled <ul> a list (workers-screen.tsx).
    <ul
      role="list"
      aria-label={t("countsLabel")}
      className="flex flex-wrap gap-x-5 gap-y-1 text-lg tabular-nums"
    >
      {KINDS.map((kind) => (
        <li key={kind}>
          {/* The mark for the eye; the kind in words for a screen reader, which can't read "Ch" or "!". */}
          <span aria-hidden>
            {t("count", {
              mark: monthWords(`mark.${kind}`),
              count: answer.worker[kind],
            })}
          </span>
          <span className="sr-only">
            {t("countSaid", {
              kind: monthWords(`kind.${kind}`),
              count: answer.worker[kind],
            })}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The month as a table: a column per weekday, Monday first, a row per week, each day its number and its mark. A day
 * with a mark is a button that opens it: under the calendar on a manager's page, in a sheet on the worker's own. */
export function Calendar({
  answer,
  days,
  monthName,
  open,
  onChoose,
}: {
  answer: CalendarMonth;
  days: Map<string, CalendarDay>;
  monthName: string;
  open: string | null;
  onChoose: (day: string) => void;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  return (
    <Card className="py-0">
      <table className="w-full table-fixed text-center tabular-nums">
        <caption className="sr-only">
          {t("calendarCaption", {
            name: answer.worker.display_name,
            month: monthName,
          })}
        </caption>
        <thead>
          <tr className="border-b border-border">
            {MONDAY_FIRST.map((weekday) => (
              <th key={weekday} scope="col" className="py-2 font-semibold">
                {/* Short for a phone's width; the whole name for a screen reader, which reads "Jtn" letter by
                    letter. */}
                <span aria-hidden>{t(`weekdaysShort.${weekday}`)}</span>
                <span className="sr-only">
                  {monthWords(`weekdays.${weekday}`)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {calendarWeeks(answer.month).map((week) => (
            // A week is named by its first place, a day or the empty place before the 1st.
            <tr key={week.find((day) => day !== null)}>
              {week.map((day, place) =>
                day === null ? (
                  <td key={`empty ${place}`} />
                ) : (
                  <td key={day} className="p-0.5 align-top">
                    <DayOfTheMonth
                      day={day}
                      mark={markOf(day, days.get(day), answer)}
                      open={day === open}
                      onChoose={onChoose}
                    />
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** The mark a day of the calendar shows: the book's own, – for a day the shop was shut; today's •, as the book keeps
 * no day until it is over, but only on one of the worker's days, from their first to their last; + for a day with taps
 * the book doesn't count, so they can still be opened; nothing for any other day. Neema, who left on the 15th, has no •
 * on the 20th, and nothing to open there: her calendar stays empty after her last day, as the card says (ATT-12's
 * review). */
export function markOf(
  day: string,
  kept: CalendarDay | undefined,
  answer: CalendarMonth,
): Mark {
  // A decided day by its decision (ATT-6): an absence by its kind, O for office duty, which is paid, apart from R and
  // H, which aren't; any other by what was decided. The book's own answer stays on the day itself (A2).
  if (kept?.decision) return kept.decision.absence_type ?? kept.decision.status;
  if (kept !== undefined) return kept.status;
  const worksThatDay =
    answer.started_on <= day &&
    (answer.left_on === null || day <= answer.left_on);
  if (day === answer.today && worksThatDay) return "today";
  // A tap on a day the book keeps nothing for: a Sunday outside the job's days, which the book never keeps, as off
  // pays nothing; a day before attendance was switched on; today, after the job's last day. Rare, but a tap the
  // answer sends must never be out of reach (ATT-12's review).
  return answer.taps.some((tap) => tap.date === day) ? "tapped" : null;
}

/** One day: its number, small, and its mark under it, big, as on Jack's picture. A day with a mark is a button, as
 * tall as a finger needs, pressed while it is open; one with none, a day to come or one the book doesn't answer, is
 * only its number. */
function DayOfTheMonth({
  day,
  mark,
  open,
  onChoose,
}: {
  day: string;
  mark: Mark;
  open: boolean;
  onChoose: (day: string) => void;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const inside = <DaysNumberAndMark day={day} mark={mark} />;
  if (mark === null) return <div className="py-1">{inside}</div>;
  return (
    <button
      type="button"
      // Named in full, "Alhamisi 12/11: inahitaji uamuzi", as a screen reader moving from button to button hears no
      // column above it; its number and mark are for the eye.
      aria-label={t("dayButton", {
        weekday: monthWords(`weekdays.${String(weekdayOf(day)) as Weekday}`),
        date: formatDayMonth(day),
        kind: kindOf(mark, t, monthWords),
      })}
      // Pressed while open, so a screen reader says which day is open, as the eye sees by its colour.
      aria-pressed={open}
      onClick={() => onChoose(day)}
      className={
        open
          ? "w-full rounded-md bg-primary py-1 text-primary-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring"
          : "w-full rounded-md py-1 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring"
      }
    >
      {inside}
    </button>
  );
}

/** A day's number and its mark, the mark for the eye, in words for a screen reader. */
function DaysNumberAndMark({ day, mark }: { day: string; mark: Mark }) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  return (
    <span className="grid gap-0.5">
      <span className="text-sm">{Number(day.slice(8))}</span>
      {mark === null ? (
        // Nothing to show: an empty place as tall as a mark, so every row keeps its height.
        <span aria-hidden className="block h-7" />
      ) : (
        <>
          <span
            aria-hidden
            className={
              mark === "needs_review"
                ? "h-7 text-lg font-bold"
                : "h-7 text-lg font-semibold"
            }
          >
            {isOwn(mark) ? t(`mark.${mark}`) : monthWords(`mark.${mark}`)}
          </span>
          <span className="sr-only">{kindOf(mark, t, monthWords)}</span>
        </>
      )}
    </span>
  );
}

/** A mark in words: one of the line's five kinds from the month page's book; a decided absence's kind, a shut day's or
 * today's from this one. */
function kindOf(
  mark: Exclude<Mark, null>,
  t: ReturnType<typeof useTranslations<"attendanceWorker">>,
  monthWords: ReturnType<typeof useTranslations<"attendanceMonth">>,
): string {
  return isOwn(mark) ? t(`kind.${mark}`) : monthWords(`kind.${mark}`);
}

/** What each mark means, under the calendar: the line's five, then a decided absence's two of its own (O, R; a no-show
 * is H, as any absence), a shut day's, today's, and a day not counted. */
export function MarksKey() {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  return (
    // A list, named, as the month page's key (month-screen.tsx).
    <ul
      role="list"
      aria-label={monthWords("keyLabel")}
      className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground"
    >
      {KINDS.map((kind) => (
        <li key={kind}>
          {monthWords(`mark.${kind}`)} {monthWords(`kind.${kind}`)}
        </li>
      ))}
      {(["office_duty", "permission", "off", "today", "tapped"] as const).map(
        (extra) => (
          <li key={extra}>
            {t(`mark.${extra}`)} {t(`kind.${extra}`)}
          </li>
        ),
      )}
    </ul>
  );
}
