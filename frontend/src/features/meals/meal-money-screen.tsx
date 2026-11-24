// meal-money-screen.tsx — Hela ya chakula, the day's meal money on the phone of whoever the owner gave its key to
// (WAGE-7, 03 §5.10), as Jack pictured it (24 Nov 2026):
//
//   ←  Hela ya chakula
//   [      Andika hela ya chakula      ]
//   [           Chagua siku            ]
//    ‹          Novemba 2026          ›
//   Jumla hadi leo, 24/11     TSh 24,000
//
//   Jumanne 24/11 (leo)        TSh 9,000
//     Itagawanywa siku ikiisha
//   Jumatatu 23/11             TSh 8,000
//     Watu 8 · TSh 1,000 kila mmoja
//   Jumamosi 21/11          Haijaandikwa
//   Ijumaa 20/11               TSh 7,000
//     Watu 7 · TSh 1,000 kila mmoja
//     1 anasubiri uamuzi
//
// The month: this one, on the shop's clock, unless the address names an earlier one (?month=2026-10), as on Mahudhurio
// ya mwezi, whose switch it wears. Or the days chosen in Chagua siku (choose-days.tsx), kept in the address too
// (?first=…&last=…), in place of the month, until Mwezi mzima:
//
//   20/11/2026 hadi 23/11/2026  [ Mwezi mzima ]
//   Jumla                           TSh 15,000
//
// Andika hela ya chakula types a day's money in a sheet (record-meal-money.tsx). Which days are listed, their sums and each one's share are the server's
// (meal_money_days); the page adds nothing up. Haijaandikwa: a day someone came and nobody typed its money, so a
// forgotten day is easy to see.
//
// An office screen: it asks the server through the store of server answers (rule 5), and needs the internet, which the
// office area says while it is gone. Its routes ask meals.record on the whole shop; someone without it has no button,
// and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Card } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { TextLink } from "@/components/design/text-link";
import { useWordInAddress } from "@/components/tab-in-address";
import {
  isMonth,
  MONTH_PARAM,
  monthOf,
  type Weekday,
} from "@/features/attendance/attendance-month";
import { MonthSwitch, usePagesClock } from "@/features/attendance/month-switch";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";
import {
  formatDay,
  formatDayMonth,
  formatMoney,
  weekdayOf,
} from "@/lib/format";
import { shopToday } from "@/offline/rules";

import { ChooseDaysSheet } from "./choose-days";
import {
  FIRST_PARAM,
  LAST_PARAM,
  mayRecordMeals,
  type MealDay,
  mealDayPage,
  type MealMoneyDays,
  monthSpan,
  type Span,
  spanFrom,
  useMealMoney,
} from "./meal-money";
import { RecordMealMoney } from "./record-meal-money";
import { Split } from "./split";

export function MealMoneyScreen() {
  const t = useTranslations("mealMoney");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const [asked, choose] = useWordInAddress(MONTH_PARAM);
  // The page's clock, as the month page keeps it (month-screen.tsx): the month it opened on, kept until the person
  // moves, and this month, as it is now, which › stops at.
  const { openedAt, now } = usePagesClock();
  const openedOn = who.data
    ? monthOf(shopToday(who.data.shop.timezone, openedAt))
    : null;
  const thisMonth = who.data
    ? monthOf(shopToday(who.data.shop.timezone, now))
    : null;
  // The month the address names, if it is one and not one to come; else the month the page opened on.
  const month =
    openedOn === null || thisMonth === null
      ? null
      : asked !== null && isMonth(asked) && asked <= thisMonth
        ? asked
        : openedOn;
  // The days chosen, if the address names any; in their place, the month's. Both wait for who is here, as nothing is
  // asked for nobody.
  const [firstAsked, chooseFirst] = useWordInAddress(FIRST_PARAM);
  const [lastAsked, chooseLast] = useWordInAddress(LAST_PARAM);
  const chosen = who.data ? spanFrom(firstAsked, lastAsked) : null;
  const span = chosen ?? (month === null ? null : monthSpan(month));
  const keepTo = (next: Span | null) => {
    chooseFirst(next?.first ?? null);
    chooseLast(next?.last ?? null);
  };
  const [choosing, setChoosing] = useState(false);
  // Chagua siku's button: Mwezi mzima goes with the days it clears, so the keyboard goes back to where choosing starts.
  const chooseButton = useRef<HTMLButtonElement>(null);
  const may = who.data !== undefined && mayRecordMeals(who.data);
  const answer = useMealMoney(span);
  // "Subiri kidogo…", through the store's own tries too, and only once there is something to wait for, as on the month
  // page.
  const waiting = who.isPending || (span !== null && answer.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title={t("title")} />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* Only for someone who may see it, so no ‹ › only asks to be refused again (the month page's review). */}
      {/* Today, the shop's, as the server last said it, or the phone's own count until it answers. */}
      {who.data && may ? (
        <RecordMealMoney
          day={answer.data?.today ?? shopToday(who.data.shop.timezone, now)}
          today={answer.data?.today ?? shopToday(who.data.shop.timezone, now)}
        />
      ) : null}
      {may ? (
        <Button
          ref={chooseButton}
          kind="second"
          size="normal"
          onClick={() => setChoosing(true)}
        >
          {t("choose.title")}
        </Button>
      ) : null}
      {may && chosen === null && month !== null && thisMonth !== null ? (
        <MonthSwitch month={month} thisMonth={thisMonth} onChoose={choose} />
      ) : null}
      {may && chosen !== null ? (
        <DaysChosen
          // The days the server counted, never past today, once it has answered.
          span={answer.data ?? chosen}
          onWholeMonth={() => {
            keepTo(null);
            chooseButton.current?.focus();
          }}
        />
      ) : null}
      {who.data && may && choosing && span !== null ? (
        <ChooseDaysSheet
          span={span}
          today={shopToday(who.data.shop.timezone, now)}
          onShow={(next) => {
            keepTo(next);
            setChoosing(false);
          }}
          onClose={() => setChoosing(false)}
          finalFocus={() => chooseButton.current}
        />
      ) : null}
      {/* Asked here alone and handed down, never by the part that shows it (frontend rules). A failed read shows its
          reason; a refresh that fails keeps the days last read, with the reason above them. */}
      <ApiErrorAlert error={answer.error} />
      {answer.data && !answer.isPending ? (
        <TheDays
          answer={answer.data}
          chosen={chosen !== null}
          // This month's total is counted up to today; a month gone by, to its end, and the days chosen, as their
          // heading says. Whether it is this month is the server's to say, from its own today: a phone's can be wrong.
          totalLabel={
            chosen === null && monthOf(answer.data.today) === month
              ? t("totalToToday", { day: formatDayMonth(answer.data.today) })
              : t("total")
          }
        />
      ) : null}
    </div>
  );
}

/** "20/11/2026 hadi 23/11/2026", or the one day, and the way back to the month. */
function DaysChosen({
  span,
  onWholeMonth,
}: {
  span: Span;
  onWholeMonth: () => void;
}) {
  const t = useTranslations("mealMoney");
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      {/* A heading, said as the days change, in the month's place (month-switch.tsx). */}
      <h2 aria-live="polite" className="text-xl font-semibold">
        {span.first === span.last
          ? formatDay(span.first)
          : t("span", {
              first: formatDay(span.first),
              last: formatDay(span.last),
            })}
      </h2>
      <Button kind="second" size="normal" onClick={onWholeMonth}>
        {t("wholeMonth")}
      </Button>
    </div>
  );
}

/** The whole of the days' money, then a line per day. */
function TheDays({
  answer,
  chosen,
  totalLabel,
}: {
  answer: MealMoneyDays;
  /** Whether the days were chosen, or are a month's. */
  chosen: boolean;
  totalLabel: string;
}) {
  const t = useTranslations("mealMoney");
  if (answer.days.length === 0)
    return <p>{t(chosen ? "noneChosen" : "none")}</p>;
  return (
    <>
      <p className="flex flex-wrap justify-between gap-x-4 text-lg font-semibold">
        <span>{totalLabel}</span>
        <span className="tabular-nums">
          {formatMoney(new Decimal(answer.total))}
        </span>
      </p>
      <Card className="py-0">
        {/* A list, so a screen reader says how many days there are. role="list" written out: Safari with VoiceOver stops
            calling a <ul> a list once its bullets are styled away (workers-screen.tsx). */}
        <ul
          role="list"
          aria-label={t(chosen ? "daysChosenLabel" : "daysLabel")}
          className="divide-y divide-border"
        >
          {answer.days.map((day) => (
            <li
              key={day.date}
              // relative: the day's link stretches over its whole line.
              className="relative grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3"
            >
              <DayLine day={day} isToday={day.date === answer.today} />
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

/** "Jumatatu 23/11 … TSh 8,000", then how it is split. */
function DayLine({ day, isToday }: { day: MealDay; isToday: boolean }) {
  const t = useTranslations("mealMoney");
  const monthWords = useTranslations("attendanceMonth");
  const amount = new Decimal(day.amount);
  // "0" as text: the shared Decimal refuses a plain number, so no float ever reaches money (rule 3). Nothing that counts
  // was typed: the day's rows are none, or all crossed out.
  const typed = amount.gt("0");
  return (
    <>
      <p>
        {/* The whole line opens the day's own page, an empty box laid over it (after:absolute), so a finger anywhere on
            it works (flags-screen.tsx). */}
        <TextLink
          href={mealDayPage(day.date)}
          className="after:absolute after:inset-0"
        >
          {t(isToday ? "today" : "day", {
            weekday: monthWords(
              `weekdays.${String(weekdayOf(day.date)) as Weekday}`,
            ),
            date: formatDayMonth(day.date),
          })}
        </TextLink>
      </p>
      <p className="text-right tabular-nums">
        {typed ? formatMoney(amount) : t("notTyped")}
      </p>
      {typed ? <Split day={day} /> : null}
    </>
  );
}
