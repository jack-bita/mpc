// worker-month-screen.tsx — one worker's month as a calendar, on the owner's or a manager's phone (ATT-12, 03 §5.10),
// opened from the worker's name on Mahudhurio ya mwezi (month-screen.tsx): the worker's name as the page's title, the
// month, the month's counts as on their line (✓ 11 · Ch 2 · …), then the month Monday first (Jt Jn Jtn Al Ij Jm Jp),
// each day its mark, a decided day by its decision (O office duty, R permission, ATT-6), and what the marks mean under it. A day tapped opens under the calendar (worker-day.tsx): its
// status, why, and each tap with its laptop and photo.
//
// As Jack pictured it (19 Nov 2026) and approved as a screen (20 Nov 2026). It only shows: deciding a day is ATT-6's.
// The server works the month out from the book of days, and the page draws the marks it is given, never deciding
// itself what a day was: – a Sunday or a closed day (`off`), • today, which the book keeps only once it is over, and
// nothing for a day the book doesn't answer, a day to come, before the worker's first day or after their last.
//
// The month is the one the page came from (?month=2026-11), with no ‹ › of its own (Jack's yes, 20 Nov 2026): to see
// another, the back arrow returns to the month page, on the same month, as the month page keeps it in its address.
// Opened from a typed address, the arrow goes to the month page on this worker's month (`fallback`). The day open is
// kept in the address too (&day=2026-11-12), replaced, not pushed, as the month page keeps its month: the back arrow
// leaves the page, whatever days were looked at, and a line of Zinahitaji uamuzi opens its day directly.
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks attendance.manage
// on the whole shop; someone without it sees the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { formatDayMonth, weekdayOf } from "@/lib/format";
import { shopToday } from "@/offline/rules";

import {
  isMonth,
  KINDS,
  MONTH_PARAM,
  type MonthNumber,
  monthOf,
  type Weekday,
} from "./attendance-month";
import { TheDay } from "./worker-day";
import {
  calendarWeeks,
  DAY_PARAM,
  useWorkerMonth,
  type WorkerAttendance,
  type WorkerDay,
} from "./worker-month";

/** The weekdays as the calendar's columns run, Monday first, as the word books number them (Sunday "0"). */
const MONDAY_FIRST: Weekday[] = ["1", "2", "3", "4", "5", "6", "0"];

/** The kind of a decided absence (ATT-6): O office duty, paid; R permission; H a no-show, as an absence the book saw. */
type Absence = "office_duty" | "permission" | "no_show";

/** What a day of the calendar shows: one of the five kinds the line counts, a decided absence by its kind, a day the shop
 * was shut, today, a day with taps the book doesn't count, or nothing. */
type Mark =
  (typeof KINDS)[number] | Absence | "off" | "today" | "tapped" | null;

/** The marks of this page's own book, beside the line's five from the month page's. */
type OwnMark = Absence | "off" | "today" | "tapped";

/** Whether a mark is this page's own, not one of the line's five. */
function isOwn(mark: Exclude<Mark, null>): mark is OwnMark {
  return !(KINDS as readonly string[]).includes(mark);
}

export function WorkerMonthScreen({
  staff,
  asked,
  askedDay,
}: {
  staff: string | null;
  asked: string | null;
  askedDay: string | null;
}) {
  const t = useTranslations("attendanceWorker");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  // The moment the page opened, read once, never while drawing (React's rule; month-screen.tsx keeps it the same way).
  const [openedAt] = useState(() => Date.now());
  // The month the address names, as the month page wrote it; or, with none, or one that is no month, this month on
  // the shop's clock, once the page knows the shop.
  const month =
    asked !== null && isMonth(asked)
      ? asked
      : who.data
        ? monthOf(shopToday(who.data.shop.timezone, openedAt))
        : null;
  const answer = useWorkerMonth(staff, month);
  const [chosen, choose] = useDayInTheAddress(askedDay);
  // Until both answer: "Subiri kidogo…", through the store's own tries too (month-screen.tsx). Only for a worker the
  // address names: with none, nothing is asked, and nothing waits.
  const waiting =
    who.isPending || (staff !== null && month !== null && answer.isPending);
  // The month page on this month, for the arrow when going back would leave the app.
  const back =
    month === null
      ? "/attendance-month/"
      : `/attendance-month/?${new URLSearchParams({ [MONTH_PARAM]: month }).toString()}`;

  return (
    <div className="grid max-w-2xl gap-6">
      {/* The worker's name as the title once the server says it, as Jack drew it ("← Juma"); until then, what the page
          is. */}
      <PageHeader
        title={answer.data?.worker.display_name ?? t("title")}
        intro={t("intro")}
        fallback={back}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* An address with no worker names nobody: the page says so, and asks nothing. */}
      {staff === null ? <p>{t("noWorker")}</p> : null}
      {/* Not logged in, no network, the server's own problem; or the month refused: no key, or a worker the shop
          doesn't have, "not found", as for an id no shop has (03 §5.4). The month is asked here alone and its answer
          handed down as values, never asked again by the part that shows it (PPL-6). */}
      <ApiErrorAlert error={who.error} />
      <ApiErrorAlert error={answer.error} />
      {answer.data && !answer.isPending ? (
        <TheWorkersMonth
          answer={answer.data}
          chosen={chosen}
          onChoose={choose}
          timezone={who.data?.shop.timezone ?? null}
        />
      ) : null}
    </div>
  );
}

/** The day open under the calendar, kept in the address as it changes (&day=2026-11-12), and how to open another. */
function useDayInTheAddress(
  asked: string | null,
): [string | null, (day: string) => void] {
  const [chosen, setChosen] = useState(asked);
  function choose(day: string) {
    setChosen(day);
    const url = new URL(window.location.href);
    url.searchParams.set(DAY_PARAM, day);
    // Replaced, not pushed: the back arrow leaves the page, whatever days were opened. null, never
    // window.history.state, so Next.js notes the new address (settings-screen.tsx, month-screen.tsx).
    window.history.replaceState(null, "", url);
  }
  return [chosen, choose];
}

/** The month's name, the counts, the calendar and what its marks mean, then the day open, if one is. */
function TheWorkersMonth({
  answer,
  chosen,
  onChoose,
  timezone,
}: {
  answer: WorkerAttendance;
  chosen: string | null;
  onChoose: (day: string) => void;
  /** The shop's zone, read once by the screen, for the date a decision was made on (ATT-6). */
  timezone: string | null;
}) {
  const monthWords = useTranslations("attendanceMonth");
  const [year, number] = answer.month.split("-") as [string, MonthNumber];
  const monthName = monthWords("monthTitle", {
    month: monthWords(`monthNames.${number}`),
    year,
  });
  // The book's days by date, to find each day's in one look.
  const days = new Map(answer.days.map((day) => [day.date, day]));
  // The day open: one of this month with a mark only, a day the book answers or today, as only those can be tapped.
  // A day the address names that has none, a day to come, or another month's, as ?month=2026-10&day=2026-11-20 would
  // name, opens nothing: never a November day under October's calendar (ATT-12's review).
  const open =
    chosen !== null &&
    chosen.startsWith(`${answer.month}-`) &&
    markOf(chosen, days.get(chosen), answer) !== null
      ? chosen
      : null;
  return (
    <>
      {/* A heading, so a screen reader can jump to it: the page's title is the worker's name. */}
      <h2 className="text-xl font-semibold">{monthName}</h2>
      <Counts answer={answer} />
      <Calendar
        answer={answer}
        days={days}
        monthName={monthName}
        open={open}
        onChoose={onChoose}
      />
      <MarksKey />
      {open !== null ? (
        <TheDay day={open} answer={answer} timezone={timezone} />
      ) : null}
    </>
  );
}

/** "✓ 11 · Ch 2 · ½ 1 · H 1 · ! 1": the worker's line from the month page, as the server counted it. */
function Counts({ answer }: { answer: WorkerAttendance }) {
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
 * with a mark is a button that opens it under the calendar. */
function Calendar({
  answer,
  days,
  monthName,
  open,
  onChoose,
}: {
  answer: WorkerAttendance;
  days: Map<string, WorkerDay>;
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
function markOf(
  day: string,
  kept: WorkerDay | undefined,
  answer: WorkerAttendance,
): Mark {
  // A decided day by its decision (ATT-6): an absence by its kind, O for office duty, which is paid, apart from R and H,
  // which aren't; any other by what was decided. The book's own answer stays on the day itself (A2).
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
function MarksKey() {
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
