// worker-pay-screen.tsx — one worker's pay of a month, line by line, on the owner's phone (WAGE-2, 03 §5.10), opened from
// their name on Mishahara (pay-screen.tsx): the worker's name as the page's title, the month and how far it is counted,
// and the lines (pay-lines.tsx), as Jack pictured it (25 Nov 2026).
//
// The month is the one the page came from (?month=2026-11), with no ‹ › of its own, as on a worker's attendance: to see
// another, the back arrow returns to Mishahara, on the same month. Opened from a typed address, the arrow goes to
// Mishahara on this worker's month (`fallback`).
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks the two keys of pay
// on the whole shop; someone without both sees the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import {
  isMonth,
  monthOf,
  type MonthNumber,
} from "@/features/attendance/attendance-month";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { shopToday } from "@/offline/rules";

import { payPage, useWorkerPay, type WorkerPayMonth } from "./pay";
import { PayLines } from "./pay-lines";
import { useCountedTo } from "./pay-notes";

export function WorkerPayScreen({
  staff,
  asked,
}: {
  staff: string | null;
  asked: string | null;
}) {
  const t = useTranslations("pay");
  const attendanceWorker = useTranslations("attendanceWorker");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  // The moment the page opened, read once, never while drawing (React's rule; worker-month-screen.tsx).
  const [openedAt] = useState(() => Date.now());
  // The month the address names, as Mishahara wrote it; or, with none, one that is no month, or one to come, this month
  // on the shop's clock, as Mishahara opens it. Once the page knows the shop.
  const thisMonth = who.data
    ? monthOf(shopToday(who.data.shop.timezone, openedAt))
    : null;
  const month =
    thisMonth !== null && asked !== null && isMonth(asked) && asked <= thisMonth
      ? asked
      : thisMonth;
  const answer = useWorkerPay(staff, month);
  // Until both answer, through the store's own tries too; only for a worker the address names.
  const waiting =
    who.isPending || (staff !== null && month !== null && answer.isPending);

  return (
    <div className="grid max-w-2xl gap-6">
      {/* The worker's name as the title once the server says it, as Jack drew it ("← Juma"); until then, what the page
          is. */}
      <PageHeader
        title={answer.data?.worker.display_name ?? t("worker")}
        fallback={payPage(month)}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* An address with no worker names nobody: the page says so, and asks nothing. */}
      {staff === null ? <p>{attendanceWorker("noWorker")}</p> : null}
      {/* Not logged in, no network, the server's own problem; or the pay refused: no key, or a worker the shop doesn't
          have, "not found". Asked here alone and handed down as values (PPL-6). */}
      <ApiErrorAlert error={who.error} />
      <ApiErrorAlert error={answer.error} />
      {answer.data && !answer.isPending ? (
        <TheWorkersPay answer={answer.data} />
      ) : null}
    </div>
  );
}

/** The month and how far it is counted, then the lines; or that the shop doesn't pay them by the day in it. */
function TheWorkersPay({ answer }: { answer: WorkerPayMonth }) {
  const t = useTranslations("pay");
  const monthWords = useTranslations("attendanceMonth");
  const [year, number] = answer.month.split("-") as [string, MonthNumber];
  const month = monthWords("monthTitle", {
    month: monthWords(`monthNames.${number}`),
    year,
  });
  const counted = useCountedTo(answer);
  return (
    <>
      {/* A heading, so a screen reader can jump to it, as the month's is on Mishahara. */}
      <h2 className="text-lg font-semibold">
        {counted === null ? month : t("monthAndCounted", { month, counted })}
      </h2>
      {/* Nothing under the heading when it says no working day has come: whether they are paid by the day isn't known
          yet. */}
      {answer.no_day_yet ? null : (
        <Card>
          <CardContent>
            {answer.paid_by_day ? (
              <PayLines answer={answer} worker={answer.worker} />
            ) : (
              <p>{t("notPaidByDay")}</p>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}
