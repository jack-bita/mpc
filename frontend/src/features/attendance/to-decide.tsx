// to-decide.tsx — Zinahitaji uamuzi, the days a person must decide, at the top of the month page (ATT-5): a line per
// day, "Juma · Alhamisi 12/11 · hakuna Toka", as Jack pictured it (19 Nov 2026), so the owner sees what waits for him
// before he reads anyone's counts.
//
// The days come from the server, worked out by the book, each with why (its review_reason): oldest first, as the
// oldest has waited longest, by name on a day. The page keeps that order and only says each in words. It only shows:
// deciding a day is ATT-6's, and opening it, with its taps and its photo, ATT-12's.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useId } from "react";
import { useTranslations } from "use-intl";

import type { components } from "@/api/schema";
import { Card } from "@/components/design/card";
import { clockPart } from "@/lib/format";

type DayToDecide = components["schemas"]["DayToDecide"];

export function DaysToDecide({ days }: { days: DayToDecide[] }) {
  const t = useTranslations("attendanceMonth");
  // The heading's id, React's own for this part, so two lists on one page (ATT-12 may show a second) never share one.
  const headingId = useId();
  return (
    // A plain box, unnamed: named by its heading too, it was a region a screen reader announced, then the list inside
    // it with the same name, said twice (the review). The list carries the name alone.
    <section className="grid gap-3">
      {/* Counted in the heading, so the owner sees at once whether anything waits: "(0)" says nothing does. A third
          level: the page's title is the first, the month's name the second. */}
      <h3 id={headingId} className="text-lg font-semibold">
        {t("toDecide", { count: days.length })}
      </h3>
      {days.length === 0 ? (
        <p>{t("noneToDecide")}</p>
      ) : (
        <Card className="py-0">
          {/* A list, named by its heading, so a screen reader says how many days wait. role="list" written out, as
              Safari with VoiceOver stops calling a styled <ul> a list (workers-screen.tsx). */}
          <ul
            role="list"
            aria-labelledby={headingId}
            className="divide-y divide-border"
          >
            {days.map((day) => (
              // A day is one job's, once: its job and its date name it.
              <li key={`${day.staff} ${day.date}`} className="px-4 py-3">
                <DayLine day={day} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </section>
  );
}

/** "Juma · Alhamisi 12/11 · hakuna Toka": whose day, which, and why. */
function DayLine({ day }: { day: DayToDecide }) {
  const t = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  const [year, month, date] = day.date.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  // The weekday of a day with no time, worked out at noon UTC, never through the phone's own zone: a day has no zone,
  // and midnight in a zone behind UTC is still the day before (formatDay, src/lib/format.ts).
  const weekday = new Date(Date.UTC(year, month - 1, date, 12)).getUTCDay();
  // The time a reason names, "alifika saa 09:10 asubuhi": one of the rule's two taps, already a minute on the shop's
  // clock, with its part of the day, so nobody reads 13:20 as Swahili time (Jack, SYNC-11). Only came_late and
  // left_early name one, and the book always keeps that tap for them; any other reason's sentence has no {time}.
  const tap = day.reason === "left_early" ? day.first_out : day.first_in;
  const time =
    tap === null
      ? ""
      : attendance("timeOfDay", { time: tap, part: clockPart(tap) });
  return t("dayToDecide", {
    name: day.display_name,
    weekday: t(`weekdays.${String(weekday) as Weekday}`),
    // The day and the month, "12/11": the year is the month's, said above the list.
    date: `${String(date).padStart(2, "0")}/${String(month).padStart(2, "0")}`,
    why: t(`reason.${day.reason}`, { time }),
  });
}

/** A weekday as the word books number it, as JavaScript does: "0" is Sunday. */
type Weekday = "0" | "1" | "2" | "3" | "4" | "5" | "6";
