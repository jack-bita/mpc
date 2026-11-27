// my-day-sheet.tsx — one of a worker's own days, in a sheet over their calendar on Siku na malipo yangu (WAGE-4), as
// Jack pictured it (27 Nov 2026):
//
//   ┌ Jumatano 04/11/2026 ───────────────────────┐
//   │  Amechelewa · faini 500                    │
//   │  Chakula: TSh 1,500                        │
//   │  Ingia na Toka za siku hii                 │
//   │    Ingia saa 08:20 asubuhi · Kompyuta Dawa │
//   │    Toka  saa 18:05 jioni · Kompyuta Dawa   │
//   │                                [ Funga ]   │
//   └────────────────────────────────────────────┘
//
// In a sheet, never opened in place under the calendar, as the manager's day is (Jack, CTRL-4: nothing unfolds inside the
// same page). Its words are the manager's own day's (worker-day.tsx): what the day was and its fine, or the decision
// with who and why and what the system said (A2); the worker's share of the day's meals; each tap, one crossed out in
// the office struck through with who, when and why, one added there with who added it and why (Jack: A); and what the day
// is missing. Only to read: no Amua, no Batilisha, no Ongeza Ingia au Toka, and no photo, which the answer doesn't
// carry, nor a tap's doubt, the shop's check on its laptops. So the sheet's only button is Funga (sheet.tsx).
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useId } from "react";
import { useTranslations } from "use-intl";

import { Sheet } from "@/components/design/sheet";
import type { Weekday } from "@/features/attendance/attendance-month";
import {
  BookSays,
  Decided,
  Missing,
  readyWords,
  useTapLine,
  voidedWords,
} from "@/features/attendance/worker-day";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney, weekdayOf } from "@/lib/format";

import type { OwnAttendance, OwnTap } from "./mine";

export function MyDaySheet({
  day,
  answer,
  timezone,
  onClose,
}: {
  /** The day open, "2026-11-04": one the calendar marks, as only those open. */
  day: string;
  answer: OwnAttendance;
  /** The shop's zone, for the date a decision was made or a tap fixed on; none while the page doesn't know the shop. */
  timezone: string | null;
  onClose: () => void;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const tapsHeading = useId();
  // The day as the book kept it, or none for today, which the book keeps only once it is over, or a day it doesn't
  // count, opened for its taps alone (the calendar's +).
  const kept = answer.days.find((each) => each.date === day);
  const isToday = day === answer.today;
  // The day's taps in the order they were made, the crossed-out ones too, struck through; and those that count, for what
  // the day is missing.
  const taps = answer.taps.filter((tap) => tap.date === day);
  const counted = taps.filter((tap) => tap.voided === null);
  const title = {
    weekday: monthWords(`weekdays.${String(weekdayOf(day)) as Weekday}`),
    date: formatDay(day),
  };
  return (
    <Sheet
      open
      onClose={onClose}
      title={isToday ? t("dayTitleToday", title) : t("dayTitle", title)}
    >
      {isToday ? <p>{t("notOverYet")}</p> : null}
      {!isToday && kept === undefined ? <p>{t("notCounted")}</p> : null}
      {kept !== undefined ? (
        <>
          {kept.decision !== null ? (
            <Decided day={kept} answer={answer} timezone={timezone} />
          ) : (
            <BookSays day={kept} answer={answer} />
          )}
          {/* Their share of the day's meals, as the book kept it (WAGE-7), on a day with one. */}
          {new Decimal(kept.meal_share).gt("0") ? (
            <p>
              {t("meals", {
                amount: formatMoney(new Decimal(kept.meal_share)),
              })}
            </p>
          ) : null}
        </>
      ) : null}
      {taps.length > 0 ? (
        <div className="grid gap-2">
          <p id={tapsHeading} className="text-muted-foreground">
            {t("tapsLabel")}
          </p>
          {/* role="list" written out, as Safari with VoiceOver stops calling a styled <ul> a list (workers-screen.tsx). */}
          <ul role="list" aria-labelledby={tapsHeading} className="grid gap-3">
            {taps.map((tap) => (
              <li key={tap.id}>
                <MyTap tap={tap} answer={answer} timezone={timezone} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <Missing kept={kept} taps={counted} isToday={isToday} />
    </Sheet>
  );
}

/** One of the worker's own taps: its line, as the manager's day says it; struck through once crossed out, with who,
 * when and why; why it was added in the office; and whether it came after its day's pay was approved (WAGE-10). */
function MyTap({
  tap,
  answer,
  timezone,
}: {
  tap: OwnTap;
  answer: OwnAttendance;
  timezone: string | null;
}) {
  const t = useTranslations("attendanceWorker");
  const { line } = useTapLine(tap, timezone);
  return (
    <div className="grid gap-1">
      {/* Struck through once crossed out (<s>, what is no longer right), with who, when and why on the line under it,
          which a screen reader says too, as it says no strike (ATT-13). */}
      <p className={tap.voided === null ? undefined : "text-muted-foreground"}>
        {tap.voided === null ? line : <s>{line}</s>}
      </p>
      {tap.voided !== null ? (
        <p>{voidedWords(tap.voided, answer, timezone, t)}</p>
      ) : null}
      {tap.entered !== null ? (
        <p>
          {t("decisionReason", {
            reason: readyWords(tap.entered.reason, answer.ready_add_reasons, t),
          })}
        </p>
      ) : null}
      {tap.after_approval ? (
        <p className="font-semibold">{t("afterApproval")}</p>
      ) : null}
    </div>
  );
}
