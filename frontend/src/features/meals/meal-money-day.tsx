// meal-money-day.tsx — one day's own page, opened from its line on Hela ya chakula (WAGE-7, 03 §5.10), as Jack pictured
// it (24 Nov 2026):
//
//   ←  Jumatatu 23/11/2026
//   Jumla TSh 8,000
//   Watu 8 · TSh 1,000 kila mmoja
//
//   TSh 5,000 · Unga na maharage
//   Asha · 23/11/2026 08:10 asubuhi
//   [ Batilisha ]
//
//   ~~TSh 30,000 · Nyama~~
//   Asha · 23/11/2026 11:20 asubuhi
//   Imebatilishwa na Baba, 23/11/2026
//   Sababu: Sifuri moja zaidi
//
//   [ Andika hela ya chakula ]
//
// At /meal-money/day/?date=…, as the app has no [id] pages (ADR-0016): the page around it reads the day from the address.
// The day alone is asked for, from the list's own route, so its sums and split are the server's. A row crossed out stays,
// struck through, with who, when and why (A2); Batilisha, under a row that counts, opens its sheet (void-meal-money.tsx).
// Andika hela ya chakula starts on the day itself: not on a Sunday, or a day to come, which the server would refuse.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Card } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import type { Weekday } from "@/features/attendance/attendance-month";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";
import {
  dayPart,
  formatDate,
  formatDay,
  formatMoney,
  formatTime,
  weekdayOf,
} from "@/lib/format";

import {
  isDay,
  isForgotten,
  isTyped,
  MEAL_MONEY_PAGE,
  type MealMoneyDays,
  type MealMoneyLine,
  useMealMoney,
} from "./meal-money";
import { RecordMealMoney } from "./record-meal-money";
import { Split } from "./split";
import { VoidMealMoney } from "./void-meal-money";

/** Sunday, as JavaScript numbers the days of the week. */
const SUNDAY = 0;

export function MealMoneyDayScreen({ date }: { date: string | null }) {
  const t = useTranslations("mealMoney");
  const monthWords = useTranslations("attendanceMonth");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  // A day the address can't mean is none: asked for, it would only show the server's refusal.
  const day = date !== null && isDay(date) ? date : null;
  const answer = useMealMoney(
    who.data && day !== null ? { first: day, last: day } : null,
  );
  const waiting =
    who.isPending ||
    (who.data !== undefined && day !== null && answer.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader
        title={
          day === null
            ? t("title")
            : t("day", {
                weekday: monthWords(
                  `weekdays.${String(weekdayOf(day)) as Weekday}`,
                ),
                date: formatDay(day),
              })
        }
        fallback={MEAL_MONEY_PAGE}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {day === null ? <p>{t("dayPage.noDay")}</p> : null}
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* A failed read above the day, not in its place: a refresh that fails keeps the day last read. */}
      <ApiErrorAlert error={answer.error} />
      {who.data && day !== null && answer.data && !answer.isPending ? (
        <TheDay
          date={day}
          answer={answer.data}
          timezone={who.data.shop.timezone}
        />
      ) : null}
    </div>
  );
}

function TheDay({
  date,
  answer,
  timezone,
}: {
  date: string;
  answer: MealMoneyDays;
  timezone: string;
}) {
  const t = useTranslations("mealMoney");
  // The day, or none: a Sunday, or a day nobody came and nobody typed, isn't answered (meal_money_days).
  const day = answer.days[0];
  const rows = day?.rows ?? [];
  return (
    <>
      <div className="grid gap-1">
        {day !== undefined && isTyped(day) ? (
          <>
            <p className="text-lg font-semibold tabular-nums">
              {t("dayPage.total", {
                amount: formatMoney(new Decimal(day.amount)),
              })}
            </p>
            <Split day={day} />
          </>
        ) : (
          // Forgotten, or a day with none to write: a Sunday, one to come, or one nobody came.
          <p className="text-lg font-semibold">
            {day !== undefined && isForgotten(day)
              ? t("notTyped")
              : t("dayPage.none")}
          </p>
        )}
      </div>
      {rows.length === 0 ? null : (
        <Card className="py-0">
          {/* Oldest first, as the server sends them. role="list" written out: Safari with VoiceOver stops calling a <ul>
              a list once its bullets are styled away (workers-screen.tsx). */}
          <ul
            role="list"
            aria-label={t("dayPage.rowsLabel")}
            className="divide-y divide-border"
          >
            {rows.map((row) => (
              <li key={row.id} className="grid gap-1 px-4 py-3">
                <Row
                  row={row}
                  readyReasons={answer.ready_void_reasons}
                  timezone={timezone}
                />
              </li>
            ))}
          </ul>
        </Card>
      )}
      {/* Days as text sort as days do. */}
      {date <= answer.today && weekdayOf(date) !== SUNDAY ? (
        <RecordMealMoney day={date} today={answer.today} />
      ) : null}
    </>
  );
}

/** One row: what it bought, who typed it and when, and Batilisha, or who crossed it out, when and why. */
function Row({
  row,
  readyReasons,
  timezone,
}: {
  row: MealMoneyLine;
  readyReasons: MealMoneyDays["ready_void_reasons"];
  timezone: string;
}) {
  const t = useTranslations("mealMoney");
  const attendance = useTranslations("attendance");
  const [crossing, setCrossing] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const line = useRef<HTMLParagraphElement>(null);
  // Whether the last close was a crossing out, when the button is gone: the keyboard then goes to the row itself. Read as
  // the sheet goes, after the draw that took it away, so a ref, not the state (worker-pay.tsx).
  const afterVoid = useRef(false);
  const amount = formatMoney(new Decimal(row.amount));
  const said =
    row.note === ""
      ? amount
      : t("dayPage.rowWithNote", { amount, note: row.note });
  const ready = readyReasons.find((code) => code === row.voided?.reason);
  return (
    <>
      {/* Struck through once crossed out (<s>, what is no longer right), with who, when and why under it, which a screen
          reader says too, as it says no strike. */}
      <p
        ref={line}
        tabIndex={-1}
        className={
          row.voided === null
            ? "font-semibold outline-none"
            : "text-muted-foreground outline-none"
        }
      >
        {row.voided === null ? said : <s>{said}</s>}
      </p>
      <p className="text-muted-foreground">
        {t("dayPage.typedBy", {
          by: row.by,
          date: formatDate(row.at, timezone),
          time: attendance("timeOfDay", {
            time: formatTime(row.at, timezone),
            part: dayPart(row.at, timezone),
          }),
        })}
      </p>
      {row.voided === null ? (
        <Button
          ref={button}
          kind="second"
          size="normal"
          className="justify-self-start"
          // By its amount too, as a day has several rows, each with a Batilisha; its visible word first (WCAG 2.5.3).
          aria-label={t("void.title", { amount })}
          onClick={() => {
            afterVoid.current = false;
            setCrossing(true);
          }}
        >
          {t("void.action")}
        </Button>
      ) : (
        <>
          <p>
            {t("dayPage.voidedBy", {
              by: row.voided.by,
              date: formatDate(row.voided.at, timezone),
            })}
          </p>
          {/* On the demo a ready reason's code, said in words; elsewhere the words typed. */}
          <p>
            {t("dayPage.reason", {
              reason:
                ready === undefined
                  ? row.voided.reason
                  : t(`readyReason.${ready}`),
            })}
          </p>
        </>
      )}
      {/* Mounted only while open, so a sheet closed with Ghairi forgets what was typed. */}
      {crossing ? (
        <VoidMealMoney
          row={row}
          readyReasons={readyReasons}
          onDone={() => {
            afterVoid.current = true;
            setCrossing(false);
          }}
          onClose={() => setCrossing(false)}
          finalFocus={() => (afterVoid.current ? line.current : button.current)}
        />
      ) : null}
    </>
  );
}
