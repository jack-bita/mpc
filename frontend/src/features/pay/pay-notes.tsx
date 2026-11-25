// pay-notes.tsx — what is said beside a pay: how far it is counted, and what it counts or leaves out (WAGE-2). Mishahara
// says it under each name, and a worker's own pay under its total, so both say it the same way.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { monthOf, type Weekday } from "@/features/attendance/attendance-month";
import { formatDay, formatDayMonth, weekdayOf } from "@/lib/format";

import type { WorkerPay } from "./pay";

/** A month of pay, as either answer says it: which, the shop's today, the last day counted, and whether no working day of
 * it has come yet: the shop's, or the worker's own. */
export type Counted = {
  month: string;
  today: string;
  counted_to: string | null;
  no_day_yet: boolean;
};

/** Whether the pay is of the month still running: the server's to say, from its own two answers, as a phone's date can be
 * wrong (the month page's review). */
export function isThisMonth(answer: Counted): boolean {
  return monthOf(answer.today) === answer.month;
}

/** "Hadi jana, Jumanne 24/11" on this month, as no day is paid before it is over; that none is yet, on the 1st, and after
 * a 1st that was a Sunday or a closed day until a working day comes (the review). Nothing on a month gone by, which is
 * counted to its end. */
export function useCountedTo(answer: Counted): string | null {
  const t = useTranslations("pay");
  const monthWords = useTranslations("attendanceMonth");
  if (!isThisMonth(answer)) return null;
  if (answer.counted_to === null || answer.no_day_yet)
    return t("nothingOverYet");
  return t("countedTo", {
    weekday: monthWords(
      `weekdays.${String(weekdayOf(answer.counted_to)) as Weekday}`,
    ),
    date: formatDayMonth(answer.counted_to),
  });
}

/** What the pay leaves out, a line each: the days that wait for a decision, the days with no daily pay, and today when
 * its Toka waits for a decision too. Nothing when all is paid. */
export function NotPaid({ worker }: { worker: WorkerPay }) {
  const t = useTranslations("pay");
  return (
    <>
      {worker.pay.waiting > 0 ? (
        <Warning>{t("waiting", { count: worker.pay.waiting })}</Warning>
      ) : null}
      {worker.pay.no_rate > 0 ? (
        <Warning>{t("noRate", { count: worker.pay.no_rate })}</Warning>
      ) : null}
      {worker.today !== null && worker.today.waiting > 0 ? (
        <Warning>{t("todayWaits")}</Warning>
      ) : null}
    </>
  );
}

/** "Aliondoka 14/11/2026", of one who left. */
export function Left({ worker }: { worker: WorkerPay }) {
  const t = useTranslations("pay");
  return worker.left_on === null ? null : (
    <Note>{t("left", { date: formatDay(worker.left_on) })}</Note>
  );
}

/** Under a worker's name on Mishahara: what isn't paid; that today is in the total, which shows no lines; the day they
 * left; and, while the month is open, that theirs alone is approved (`approvedOn`, its day, WAGE-3). */
export function PayNotes({
  worker,
  approvedOn,
}: {
  worker: WorkerPay;
  /** The day theirs was approved alone, or null: on an approved month the page says it once, of everyone. */
  approvedOn: string | null;
}) {
  const t = useTranslations("pay");
  return (
    <>
      <NotPaid worker={worker} />
      {worker.today !== null && worker.today.waiting === 0 ? (
        <Note>{t("withToday")}</Note>
      ) : null}
      <Left worker={worker} />
      {approvedOn === null ? null : (
        <Note>{t("approval.approvedOn", { date: approvedOn })}</Note>
      )}
    </>
  );
}

/** Something not paid, with the ! of a day to decide. */
function Warning({ children }: { children: React.ReactNode }) {
  const monthWords = useTranslations("attendanceMonth");
  return (
    <Note>
      {/* The mark for the eye: the words say it to a screen reader. */}
      <span aria-hidden className="font-semibold">
        {monthWords("mark.needs_review")}{" "}
      </span>
      {children}
    </Note>
  );
}

/** A line of its own, across both columns of a list's line. */
function Note({ children }: { children: React.ReactNode }) {
  return <p className="col-span-full text-muted-foreground">{children}</p>;
}
