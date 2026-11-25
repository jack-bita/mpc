// pay-screen.tsx — Mishahara, the month's pay of everyone the shop pays by the day, on the owner's phone (WAGE-2,
// 03 §5.10), as Jack pictured it (25 Nov 2026):
//
//   ←  Mishahara
//    ‹          Novemba 2026          ›
//   Hadi jana, Jumanne 24/11
//
//   Jumla ya wote          TSh 492,000
//   Asha                       152,000
//   Baraka                     148,000
//   Juma                       132,000
//     ! Siku 1 inasubiri uamuzi
//   Neema                       60,000
//     Aliondoka 14/11/2026
//
// The month: this one, on the shop's clock, unless the address names an earlier one (?month=2026-10), as on Mahudhurio
// ya mwezi, whose switch it wears: on 2 December Baba still sees the whole of November. A name opens that worker's pay,
// line by line (worker-pay-screen.tsx). A worker's total counts the days that are over, and today once they tapped Toka:
// Pamoja na leo (Jack: A). Which workers are listed, each total and the whole are the server's (pay_month); the page adds
// nothing up. What isn't paid is said under the name, with the ! that marks a day to decide on the attendance pages: days
// that wait for a decision, and days with no daily pay.
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks the two keys of pay
// on the whole shop; someone without both has no button, and opening the address shows the server's refusal.
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
} from "@/features/attendance/attendance-month";
import { MonthSwitch, usePagesClock } from "@/features/attendance/month-switch";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { maySeePay } from "@/features/workers/pay-rates";
import { Decimal } from "@/lib/decimal";
import { formatAmount, formatMoney } from "@/lib/format";
import { shopToday } from "@/offline/rules";

import { type PayMonth, usePayMonth, workerPayPage } from "./pay";
import { PayNotes, useCountedTo } from "./pay-notes";

export function PayScreen() {
  const t = useTranslations("pay");
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
  const may = who.data !== undefined && maySeePay(who.data);
  const answer = usePayMonth(month);
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

/** How far the month is counted, the whole of it, then a line per worker. */
function TheMonth({ answer }: { answer: PayMonth }) {
  const t = useTranslations("pay");
  const counted = useCountedTo(answer);
  return (
    <>
      {counted === null ? null : <p>{counted}</p>}
      {answer.workers.length === 0 ? (
        // Nobody paid by the day; or no working day yet, which the line above says, and is all the page knows: on a
        // Sunday the 1st, ten workers with a rate are listed nowhere (the review, as on the attendance month).
        answer.no_day_yet ? null : (
          <p>{t("nobody")}</p>
        )
      ) : (
        <>
          <p className="flex flex-wrap justify-between gap-x-4 text-lg font-semibold">
            {/* The space between is for a screen reader: side by side with none, it may run the two into one word. */}
            <span>{t("totalOfAll")}</span>{" "}
            <span className="tabular-nums">
              {formatMoney(new Decimal(answer.total))}
            </span>
          </p>
          <Card className="py-0">
            {/* A list, so a screen reader says how many workers there are. role="list" written out: Safari with
                VoiceOver stops calling a <ul> a list once its bullets are styled away (workers-screen.tsx). */}
            <ul
              role="list"
              aria-label={t("workersLabel")}
              className="divide-y divide-border"
            >
              {answer.workers.map((worker) => (
                // Keyed by the job: a person hired again in the month has a line for each (PPL-11).
                <li
                  key={worker.staff}
                  // relative: the name's link stretches over its whole line.
                  className="relative grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3"
                >
                  <p>
                    {/* The whole line opens the worker's own pay, the same month, an empty box laid over it
                        (after:absolute), so a finger anywhere on it works (meal-money-screen.tsx). */}
                    <TextLink
                      href={workerPayPage(worker.staff, answer.month)}
                      className="after:absolute after:inset-0"
                    >
                      {worker.display_name}
                    </TextLink>
                  </p>
                  <p className="text-right tabular-nums">
                    {formatAmount(new Decimal(worker.total))}
                  </p>
                  <PayNotes worker={worker} />
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </>
  );
}
