// advances-screen.tsx — Advansi, the money given to workers before payday, on the phone of whoever may give it (WAGE-8,
// 03 §5.10), as Jack pictured it (25 Nov 2026):
//
//   ←  Advansi
//   [          Andika advansi          ]
//    ‹          Novemba 2026          ›
//   Jumla                     TSh 70,000
//
//   Jumatano 25/11 · Juma         20,000
//   Jumatatu 16/11 · Asha         30,000
//   Jumanne 10/11 · Juma          20,000
//
// The month: this one, on the shop's clock, unless the address names an earlier one (?month=2026-10), as on Mahudhurio
// ya mwezi, whose switch it wears. Newest first, each line opening its own page (advance-page.tsx). One crossed out stays,
// struck through (A2), and the total, which is the server's, leaves it out. What was given comes off that month's pay at
// once (Mishahara). Andika advansi types one in a sheet (record-advance.tsx), for a worker the month's answer names.
//
// An office screen: it asks the server through the store of server answers (rule 5). Its routes ask money.advance on the
// whole shop; someone without it has no button, and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
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
  formatAmount,
  formatDayMonth,
  formatMoney,
  weekdayOf,
} from "@/lib/format";
import { shopToday } from "@/offline/rules";

import {
  type AdvanceLine,
  advancePage,
  type AdvancesMonth,
  mayGiveAdvances,
  useAdvances,
} from "./advances";
import { RecordAdvance } from "./record-advance";

export function AdvancesScreen() {
  const t = useTranslations("advances");
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
  const may = who.data !== undefined && mayGiveAdvances(who.data);
  const answer = useAdvances(month);
  // "Subiri kidogo…", through the store's own tries too, and only once there is something to wait for, as on the month
  // page.
  const waiting = who.isPending || (month !== null && answer.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title={t("title")} />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* On who is here, never on the list's wait (frontend rules): ‹ to a month not read yet takes away neither the button
          nor the line of what was written (the review). Today on its sheet is the server's: a phone's date can be wrong. Not
          on a month whose pay is approved, which takes none (WAGE-3). */}
      {may && answer.data?.closed !== true ? (
        <RecordAdvance month={answer.data} />
      ) : null}
      {/* Only for someone who may see it, so no ‹ › only asks to be refused again (the month page's review). */}
      {may && month !== null && thisMonth !== null ? (
        <MonthSwitch month={month} thisMonth={thisMonth} onChoose={choose} />
      ) : null}
      {/* Asked here alone and handed down, never by the part that shows it (frontend rules). A failed read shows its
          reason; a refresh that fails keeps the month last read, with the reason above it. */}
      <ApiErrorAlert error={answer.error} />
      {answer.data && !answer.isPending ? (
        <TheMonth answer={answer.data} />
      ) : null}
    </div>
  );
}

/** The whole of what was given, then a line each. */
function TheMonth({ answer }: { answer: AdvancesMonth }) {
  const t = useTranslations("advances");
  // The month's pay is approved (WAGE-3), so no button above types one in it: said here, why.
  const closed = answer.closed ? <p>{t("closed")}</p> : null;
  if (answer.rows.length === 0)
    return (
      <>
        {closed}
        <p>{t("none")}</p>
      </>
    );
  return (
    <>
      {closed}
      <p className="flex flex-wrap justify-between gap-x-4 text-lg font-semibold">
        {/* The space between is for a screen reader: side by side with none, it may run the two into one word. */}
        <span>{t("total")}</span>{" "}
        <span className="tabular-nums">
          {formatMoney(new Decimal(answer.total))}
        </span>
      </p>
      <Card className="py-0">
        {/* A list, so a screen reader says how many there are. role="list" written out: Safari with VoiceOver stops
            calling a <ul> a list once its bullets are styled away (workers-screen.tsx). */}
        <ul
          role="list"
          aria-label={t("rowsLabel")}
          className="divide-y divide-border"
        >
          {answer.rows.map((row) => (
            <li
              key={row.id}
              // relative: the line's link stretches over the whole of it.
              className="relative grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3"
            >
              <Line row={row} />
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

/** "Jumatano 25/11 · Juma … 20,000", struck through once crossed out. */
function Line({ row }: { row: AdvanceLine }) {
  const t = useTranslations("advances");
  const monthWords = useTranslations("attendanceMonth");
  const amount = formatAmount(new Decimal(row.amount));
  return (
    <>
      <p>
        {/* The whole line opens its own page, an empty box laid over it (after:absolute), so a finger anywhere on it
            works (meal-money-screen.tsx). */}
        <TextLink
          href={advancePage(row.id)}
          className="after:absolute after:inset-0"
        >
          {t("line", {
            weekday: monthWords(
              `weekdays.${String(weekdayOf(row.date)) as Weekday}`,
            ),
            date: formatDayMonth(row.date),
            name: row.display_name,
          })}
        </TextLink>
      </p>
      {/* <s>, what is no longer right, with the word under it, which a screen reader says too, as it says no strike. */}
      <p className="text-right tabular-nums">
        {row.voided === null ? (
          amount
        ) : (
          <s className="text-muted-foreground">{amount}</s>
        )}
      </p>
      {row.voided === null ? null : (
        <p className="col-span-full text-muted-foreground">{t("voided")}</p>
      )}
    </>
  );
}
