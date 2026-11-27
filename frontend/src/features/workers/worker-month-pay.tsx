// worker-month-pay.tsx — Malipo ya mwezi on a worker's page (WAGE-2): the month's pay so far, line by line, so the owner
// pays a worker who leaves from their own page, with no sum of his own, as Jack pictured it (19 and 25 Nov 2026):
//
//    Malipo ya mwezi
//    ‹        Novemba 2026        ›
//    Hadi jana, Jumanne 24/11
//    Siku kamili   14 × 10,000   140,000
//    …
//    Jumla ya kumlipa leo    TSh 132,000
//
// Under Malipo kwa siku, for whoever may see pay (maySeePay, pay-rates.ts): the page asks the pay for them alone, and
// hands the read down (worker-page.tsx). The same lines as the worker's page off Mishahara (pay-lines.tsx), from the same
// answer. ‹ › moves the month, this one at first, and › stops at it; a month is kept by the page, not the address, which
// names the worker alone.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useId } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card, CardContent } from "@/components/design/card";
import { MonthSwitch } from "@/features/attendance/month-switch";
import { ApprovedLine } from "@/features/pay/approved-line";
import { correctionsThatCount } from "@/features/pay/corrections";
import type { WorkerPayMonth } from "@/features/pay/pay";
import { PayLines } from "@/features/pay/pay-lines";
import { useCountedTo } from "@/features/pay/pay-notes";

import { CardHeading } from "./card-heading";

export function WorkerMonthPay({
  month,
  thisMonth,
  onChoose,
  timezone,
  read,
}: {
  /** The month shown, and this month, which › stops at. */
  month: string;
  thisMonth: string;
  onChoose: (month: string) => void;
  /** The shop's, for when the pay was approved. */
  timezone: string;
  /** The pay of that month, read by the page, the part always on it, and handed down by its values (RolesRead,
   * workers.ts). */
  read: {
    data: WorkerPayMonth | undefined;
    error: unknown;
    isPending: boolean;
  };
}) {
  const t = useTranslations("pay");
  const loginWords = useTranslations("login");
  const titleId = useId();

  return (
    <Card>
      <CardContent>
        <section aria-labelledby={titleId} className="grid gap-4">
          <CardHeading id={titleId} title={t("cardTitle")} />
          <MonthSwitch
            month={month}
            thisMonth={thisMonth}
            onChoose={onChoose}
            heading="h3"
          />
          {/* Until each month's first answer, through the store's own tries too (worker-page.tsx). */}
          {read.isPending ? <p role="status">{loginWords("waiting")}</p> : null}
          {/* A failed read keeps the pay last read, with the reason above it. */}
          <ApiErrorAlert error={read.error} />
          {read.data ? <ThePay answer={read.data} timezone={timezone} /> : null}
        </section>
      </CardContent>
    </Card>
  );
}

/** How far the month is counted, or who approved it (WAGE-3), and the lines; or that the shop doesn't pay them by the day
 * in it. Approving is their own pay page's, off Mishahara. */
function ThePay({
  answer,
  timezone,
}: {
  answer: WorkerPayMonth;
  timezone: string;
}) {
  const t = useTranslations("pay");
  const counted = useCountedTo(answer);
  const { approval } = answer.worker;
  return (
    <>
      {approval !== null ? (
        <ApprovedLine approval={approval} timezone={timezone} />
      ) : counted === null ? null : (
        <p>{counted}</p>
      )}
      {/* Their line whenever there is one: money given on a 1st that is a Sunday is one, before any working day (WAGE-8).
          With none, nothing more when the line above says no working day has come: whether they are paid by the day isn't
          known yet. */}
      {answer.paid_by_day ? (
        <PayLines
          answer={answer}
          worker={answer.worker}
          corrections={correctionsThatCount(answer)}
        />
      ) : answer.no_day_yet ? null : (
        <p>{t("notPaidByDay")}</p>
      )}
    </>
  );
}
