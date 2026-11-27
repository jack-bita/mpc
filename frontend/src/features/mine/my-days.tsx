// my-days.tsx — Siku, a worker's own month on Siku na malipo yangu (WAGE-4), as Jack pictured it (27 Nov 2026): the
// counts, the month Monday first with each day's mark, and what the marks mean, the manager's very calendar of them
// (month-calendar.tsx), so the two never mark a day two ways. A day with a mark, tapped, opens in a sheet over the page
// (my-day-sheet.tsx), never under the calendar: nothing unfolds inside the same page (Jack, CTRL-4).
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import type { MonthNumber } from "@/features/attendance/attendance-month";
import {
  Calendar,
  Counts,
  markOf,
  MarksKey,
} from "@/features/attendance/month-calendar";

import type { OwnAttendance } from "./mine";
import { MyDaySheet } from "./my-day-sheet";

export function MyDays({
  answer,
  timezone,
}: {
  answer: OwnAttendance;
  /** The shop's zone, read once by the screen, for the date a decision or a fix was made on. */
  timezone: string | null;
}) {
  const monthWords = useTranslations("attendanceMonth");
  // The day whose sheet is open, or none. Not kept in the address: a sheet is a moment over the page, and the back arrow
  // leaves the page, never a day.
  const [chosen, choose] = useState<string | null>(null);
  const [year, number] = answer.month.split("-") as [string, MonthNumber];
  const monthName = monthWords("monthTitle", {
    month: monthWords(`monthNames.${number}`),
    year,
  });
  const days = new Map(answer.days.map((day) => [day.date, day]));
  // Only a day of this month with a mark opens: one chosen before ‹ or › changed the month opens nothing on the next.
  const open =
    chosen !== null &&
    chosen.startsWith(`${answer.month}-`) &&
    markOf(chosen, days.get(chosen), answer) !== null
      ? chosen
      : null;
  return (
    <div className="grid gap-4">
      <Counts answer={answer} />
      <Calendar
        answer={answer}
        days={days}
        monthName={monthName}
        open={open}
        onChoose={choose}
      />
      <MarksKey />
      {/* Drawn only while open, so each opening starts afresh; as it closes, the keyboard goes back to the day's button,
          which stays on the calendar (sheet.tsx). */}
      {open !== null ? (
        <MyDaySheet
          day={open}
          answer={answer}
          timezone={timezone}
          onClose={() => choose(null)}
        />
      ) : null}
    </div>
  );
}
