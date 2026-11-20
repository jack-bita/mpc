// month-screen.tsx — Mahudhurio ya mwezi, the month's attendance on the owner's or a manager's phone (ATT-5, 03 §5.10):
// the month (‹ Novemba 2026 ›), the days a person must decide at the top (Zinahitaji uamuzi, to-decide.tsx), then a
// line per worker paid by the day with the month's counts, under marks a phone has room for (✓ Ch ½ H !), and what each
// mark means under them.
//
// As Jack pictured it (19 Nov 2026). It only shows: deciding a day is ATT-6's, and a worker's own month, ATT-12's.
// The server works the month out from the book of days and lists only workers with a daily pay rate, so Baba, who
// never clocks in, is not on it; the page shows the counts it is given and never adds them up itself.
//
// The month: this one, on the shop's clock, unless the address names an earlier one (?month=2026-10). ‹ goes back a
// month, › forward, never past this one, as no day after today is over. Each move writes the month in the address,
// replaced, not pushed, as the settings page keeps its tab (settings-screen.tsx): the back arrow still leaves the page,
// and a worker's page (ATT-12) comes back to the month it was opened from.
//
// An office screen: it asks the server through the store of server answers (rule 5), and needs the internet, which
// the office area says while it is gone. Its route asks attendance.manage on the whole shop; someone without it has
// no button on the office home, and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Card } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { dayBefore, formatDay } from "@/lib/format";
import { shopToday } from "@/offline/rules";

import { DaysToDecide } from "./to-decide";
import {
  type AttendanceMonth,
  isMonth,
  mayManageAttendance,
  MONTH_PARAM,
  monthAfter,
  monthBefore,
  monthOf,
  useAttendanceMonth,
  type WorkerMonth,
} from "./attendance-month";

/** The kinds of day a line counts, in the order Jack drew them: on time, late, half, absent, to decide. Off days, a
 * Sunday or a closed day, are nobody's to count. */
const KINDS = ["on_time", "late", "half", "absent", "needs_review"] as const;

export function MonthScreen({ asked }: { asked: string | null }) {
  const t = useTranslations("attendanceMonth");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const [chosen, choose] = useMonthInTheAddress(asked);
  // The page's clock: read as it opens, and again each time it comes back into view, never while drawing, as a page
  // drawn again must draw the same (React's rule; register-this-device.tsx keeps its clock in the same way).
  const { openedAt, now } = usePagesClock();
  // On the shop's clock, once the page knows the shop: a phone in another zone still reads Arusha's. The month the
  // page opened on, which it keeps until the person moves; and this month, as it is now, which › stops at.
  const openedOn = who.data
    ? monthOf(shopToday(who.data.shop.timezone, openedAt))
    : null;
  const thisMonth = who.data
    ? monthOf(shopToday(who.data.shop.timezone, now))
    : null;
  // The month shown: the one chosen, if it is a month and not one to come; else the month the page opened on. A month
  // to come has no day that is over, so the address can't open one, nor can a typo. Never moved by the clock alone:
  // Baba, back on 2 December to a page he opened in November, is checking November before payday.
  const month =
    openedOn === null || thisMonth === null
      ? null
      : chosen !== null && isMonth(chosen) && chosen <= thisMonth
        ? chosen
        : openedOn;
  const answer = useAttendanceMonth(month);
  // Until both answer: "Subiri kidogo…", never a title with nothing under it, through the store's own tries too
  // (workers-screen.tsx). Only once the month is known: a query not yet asked waits forever, and a person the server
  // refused has no month to wait for.
  const waiting = who.isPending || (month !== null && answer.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title={t("title")} intro={t("intro")} />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* Only for someone who may see a month: a seller who opened the address sees the server's refusal alone, with no
          ‹ › to press, as each press would only ask again and be refused again (the review). The server still asks
          the key on every read. */}
      {month !== null &&
      thisMonth !== null &&
      who.data &&
      mayManageAttendance(who.data) ? (
        <MonthSwitch month={month} thisMonth={thisMonth} onChoose={choose} />
      ) : null}
      {/* The month is asked here alone and its answer handed down as values, never asked again by the part that shows
          it: a part that mounts on a failed read asks again (TanStack's retryOnMount), round and round (PPL-6). A
          failed read shows its reason; a refresh that fails keeps the month last read, with the reason above it. */}
      <ApiErrorAlert error={answer.error} />
      {month !== null && answer.data && !answer.isPending ? (
        <TheMonth answer={answer.data} />
      ) : null}
    </div>
  );
}

/** The page's two looks at the clock: the moment it opened, kept; and the last, as it opened, then each time it comes
 * back into view. Baba leaves November open on 30 November and unlocks his phone on 2 December: the store asks for
 * November again as the page comes back (TanStack's refetch on focus), November stays on show, and this month moves
 * on, so › reaches December (the review). */
function usePagesClock(): { openedAt: number; now: number } {
  const [openedAt] = useState(() => Date.now());
  const [now, setNow] = useState(openedAt);
  useEffect(() => {
    function lookAgain() {
      if (document.visibilityState !== "hidden") setNow(Date.now());
    }
    // A phone unlocked, or a tab come back to, says it is visible again; a laptop's window clicked into, focused.
    document.addEventListener("visibilitychange", lookAgain);
    window.addEventListener("focus", lookAgain);
    return () => {
      document.removeEventListener("visibilitychange", lookAgain);
      window.removeEventListener("focus", lookAgain);
    };
  }, []);
  return { openedAt, now };
}

/** The month chosen, kept in the address as it changes (?month=2026-10), and how to choose another. */
function useMonthInTheAddress(
  asked: string | null,
): [string | null, (month: string) => void] {
  const [chosen, setChosen] = useState(asked);
  function choose(month: string) {
    setChosen(month);
    const url = new URL(window.location.href);
    url.searchParams.set(MONTH_PARAM, month);
    // Replaced, not pushed: the back arrow leaves the page, whatever months were looked at. null, never
    // window.history.state, so Next.js notes the new address, as settings-screen.tsx explains.
    window.history.replaceState(null, "", url);
  }
  return [chosen, choose];
}

/** ‹ Novemba 2026 ›: the month's name between its two arrows, › only before this month. */
function MonthSwitch({
  month,
  thisMonth,
  onChoose,
}: {
  month: string;
  thisMonth: string;
  onChoose: (month: string) => void;
}) {
  const t = useTranslations("attendanceMonth");
  const [year, number] = month.split("-") as [string, string];
  return (
    // Three columns, the name always in the middle. Each arrow a square button as tall as
    // a normal one, so a finger finds it; its name a word, as a screen reader can't read an arrow (page-header.tsx).
    <nav
      aria-label={t("months")}
      className="grid grid-cols-[auto_1fr_auto] items-center gap-3"
    >
      <Button
        kind="second"
        size="normal"
        aria-label={t("before")}
        className="w-(--control-normal) px-0"
        onClick={() => onChoose(monthBefore(month))}
      >
        <ChevronLeft aria-hidden className="size-6" />
      </Button>
      {/* A heading, so a screen reader can jump to it, and says the month as it changes: the page's title stays. */}
      <h2 aria-live="polite" className="text-center text-xl font-semibold">
        {t("monthTitle", {
          month: t(`monthNames.${number as MonthNumber}`),
          year,
        })}
      </h2>
      {/* Always there, greyed out on this month, as no day after today is over. Never taken away: pressed to reach
          this month, a button that went would take the keyboard's place with it, back to the page's top (the review).
          focusableWhenDisabled keeps it in the Tab order, said "dimmed" by a screen reader, where a plain disabled
          button would drop the focus it has. */}
      <Button
        kind="second"
        size="normal"
        aria-label={t("after")}
        className="w-(--control-normal) px-0"
        disabled={month >= thisMonth}
        focusableWhenDisabled
        onClick={() => onChoose(monthAfter(month))}
      >
        <ChevronRight aria-hidden className="size-6" />
      </Button>
    </nav>
  );
}

/** A month's number as the word books name it: "01" to "12". */
type MonthNumber =
  | "01"
  | "02"
  | "03"
  | "04"
  | "05"
  | "06"
  | "07"
  | "08"
  | "09"
  | "10"
  | "11"
  | "12";

/** The month's answer: how far it is counted, the days to decide, then the workers' lines and what the marks mean. */
function TheMonth({ answer }: { answer: AttendanceMonth }) {
  const t = useTranslations("attendanceMonth");
  // This month is counted to yesterday, as the book keeps no day until it is over. Whether the month shown is this
  // month is the server's to say, from its own two answers, the month and the shop's today, never from the phone's
  // clock: a page left open into the next month, read again, would say "Hadi jana, 01/12/2026" under November's full
  // table (the review). A month gone by is counted to its end.
  const isThisMonth = monthOf(answer.today) === answer.month;
  // No working day of this month over yet, the server says: on the 1st, or on Monday the 2nd after a Sunday the 1st.
  // Nobody is listed then for want of a day, not of a rate, so that is all the page says: "Hakuna mfanyakazi
  // anayelipwa kwa siku" would be untrue (ATT-5's review).
  if (isThisMonth && !answer.working_day_over) {
    return <p>{t("nothingOverYet")}</p>;
  }
  const countedTo = isThisMonth ? (
    <p>{t("countedTo", { day: formatDay(dayBefore(answer.today)) })}</p>
  ) : null;
  if (answer.workers.length === 0) {
    return (
      <>
        {countedTo}
        <p>{t("nobody")}</p>
      </>
    );
  }
  return (
    <>
      {countedTo}
      {/* At the top, before anyone's counts: what waits for the owner's decision (Jack's picture). */}
      <DaysToDecide days={answer.to_decide} />
      <Workers workers={answer.workers} />
      <MarksKey />
    </>
  );
}

/** A table: a row per worker, a column per kind of day, so the numbers line up under their marks on a phone. */
function Workers({ workers }: { workers: WorkerMonth[] }) {
  const t = useTranslations("attendanceMonth");
  return (
    <Card className="py-0">
      <table className="w-full tabular-nums">
        {/* The table's name, for a screen reader: the page's month is said by the heading above it. */}
        <caption className="sr-only">{t("workersCaption")}</caption>
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="px-4 py-3 text-left font-semibold">
              {t("worker")}
            </th>
            {KINDS.map((kind) => (
              <th
                key={kind}
                scope="col"
                // Room at the row's end, as the name has at its start.
                className="w-10 py-3 text-center font-semibold last:pr-3"
              >
                {/* The mark for the eye, the kind in words for a screen reader, which can't read "Ch" or "!". */}
                <span aria-hidden>{t(`mark.${kind}`)}</span>
                <span className="sr-only">{t(`kind.${kind}`)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {workers.map((worker) => (
            <tr key={worker.staff}>
              <th scope="row" className="px-4 py-3 text-left font-normal">
                {worker.display_name}
              </th>
              {KINDS.map((kind) => (
                <td key={kind} className="py-3 text-center last:pr-3">
                  {worker[kind]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

/** What each mark means, under the table: "✓ kwa wakati · Ch amechelewa · …", for whoever doesn't know them yet. */
function MarksKey() {
  const t = useTranslations("attendanceMonth");
  return (
    // A list, named, so a screen reader says what it is and how many marks there are. role="list" written out, as
    // Safari with VoiceOver stops calling a styled <ul> a list (workers-screen.tsx).
    <ul
      role="list"
      aria-label={t("keyLabel")}
      className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground"
    >
      {KINDS.map((kind) => (
        <li key={kind}>
          {t(`mark.${kind}`)} {t(`kind.${kind}`)}
        </li>
      ))}
    </ul>
  );
}
