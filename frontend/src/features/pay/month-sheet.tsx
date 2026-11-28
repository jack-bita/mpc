// month-sheet.tsx — the month's sheet (WAGE-5): every payment of an approved month on one A4 page, each with its proof,
// for NSSF and the owner's file, as Jack pictured it (28 Nov 2026):
//
//   MPC · Mabatini Pumba Center
//   Mishahara ya Novemba 2026
//   Imeidhinishwa na Baba · 01/12/2026 09:00 asubuhi
//
//   Na. Jina    Kiasi    Tarehe      Njia                 Sahihi          Sahihi kwa kalamu
//   1   Asha    152,000  02/12/2026  Taslimu              (her drawing)   ______________
//   2   Baraka  117,000  02/12/2026  M-Pesa QJK7A2B9XC    —               ______________
//   3   Juma    163,000  03/12/2026  Taslimu              (his drawing)   ______________
//   4   Neema         0  —           Hakulipwa: deni 18,000  —            ______________
//
//   Jumla ya wote: TSh 432,000
//   Sahihi ya aliyelipa: ______________      Tarehe: ____________
//
// One not paid yet says Hajalipwa, their signature's box empty, as is their pen's. Only the payment that counts shows:
// one crossed out (WAGE-9) proves nothing, and the payslip's own page keeps it, struck through. On the demo no signature
// is kept (WAGE-9), so its box says so. The pen's space is there for every row: the owner may ask each worker to sign
// the paper too, as they sign on paper today.
//
// Only an approved month: an open one is a draft whose numbers may still change, and has no payment to show. Read from
// Mishahara's own answer (GET pay/?month=…), which holds every name, amount, payment and signature (rule 5: an office
// page asks the server, through the store of server answers); the page adds nothing up, as every amount is the server's.
// Behind the two keys of pay, as Mishahara is: the server refuses anyone else, and the page shows its refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import Image from "next/image";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { isMonth } from "@/features/attendance/attendance-month";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";
import { formatAmount, formatDate, formatMoney } from "@/lib/format";
import { photoAddress } from "@/lib/photo-address";

import { useMonthTitle } from "./approve-sheet";
import { ApprovedLine } from "./approved-line";
import { Paper, PaperHeading, PaperSheet } from "./paper";
import {
  type Approval,
  type PayMonth,
  payPage,
  usePayMonth,
  type WorkerPay,
} from "./pay";
import { paymentOf } from "./payments";

export function MonthSheetScreen({ asked }: { asked: string | null }) {
  const t = useTranslations("pay.sheet");
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  // The month the address names; anything else names none, and nothing is asked.
  const month = asked !== null && isMonth(asked) ? asked : null;
  const answer = usePayMonth(month);
  const waiting = who.isPending || (month !== null && answer.isPending);
  // The arrow goes back to Mishahara on the same month, when the page before isn't the app's own.
  const fallback = payPage(month);
  // Shown once the server says the month is approved, and who did it.
  const approval =
    answer.data && !answer.isPending ? answer.data.approval : null;

  return (
    <Paper title={t("title")} fallback={fallback}>
      {/* The screen's own lines, never on paper: the wait, a refusal, and why there is nothing to print. */}
      <div className="grid gap-4 print:hidden">
        <p role="status" className={waiting ? "text-lg" : "sr-only"}>
          {waiting ? loginWords("waiting") : null}
        </p>
        <ApiErrorAlert error={who.error} />
        <ApiErrorAlert error={answer.error} />
        {month === null || (answer.data && answer.data.approval === null) ? (
          <p>{t("notApproved")}</p>
        ) : null}
      </div>
      {who.data && answer.data && approval !== null ? (
        <TheSheet
          answer={answer.data}
          approval={approval}
          shop={who.data.shop}
        />
      ) : null}
    </Paper>
  );
}

/** The sheet itself, of a month the server says is approved. */
function TheSheet({
  answer,
  approval,
  shop,
}: {
  answer: PayMonth;
  /** Who approved it and when: the sheet is only ever of an approved month. */
  approval: Approval;
  /** The shop's code and name for the top, and its zone, for each day and time. */
  shop: { code: string; name: string; timezone: string };
}) {
  const t = useTranslations("pay.sheet");
  const monthTitle = useMonthTitle();
  // Each column's heading, in the order Jack drew them; the pen's last, as it is filled last, by hand.
  const columns = [
    t("number"),
    t("name"),
    t("amount"),
    t("date"),
    t("way"),
    t("signature"),
    t("byPen"),
  ];
  return (
    <PaperSheet>
      <div className="grid gap-4">
        <div className="grid gap-1">
          <PaperHeading
            shop={shop}
            title={t("heading", { month: monthTitle(answer.month) })}
          />
          <ApprovedLine approval={approval} timezone={shop.timezone} />
        </div>
        {/* Wider than a phone: on the screen it scrolls sideways, on paper it fits the A4 page. */}
        <div className="overflow-x-auto print:overflow-visible">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {columns.map((heading) => (
                  <th
                    key={heading}
                    scope="col"
                    className="border border-foreground px-2 py-1 text-left font-semibold"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.workers.map((worker, index) => (
                // Keyed by the job: one hired again in the month has a row for each (PPL-11). A row never splits over
                // two pages, so a signature is never cut in half (break-inside-avoid).
                <SheetRow
                  key={worker.staff}
                  number={index + 1}
                  worker={worker}
                  timezone={shop.timezone}
                />
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-lg font-semibold">
          {t("total", { total: formatMoney(new Decimal(answer.total)) })}
        </p>
        {/* For whoever hands the paper in: their own signature, by pen, and the day, each on a line drawn for it (an
            empty box with a bottom edge), as a form on paper has. */}
        <p className="flex flex-wrap items-end gap-x-12 gap-y-6 pt-8">
          <span className="flex items-end gap-2">
            {t("signedBy")}
            <span className="inline-block w-56 border-b border-foreground" />
          </span>
          <span className="flex items-end gap-2">
            {t("signedOn")}
            <span className="inline-block w-32 border-b border-foreground" />
          </span>
        </p>
      </div>
    </PaperSheet>
  );
}

/** One worker's row: what they were handed, when, how, and its proof; or that they aren't paid yet, or owe. */
function SheetRow({
  number,
  worker,
  timezone,
}: {
  number: number;
  worker: WorkerPay;
  timezone: string;
}) {
  const t = useTranslations("pay.sheet");
  const payment = useTranslations("pay.payment");
  const paid = paymentOf(worker);
  // A payslip below 0 hands nothing over: the worker owes the rest, which their next pay takes (WAGE-3).
  const total = new Decimal(worker.total);
  const owes = total.lt("0");
  // What was handed over, or is still to hand over: the payment's own amount, or what the payslip pays (to_hand_out),
  // 0 for one who owes. Never worked out here.
  const amount = paid === null ? worker.to_hand_out : paid.amount;
  const cell = "border border-foreground px-2 py-1 align-middle";
  return (
    <tr className="break-inside-avoid">
      <td className={`${cell} tabular-nums`}>{number}</td>
      <td className={cell}>{worker.display_name}</td>
      <td className={`${cell} text-right tabular-nums`}>
        {formatAmount(new Decimal(amount))}
      </td>
      <td className={`${cell} tabular-nums`}>
        {paid === null
          ? owes
            ? t("none")
            : null
          : formatDate(paid.at, timezone)}
      </td>
      <td className={cell}>
        {paid !== null ? (
          <>
            {payment(`methods.${paid.method}`)}
            {paid.reference === "" ? null : <> {paid.reference}</>}
          </>
        ) : owes ? (
          t("owes", { amount: formatAmount(total.abs()) })
        ) : (
          payment("notPaid")
        )}
      </td>
      <td className={cell}>
        <Proof worker={worker} />
      </td>
      {/* The pen's space: empty, as tall as a drawn signature, for every row. */}
      <td className={`${cell} h-12 min-w-32`} />
    </tr>
  );
}

/** The signature's box: the worker's drawing, opened from the photos' own route; that the demo keeps none; a dash for
 * M-Pesa and a bank, proven by their numbers instead, and for one who owes, who was handed nothing; or empty, not paid
 * yet. */
function Proof({ worker }: { worker: WorkerPay }) {
  const t = useTranslations("pay.sheet");
  const payment = useTranslations("pay.payment");
  const [failed, setFailed] = useState(false);
  const paid = paymentOf(worker);
  if (paid === null)
    return new Decimal(worker.total).lt("0") ? t("none") : null;
  if (paid.signature !== null) {
    // A drawing that can't be opened says so, so a paper never prints a box that looks signed and isn't.
    return failed ? (
      payment("signatureFailed")
    ) : (
      // Not shrunk by Next.js, which a static app can't (images.unoptimized); as tall as the pen's space beside it.
      // Fetched at once, never as it nears the screen (Next's own lazy), as Chapisha waits for every signature, and a
      // lazy one far down a long sheet is fetched only once someone scrolls to it (WAGE-5's review).
      <Image
        unoptimized
        src={photoAddress(paid.signature)}
        alt={payment("signature", { name: worker.display_name })}
        width={600}
        height={160}
        loading="eager"
        className="h-12 w-auto"
        onError={() => setFailed(true)}
      />
    );
  }
  if (paid.no_signature === "demo") return payment("demoSignature");
  return t("none");
}
