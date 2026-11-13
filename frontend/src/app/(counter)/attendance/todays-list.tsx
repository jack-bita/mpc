// todays-list.tsx — who clocked in today on this laptop, under the Mahudhurio button (SYNC-11, 02 §12): one
// line per person, the time they came and, once out, the time they left, like the sign-in sheet on the
// shop's wall. It owns how the list reads; which taps are today's is clock-today.ts's.
//
// Read live from the laptop (useTodaysTaps): a tap shows the moment it is saved, with or without the
// internet, and the list starts empty at the shop's midnight by itself. Only this laptop's taps: a clock-in
// on the Vyakula laptop is in that laptop's list (Jack, SYNC-11). Names from the laptop's copy of the staff;
// someone whose row a pull took away since, as one who left the shop, still shows, as an unknown worker:
// the tap happened, and the list must not hide it.
//
// A table, not a plain list: a screen reader reads each time with its column's name, "Aliingia 07:55".
//
// "use client": it asks use-intl for words, and reads the laptop's database, in the browser only.
"use client";

import { useId } from "react";
import { useTranslations } from "use-intl";

import { useThisDevice } from "@/features/devices/this-device";
import { dayPart, formatTime } from "@/lib/format";
import { peopleToday, useTodaysTaps } from "@/offline/clock-today";
import { useStaff } from "@/offline/reference";

export function TodaysList() {
  const t = useTranslations("attendance.list");
  const attendance = useTranslations("attendance");
  const heading = useId();
  const today = useTodaysTaps();
  const staff = useStaff();
  const timezone = useThisDevice()?.shop.timezone;

  // Nothing until both reads are in: a list drawn before the names would flash "unknown worker".
  if (today === undefined || staff === undefined || timezone === undefined)
    return null;

  const people = peopleToday(today.taps);
  const nameOf = (staffId: string) =>
    staff.find((row) => row.id === staffId)?.display_name ?? t("unknown");
  // "07:55 asubuhi" in Swahili, "07:55" in English (attendance.timeOfDay).
  const time = (at: string | null) =>
    at
      ? attendance("timeOfDay", {
          time: formatTime(at, timezone),
          part: dayPart(at, timezone),
        })
      : "";

  return (
    <section aria-labelledby={heading} className="grid gap-3">
      <h2 id={heading} className="text-xl font-semibold">
        {t("title")}
      </h2>
      {people.length === 0 ? (
        <p>{t("empty")}</p>
      ) : (
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border">
              <th scope="col" className="py-2 font-semibold">
                {t("name")}
              </th>
              <th scope="col" className="py-2 font-semibold">
                {t("came")}
              </th>
              <th scope="col" className="py-2 font-semibold">
                {t("left")}
              </th>
            </tr>
          </thead>
          <tbody>
            {people.map((person) => (
              <tr key={person.staffId} className="border-b border-border">
                <td className="py-2">{nameOf(person.staffId)}</td>
                <td className="py-2 tabular-nums">{time(person.cameAt)}</td>
                <td className="py-2 tabular-nums">{time(person.leftAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
