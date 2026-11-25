// worker-pay-screen.tsx — one worker's pay of a month, line by line, on the owner's phone (WAGE-2, 03 §5.10), opened from
// their name on Mishahara (pay-screen.tsx): the worker's name as the page's title, the month and how far it is counted,
// and the lines (pay-lines.tsx), as Jack pictured it (25 Nov 2026).
//
// The month is the one the page came from (?month=2026-11), with no ‹ › of its own, as on a worker's attendance: to see
// another, the back arrow returns to Mishahara, on the same month. Opened from a typed address, the arrow goes to
// Mishahara on this worker's month (`fallback`).
//
// Once a payslip keeps it, approved with the month or alone, the page says by whom and when, and these are its lines
// (WAGE-3). And of one who left, with pay still open, whoever may approve it (mayApprovePay) finds Idhinisha malipo ya
// Neema under the lines, which opens a sheet (approve-leaver.tsx), as Jack pictured it (25 Nov 2026).
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks the two keys of pay
// on the whole shop; someone without both sees the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { type RefObject, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import {
  isMonth,
  monthOf,
  type MonthNumber,
} from "@/features/attendance/attendance-month";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { shopToday } from "@/offline/rules";

import { ApproveLeaver } from "./approve-leaver";
import { ApprovedLine } from "./approved-line";
import {
  mayApprovePay,
  payPage,
  useWorkerPay,
  type WorkerPayMonth,
} from "./pay";
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
  // The page's title, which the keyboard goes to when a sheet's link moved the page to another month.
  const title = useRef<HTMLHeadingElement>(null);
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
        headingRef={title}
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
      {who.data && answer.data && !answer.isPending ? (
        <TheWorkersPay
          // A worker's month of its own: on another, as a link or the browser's back moves the address, an open sheet
          // closes, so Neema's November is never approved from Juma's page.
          key={`${answer.data.worker.staff} ${answer.data.month}`}
          answer={answer.data}
          timezone={who.data.shop.timezone}
          mayApprove={mayApprovePay(who.data)}
          title={title}
        />
      ) : null}
    </div>
  );
}

/** The month and how far it is counted, or who approved it, then the lines; or that the shop doesn't pay them by the day
 * in it; and Idhinisha, of one who left. */
function TheWorkersPay({
  answer,
  timezone,
  mayApprove,
  title,
}: {
  answer: WorkerPayMonth;
  /** The shop's, for when it was approved. */
  timezone: string;
  mayApprove: boolean;
  /** The page's title, which stays as the month moves. */
  title: RefObject<HTMLHeadingElement | null>;
}) {
  const t = useTranslations("pay");
  const monthWords = useTranslations("attendanceMonth");
  const [year, number] = answer.month.split("-") as [string, MonthNumber];
  const month = monthWords("monthTitle", {
    month: monthWords(`monthNames.${number}`),
    year,
  });
  const counted = useCountedTo(answer);
  const [approving, setApproving] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const line = useRef<HTMLDivElement>(null);
  // Whether the last close was an approval, when the button is gone: read as the sheet goes, after the draw that took it
  // away, so a ref, not the state (worker-pay.tsx).
  const afterApproval = useRef(false);
  const { approval } = answer.worker;
  return (
    <>
      {/* A heading, so a screen reader can jump to it, as the month's is on Mishahara. */}
      <h2 className="text-lg font-semibold">
        {counted === null || approval !== null
          ? month
          : t("monthAndCounted", { month, counted })}
      </h2>
      {/* Always on the page, empty and hidden until it is approved: the keyboard goes to it as the sheet closes, which may
          be a moment before the page has drawn the line in it (pay-screen.tsx). */}
      <div
        ref={line}
        tabIndex={-1}
        className={approval === null ? "sr-only" : "outline-none"}
      >
        {approval === null ? null : (
          <ApprovedLine approval={approval} timezone={timezone} />
        )}
      </div>
      {/* Their line whenever there is one: money given on a 1st that is a Sunday is one, before any working day (WAGE-8).
          With none, nothing under a heading that says no working day has come: whether they are paid by the day isn't
          known yet. */}
      {!answer.paid_by_day && answer.no_day_yet ? null : (
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
      {/* Only of one who left, with pay still open, as the server says (to_approve), and only for whoever may. */}
      {mayApprove && answer.to_approve !== null ? (
        <Button
          ref={button}
          onClick={() => {
            afterApproval.current = false;
            setApproving(true);
          }}
        >
          {t("approval.leaverTitle", { name: answer.worker.display_name })}
        </Button>
      ) : null}
      {/* Mounted only while open, so each opening makes its own request (its id). */}
      {approving ? (
        <ApproveLeaver
          answer={answer}
          timezone={timezone}
          onDone={() => {
            afterApproval.current = true;
            setApproving(false);
          }}
          onClose={() => setApproving(false)}
          // The line once approved; the button that opened it; or, when both went with their month, the title.
          finalFocus={() =>
            afterApproval.current
              ? line.current
              : (button.current ?? line.current ?? title.current)
          }
        />
      ) : null}
    </>
  );
}
