// pay-notes.tsx — what is said beside a pay: how far it is counted, and what it counts or leaves out (WAGE-2). Mishahara
// says it under each name, and a worker's own pay under its total, so both say it the same way.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { monthOf, type Weekday } from "@/features/attendance/attendance-month";
import { formatDay, formatDayMonth, weekdayOf } from "@/lib/format";

import type { WorkerPay } from "./pay";

/** "Hadi jana, Jumanne 24/11" on this month, as no day is paid before it is over; on the 1st, that none is yet. Nothing
 * on a month gone by, which is counted to its end. Whether it is this month is the server's to say, from its own two
 * answers: a phone's date can be wrong (the month page's review). */
export function CountedTo({
  answer,
}: {
  answer: { month: string; today: string; counted_to: string | null };
}) {
  const t = useTranslations("pay");
  const monthWords = useTranslations("attendanceMonth");
  if (monthOf(answer.today) !== answer.month) return null;
  if (answer.counted_to === null) return <p>{t("nothingOverYet")}</p>;
  return (
    <p>
      {t("countedTo", {
        weekday: monthWords(
          `weekdays.${String(weekdayOf(answer.counted_to)) as Weekday}`,
        ),
        date: formatDayMonth(answer.counted_to),
      })}
    </p>
  );
}

/** Under a worker's name on Mishahara: the days that wait for a decision or have no daily pay, neither paid; whether
 * today is in the total, or waits; and the day they left. A line each, under the name, across both columns. */
export function PayNotes({ worker }: { worker: WorkerPay }) {
  const t = useTranslations("pay");
  return (
    <>
      {worker.pay.waiting > 0 ? (
        <Warning>{t("waiting", { count: worker.pay.waiting })}</Warning>
      ) : null}
      {worker.pay.no_rate > 0 ? (
        <Warning>{t("noRate", { count: worker.pay.no_rate })}</Warning>
      ) : null}
      {worker.today === null ? null : worker.today.waiting > 0 ? (
        <Warning>{t("todayWaits")}</Warning>
      ) : (
        <Note>{t("withToday")}</Note>
      )}
      {worker.left_on === null ? null : (
        <Note>{t("left", { date: formatDay(worker.left_on) })}</Note>
      )}
    </>
  );
}

/** Something not paid, with the ! of a day to decide. */
export function Warning({ children }: { children: React.ReactNode }) {
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

function Note({ children }: { children: React.ReactNode }) {
  return <p className="col-span-full pl-4 text-muted-foreground">{children}</p>;
}
