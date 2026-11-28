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
// Once a month is over, whoever may approve it (mayApprovePay) finds Idhinisha at its foot, which opens a sheet
// (approve-month.tsx); and once it is approved, the page says who did and when, and shows the payslips as they were kept
// (WAGE-3, as Jack pictured it):
//
//    ‹          Novemba 2026          ›
//   Imeidhinishwa na Baba · 1/12/2026 19:05 usiku
//
//   Jumla ya wote          TSh 432,000
//   …
//
// One who left and was approved alone says so under their name while the month is still open: Imeidhinishwa 14/11/2026.
//
// Once a payslip keeps a line, the line says whether it is handed out (WAGE-9), as Jack pictured it (26 Nov 2026), and
// the month what cash is still to hand out:
//
//   Jumla ya wote          TSh 432,000
//   Bado kulipa            TSh 280,000      (Wote wamelipwa, once each is)
//   Asha                       152,000
//     Amelipwa 2/12/2026
//   Baraka                     148,000
//     Hajalipwa               [ Lipa ]
//
// Lipa is on the line itself, for whoever may hand out pay (mayPay), never on their own; it opens the Lipa sheet
// (pay-sheet.tsx). A payslip that pays nothing has neither, as there is nothing to hand over.
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks the two keys of pay
// on the whole shop; someone without both has no button, and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { type RefObject, useRef, useState } from "react";
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
} from "@/features/attendance/attendance-month";
import { MonthSwitch, usePagesClock } from "@/features/attendance/month-switch";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { maySeePay } from "@/features/workers/pay-rates";
import { Decimal } from "@/lib/decimal";
import { formatAmount, formatDate, formatMoney } from "@/lib/format";
import { shopToday } from "@/offline/rules";

import { ApproveMonth } from "./approve-month";
import { useMonthTitle } from "./approve-sheet";
import { ApprovedLine } from "./approved-line";
import {
  mayApprovePay,
  type PayMonth,
  usePayMonth,
  type WorkerPay,
  workerPayPage,
} from "./pay";
import { PayNotes, useCountedTo } from "./pay-notes";
import { MonthPapers } from "./pay-papers";
import { PaySheet } from "./pay-sheet";
import { PaymentNote } from "./payment-note";
import { mayPay } from "./payments";

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
  // The page's title, which the keyboard goes to when a sheet moves the page to another month.
  const title = useRef<HTMLHeadingElement>(null);
  // "Subiri kidogo…", through the store's own tries too, and only once there is something to wait for, as on the month
  // page.
  const waiting = who.isPending || (month !== null && answer.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title={t("title")} headingRef={title} />
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
      {who.data && answer.data && !answer.isPending ? (
        <TheMonth
          // A month of its own: on another's, as ‹ › or the browser's back move the address, an open sheet closes, so
          // November is never approved from October's page.
          key={answer.data.month}
          answer={answer.data}
          timezone={who.data.shop.timezone}
          mayApprove={mayApprovePay(who.data)}
          mayPay={mayPay(who.data)}
          onMonth={choose}
          title={title}
        />
      ) : null}
    </div>
  );
}

/** How far the month is counted, or who approved it; the whole of it; a line per worker; and Idhinisha. */
function TheMonth({
  answer,
  timezone,
  mayApprove,
  mayPay,
  onMonth,
  title,
}: {
  answer: PayMonth;
  /** The shop's, for when it was approved. */
  timezone: string;
  mayApprove: boolean;
  /** Whether Lipa is offered: the key of handing out pay, with the two of pay. */
  mayPay: boolean;
  /** Move the page to another month, as ‹ › do. */
  onMonth: (month: string) => void;
  /** The page's title, which stays as the month moves. */
  title: RefObject<HTMLHeadingElement | null>;
}) {
  const t = useTranslations("pay");
  const counted = useCountedTo(answer);
  const monthTitle = useMonthTitle();
  const [approving, setApproving] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const line = useRef<HTMLDivElement>(null);
  // Whether the last close was an approval, when the button is gone: read as the sheet goes, after the draw that took it
  // away, so a ref, not the state (worker-pay.tsx).
  const afterApproval = useRef(false);
  // Whether the sheet moved the page to another month, when all of this one's is gone.
  const moved = useRef(false);
  // The worker whose Lipa sheet is open, or null; and, once paid, where the keyboard goes: their line's Amelipwa.
  const [paying, setPaying] = useState<WorkerPay | null>(null);
  const afterPayment = useRef(false);
  const paidLines = useRef(new Map<string, HTMLElement>());
  return (
    <>
      {counted === null ? null : <p>{counted}</p>}
      {/* Always on the page, empty and hidden until it is approved: the keyboard goes to it as the sheet closes, which may
          be a moment before the page has drawn the line in it. */}
      <div
        ref={line}
        tabIndex={-1}
        className={answer.approval === null ? "sr-only" : "outline-none"}
      >
        {answer.approval === null ? null : (
          <ApprovedLine approval={answer.approval} timezone={timezone} />
        )}
      </div>
      {/* Once approved: the month's sheet, its payslips and its Excel file (WAGE-5). */}
      {answer.approval === null ? null : (
        <MonthPapers
          answer={answer}
          approval={answer.approval}
          timezone={timezone}
        />
      )}
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
          {/* Once approved: the cash still to hand out, and once each is paid, that everyone is (WAGE-9). */}
          {answer.still_to_pay === null ? null : new Decimal(
              answer.still_to_pay,
            ).gt("0") ? (
            <p className="flex flex-wrap justify-between gap-x-4 text-lg font-semibold">
              <span>{t("payment.stillToPay")}</span>{" "}
              <span className="tabular-nums">
                {formatMoney(new Decimal(answer.still_to_pay))}
              </span>
            </p>
          ) : (
            <p className="text-lg font-semibold">{t("payment.allPaid")}</p>
          )}
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
                  <PayNotes
                    worker={worker}
                    approvedOn={
                      answer.approval === null && worker.approval !== null
                        ? formatDate(worker.approval.at, timezone)
                        : null
                    }
                  />
                  <PaymentNote
                    worker={worker}
                    timezone={timezone}
                    mayPay={mayPay}
                    onPay={() => {
                      afterPayment.current = false;
                      setPaying(worker);
                    }}
                    lineRef={(element) => {
                      if (element === null)
                        paidLines.current.delete(worker.staff);
                      else paidLines.current.set(worker.staff, element);
                    }}
                  />
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
      {/* At the foot, under the totals it closes: only once the month is over and open, as the server says
          (to_approve), and only for whoever may. */}
      {mayApprove && answer.to_approve !== null ? (
        <Button
          ref={button}
          onClick={() => {
            afterApproval.current = false;
            setApproving(true);
          }}
        >
          {t("approval.monthButton", { month: monthTitle(answer.month) })}
        </Button>
      ) : null}
      {/* Mounted only while open, so each opening makes its own payment (its ids). Once paid, the keyboard goes to the
          line's Amelipwa, as its Lipa is gone; else back to the Lipa that opened it. */}
      {paying === null ? null : (
        <PaySheet
          worker={paying}
          month={answer.month}
          keepsSignatures={answer.keeps_signatures}
          onDone={() => {
            afterPayment.current = true;
            setPaying(null);
          }}
          onClose={() => setPaying(null)}
          finalFocus={() =>
            afterPayment.current
              ? (paidLines.current.get(paying.staff) ?? null)
              : null
          }
        />
      )}
      {/* Mounted only while open, so each opening makes its own request (its id). It stays until it is done, though the
          page has learned meanwhile that the month is approved and its button is gone. */}
      {approving ? (
        <ApproveMonth
          answer={answer}
          timezone={timezone}
          onEarlier={(earlier) => {
            moved.current = true;
            onMonth(earlier);
          }}
          onDone={() => {
            afterApproval.current = true;
            setApproving(false);
          }}
          onClose={() => setApproving(false)}
          // Or the line, when the button went while the sheet was open: approved, its answer lost.
          finalFocus={() =>
            moved.current
              ? title.current
              : afterApproval.current
                ? line.current
                : (button.current ?? line.current)
          }
        />
      ) : null}
    </>
  );
}
