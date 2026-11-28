// printed-payslips.tsx — the payslips of an approved month on A4, one page each (WAGE-5), for each worker to take home,
// as Jack pictured them (28 Nov 2026):
//
//   MPC · Mabatini Pumba Center
//   Hati ya malipo · Novemba 2026
//   Asha
//
//   Siku kamili              20 × 9,000     180,000
//   Nusu siku                 2 × 4,500       9,000
//   Faini                     siku 2         − 1,000
//   Chakula                   siku 22       − 16,000
//   Advansi ya 05/11/2026                   − 10,000
//   Advansi ya 18/11/2026                   − 10,000
//   ────────────────────────────────────────────────
//   Jumla ya mwezi                      TSh 152,000
//
//   Imeidhinishwa na Baba · 01/12/2026 09:00 asubuhi
//   Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi
//   (her drawing)
//
// Each line as its payslip kept it (kept_lines, WAGE-5), worded as the pay page words them (pay-lines.tsx): each advance a
// line of its own with its day, where the screen adds them into one, so a worker who says they took two, not three, is
// shown which; a debt with its month; each correction with its reason, last. Nothing is added up here: every amount and
// the total are the server's, as kept. One who owes is told so, as their payslip says: Alilipwa 0. Alibaki anadaiwa….
// How it was handed out is the payslip page's own words and proof (payslip-payments.tsx); not yet, Hajalipwa; only the
// payment that counts, as on the month's sheet.
//
// Every payslip of an approved month (from Mishahara), or one worker's alone (from their pay page, ?staff=…), a leaver
// approved alone before the month among them. Read from Mishahara's answer (GET pay/?month=…), which holds every kept
// line, as an office page asks the server (rule 5); behind the two keys of pay, as Mishahara is.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import {
  isMonth,
  type MonthNumber,
} from "@/features/attendance/attendance-month";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";
import { formatAmount, formatDay, formatMoney } from "@/lib/format";

import { useMonthTitle } from "./approve-sheet";
import { ApprovedLine } from "./approved-line";
import { useReasonWords } from "./corrections";
import { Paper, PaperHeading, PaperSheet } from "./paper";
import { payPage, usePayMonth, type WorkerPay, workerPayPage } from "./pay";
import { useSignedAmount } from "./pay-lines";
import { Left } from "./pay-notes";
import { paymentOf } from "./payments";
import { Proof, useSaid } from "./payslip-payments";

export function PrintedPayslipsScreen({
  asked,
  staff,
}: {
  /** The month in the address, "2026-11". */
  asked: string | null;
  /** One worker's job, from their pay page; null for everyone's. */
  staff: string | null;
}) {
  const t = useTranslations("pay.payslips");
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const month = asked !== null && isMonth(asked) ? asked : null;
  const answer = usePayMonth(month);
  const waiting = who.isPending || (month !== null && answer.isPending);
  // The arrow goes back where the paper was opened: the worker's pay page, or Mishahara, the same month.
  const fallback =
    month !== null && staff !== null
      ? workerPayPage(staff, month)
      : payPage(month);
  // What is printed: once the server answers, the payslips it keeps, each a worker's line with its payslip. Everyone's
  // only once the month is approved; one worker's once their own payslip is kept, as a leaver's is before the month's.
  const read = answer.data && !answer.isPending ? answer.data : null;
  const slips =
    read === null
      ? []
      : read.workers.filter(
          (worker) =>
            worker.payslip !== null &&
            (staff === null ? read.approval !== null : worker.staff === staff),
        );

  return (
    <Paper
      title={staff === null ? t("titleAll") : t("titleOne")}
      fallback={fallback}
    >
      {/* The screen's own lines, never on paper. */}
      <div className="grid gap-4 print:hidden">
        <p role="status" className={waiting ? "text-lg" : "sr-only"}>
          {waiting ? loginWords("waiting") : null}
        </p>
        <ApiErrorAlert error={who.error} />
        <ApiErrorAlert error={answer.error} />
        {month === null || (read !== null && slips.length === 0) ? (
          <p>{t("notApproved")}</p>
        ) : null}
      </div>
      {who.data && read !== null
        ? slips.map((worker) => (
            // Keyed by the job: one hired again in the month has a payslip for each (PPL-11).
            <PrintedPayslip
              key={worker.staff}
              month={read.month}
              worker={worker}
              shop={who.data.shop}
            />
          ))
        : null}
    </Paper>
  );
}

/** One worker's payslip, on a page of its own. */
function PrintedPayslip({
  month,
  worker,
  shop,
}: {
  month: string;
  /** Their line, kept by a payslip. */
  worker: WorkerPay;
  shop: { code: string; name: string; timezone: string };
}) {
  const t = useTranslations("pay.payslips");
  const pay = useTranslations("pay");
  const payment = useTranslations("pay.payment");
  const monthWords = useTranslations("attendanceMonth");
  const monthTitle = useMonthTitle();
  const reasonWords = useReasonWords();
  const signed = useSignedAmount();
  const said = useSaid(shop.timezone);
  const paid = paymentOf(worker);
  const total = new Decimal(worker.total);

  // Each kept line as a row: what, how many, how much. Days that pay say their amount as it stands; every other line
  // takes off, or, a correction, adds or takes off, so says its sign.
  const rows = worker.kept_lines.map((line) => {
    const plus = formatAmount(new Decimal(line.amount));
    switch (line.kind) {
      case "full":
      case "half":
        return {
          what: pay(`line.${line.kind}`),
          many: pay("times", {
            days: line.days ?? 0,
            each: formatAmount(new Decimal(line.each ?? "0")),
          }),
          amount: plus,
        };
      case "fines":
        return {
          what: pay("fines"),
          many: pay("mealDays", { count: line.days ?? 0 }),
          amount: signed(line.amount),
        };
      case "meals":
        return {
          what: pay("meals"),
          many: pay("mealDays", { count: line.days ?? 0 }),
          amount: signed(line.amount),
        };
      case "advance":
        return {
          // A day with no time: written from its own parts, never through a Date (formatDay).
          what: t("advanceOn", { date: formatDay(line.date ?? "") }),
          many: "",
          amount: signed(line.amount),
        };
      case "carried":
        return {
          what: pay("carried", {
            month: monthWords(
              `monthNames.${(line.date ?? "").slice(5, 7) as MonthNumber}`,
            ),
          }),
          many: "",
          amount: signed(line.amount),
        };
      case "correction":
        return {
          what: pay("correction.line", { reason: reasonWords(line.note) }),
          many: "",
          amount: signed(line.amount),
        };
    }
  });

  return (
    <PaperSheet>
      <div className="grid gap-4">
        <div className="grid gap-1">
          <PaperHeading
            shop={shop}
            title={t("heading", { month: monthTitle(month) })}
          />
          <p className="text-lg font-semibold">{worker.display_name}</p>
          <Left worker={worker} />
        </div>
        <table className="w-full tabular-nums">
          <caption className="sr-only">{pay("linesCaption")}</caption>
          <tbody>
            {rows.map((row, index) => (
              // The kept lines have one order and never change, so their place is their key.
              <tr key={index} className="break-inside-avoid">
                <th scope="row" className="py-1 text-left font-normal">
                  {row.what}
                </th>
                {/* Kept on one line: "20 × 9,000" cut in two reads as two numbers. */}
                <td className="px-3 py-1 text-right whitespace-nowrap">
                  {row.many}
                </td>
                <td className="py-1 text-right whitespace-nowrap">
                  {row.amount}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            {/* The ink's own colour, not the screen's pale line, which prints faint. */}
            <tr className="border-t border-foreground text-lg">
              <th
                scope="row"
                colSpan={2}
                className="pt-2 text-left font-semibold"
              >
                {pay("totalMonth")}
              </th>
              <td className="pt-2 text-right font-semibold whitespace-nowrap">
                {formatMoney(total)}
              </td>
            </tr>
          </tfoot>
        </table>
        {/* A payslip below 0 paid nothing, and its worker owed the rest (WAGE-3), said as their pay page says it. */}
        {total.lt("0") ? (
          <p>{pay("owed", { amount: formatMoney(total.abs()) })}</p>
        ) : null}
        <div className="grid gap-2">
          {worker.approval === null ? null : (
            <ApprovedLine approval={worker.approval} timezone={shop.timezone} />
          )}
          {paid !== null ? (
            <>
              <p>{said.paid(paid)}</p>
              <Proof payment={paid} name={worker.display_name} />
            </>
          ) : total.gt("0") ? (
            <p>{payment("notPaid")}</p>
          ) : null}
        </div>
      </div>
    </PaperSheet>
  );
}
