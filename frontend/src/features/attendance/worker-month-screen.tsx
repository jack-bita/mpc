// worker-month-screen.tsx — one worker's month as a calendar, on the owner's or a manager's phone (ATT-12, 03 §5.10),
// opened from the worker's name on Mahudhurio ya mwezi (month-screen.tsx): the worker's name as the page's title, the
// month, the month's counts as on their line (✓ 11 · Ch 2 · …), then the month Monday first (Jt Jn Jtn Al Ij Jm Jp),
// each day its mark, a decided day by its decision (O office duty, R permission, ATT-6), and what the marks mean under
// it. A day tapped opens under the calendar (worker-day.tsx): its status, why, and each tap with its laptop and photo;
// and there a manager decides it, in a sheet over the day (decide-day.tsx, ATT-6).
//
// As Jack pictured it (19 Nov 2026) and approved as a screen (20 Nov 2026).
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
// The calendar's parts, the counts, the calendar and its key, are month-calendar.tsx's, shared with the worker's own
// page (WAGE-4), so both mark a day the same way.
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks attendance.manage
// on the whole shop; someone without it sees the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { PageHeader } from "@/components/design/page-header";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { shopToday } from "@/offline/rules";

import {
  isMonth,
  MONTH_PARAM,
  type MonthNumber,
  monthOf,
} from "./attendance-month";
import { Calendar, Counts, markOf, MarksKey } from "./month-calendar";
import { TheDay } from "./worker-day";
import {
  DAY_PARAM,
  useWorkerMonth,
  type WorkerAttendance,
} from "./worker-month";

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
