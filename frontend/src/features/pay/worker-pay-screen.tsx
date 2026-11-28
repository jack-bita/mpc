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
// And once a payslip keeps it, how it was handed out, at its foot (payslip-payments.tsx, WAGE-9): Amelipwa taslimu na
// Baba, with the signature, and Batilisha; or Hajalipwa with Lipa, for whoever may hand out pay (mayPay), never on their
// own. One who left is paid from here the evening they go, once theirs is approved alone.
//
// And Ongeza marekebisho, a mistake of an earlier month put right in this one (correction-sheet.tsx, WAGE-10), for
// whoever approves pay, never on their own, on a month that takes one, as the server says (`no_correction`); each
// correction a line of the pay, with its reason. Of one who left whose pay is approved, the page says why there is none
// (Jack: A). The address's `marekebisho=ongeza` opens the sheet as the page opens, as the flag of a late tap sends Baba
// here, and goes as the sheet closes, so the browser's back never opens it again. A correction's line opens a sheet
// with who typed it and Batilisha, while the month takes one (void-correction.tsx); those crossed out stay under the
// lines, struck through, with who, when and why.
//
// An office screen: it asks the server through the store of server answers (rule 5). Its route asks the two keys of pay
// on the whole shop; someone without both sees the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { type RefObject, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { useWordInAddress } from "@/components/tab-in-address";
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
import { AddCorrection } from "./correction-sheet";
import {
  CORRECTION_PARAM,
  type CorrectionLine,
  correctionsThatCount,
  OPEN_THE_SHEET,
  offersCorrection,
  offersCrossingOut,
} from "./corrections";
import {
  mayApprovePay,
  payPage,
  useWorkerPay,
  type WorkerPayMonth,
} from "./pay";
import { PayLines } from "./pay-lines";
import { PayslipPaper } from "./pay-papers";
import { useCountedTo } from "./pay-notes";
import { mayPay } from "./payments";
import { PayslipPayments } from "./payslip-payments";
import { CrossedOutCorrections, VoidCorrection } from "./void-correction";

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
  // Whether the address asks for Ongeza marekebisho's sheet as the page opens (WAGE-10).
  const [correcting, setCorrecting] = useWordInAddress(CORRECTION_PARAM);
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
          mayPay={mayPay(who.data)}
          title={title}
          openCorrection={correcting === OPEN_THE_SHEET}
          onCorrectionOpened={() => setCorrecting(null)}
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
  mayPay,
  title,
  openCorrection,
  onCorrectionOpened,
}: {
  answer: WorkerPayMonth;
  /** The shop's, for when it was approved. */
  timezone: string;
  mayApprove: boolean;
  /** Whether Lipa and Batilisha are offered: the key of handing out pay, with the two of pay. */
  mayPay: boolean;
  /** The page's title, which stays as the month moves. */
  title: RefObject<HTMLHeadingElement | null>;
  /** Whether the address asked for Ongeza marekebisho's sheet (WAGE-10); and the page takes the word away once it is
   * opened. */
  openCorrection: boolean;
  onCorrectionOpened: () => void;
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
  // The correction whose sheet is open, its line tapped (WAGE-10); and where the keyboard goes once it is crossed out.
  const [voiding, setVoiding] = useState<CorrectionLine | null>(null);
  const crossedOut = useRef<HTMLDivElement>(null);
  const afterVoid = useRef(false);
  const corrects = offersCorrection(answer, mayApprove);
  const crossesOut = offersCrossingOut(answer, mayApprove);
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
              <PayLines
                answer={answer}
                worker={answer.worker}
                corrections={correctionsThatCount(answer)}
                onCorrection={
                  crossesOut
                    ? (line) => {
                        afterVoid.current = false;
                        setVoiding(line);
                      }
                    : undefined
                }
              />
            ) : (
              <p>{t("notPaidByDay")}</p>
            )}
          </CardContent>
        </Card>
      )}
      <CrossedOutCorrections
        corrections={answer.corrections}
        timezone={timezone}
        place={crossedOut}
      />
      {/* Mounted only while open, so each opening makes its own request. */}
      {voiding !== null ? (
        <VoidCorrection
          line={voiding}
          name={answer.worker.display_name}
          month={answer.month}
          timezone={timezone}
          readyReasons={answer.correction_void_reasons}
          onDone={() => {
            afterVoid.current = true;
            setVoiding(null);
          }}
          onClose={() => setVoiding(null)}
          // Once crossed out, the list it moved to; else the page's title, as the line's button may be gone.
          finalFocus={() =>
            afterVoid.current
              ? (crossedOut.current ?? title.current)
              : title.current
          }
        />
      ) : null}
      {/* Ongeza marekebisho, for whoever approves pay, on a month that takes one (WAGE-10); of one who left and was paid,
          why there is none (Jack: A). */}
      {corrects ? (
        <AddCorrection
          answer={answer}
          month={month}
          openAtStart={openCorrection}
          onOpened={onCorrectionOpened}
        />
      ) : mayApprove && answer.no_correction === "correction.left_paid" ? (
        <p>{t("correction.leftPaid", { name: answer.worker.display_name })}</p>
      ) : null}
      {/* Once a payslip keeps it: how it was handed out, or Lipa (WAGE-9). */}
      <PayslipPayments
        worker={answer.worker}
        month={answer.month}
        timezone={timezone}
        mayPay={mayPay}
        keepsSignatures={answer.keeps_signatures}
        readyReasons={answer.void_reasons}
      />
      {/* Once a payslip keeps it: their payslip on paper (WAGE-5). */}
      <PayslipPaper worker={answer.worker} month={answer.month} />
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
