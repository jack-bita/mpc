// pay-lines.tsx — one worker's pay, line by line, as Jack drew it (25 Nov 2026), so whoever pays it can check each line
// with a calculator (WAGE-2):
//
//   Siku kamili      14 × 10,000     140,000
//   Nusu siku         2 ×  5,000      10,000
//   Faini             2              − 2,000
//   Chakula          siku 16        − 16,000
//   Leo: siku kamili                  10,000
//   Advansi                         − 40,000
//   Deni la Oktoba                  − 18,000
//   Marekebisho: Oktoba: siku ya 7/10 haikuhesabiwa   + 9,000
//   ------------------------------------------
//   Jumla ya kumlipa leo         TSh 102,000
//   ! Siku 1 inasubiri uamuzi
//
// On the worker's pay page (worker-pay-screen.tsx) and in the card of their own page (worker-month-pay.tsx), so both
// show the same; and on the worker's own Siku na malipo yangu (WAGE-4, my-pay.tsx), the same lines said to them (voice
// "own": Jumla ya kulipwa leo, Unadaiwa), with no row to open. Today's lines, once they tapped Toka, are apart, as
// today isn't over: its meals are split so far (Jack: A). Then what they were given before payday (WAGE-8), today's
// with it, and what an earlier month's pay left owed (WAGE-3), just above the total; last, each correction of an
// earlier month's mistake, with its reason, plus or minus (WAGE-10). A total below 0 pays nothing, and the page says
// what is owed (Jack: A). Every amount is the server's; the page multiplies and adds up nothing. Once a payslip keeps
// the pay, these are its lines as they were kept.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import {
  monthOf,
  type MonthNumber,
} from "@/features/attendance/attendance-month";
import { Decimal } from "@/lib/decimal";
import { formatAmount, formatMoney } from "@/lib/format";

import { type CorrectionLine, useReasonWords } from "./corrections";
import type { WorkerPay } from "./pay";
import { type Counted, isThisMonth, Left, NotPaid } from "./pay-notes";

/** What the lines read of a worker's pay: the days over and today's, the total, a debt's month, who approved it, and
 * their last day. Mishahara's line and the worker's own (OwnPayLine, WAGE-4) both have these. */
export type PaidLine = Pick<
  WorkerPay,
  "pay" | "today" | "total" | "carried_from" | "approval" | "left_on"
>;

/** Who the words speak of: the worker, as Baba reads their pay ("Jumla ya kumlipa leo", "Anadaiwa"); or to them, on
 * their own page (WAGE-4: "Jumla ya kulipwa leo", "Unadaiwa"). */
export type Voice = "worker" | "own";

/** One row: what, how many, and how much; and, for a correction the page lets open, what a tap opens. */
type Row = {
  key: string;
  what: string;
  many: string;
  amount: string;
  open?: () => void;
};

/** An amount that may be either way, with its sign: "+ 9,000", "− 5,000" (WAGE-10). */
export function useSignedAmount(): (amount: string) => string {
  const t = useTranslations("pay");
  return (amount) => {
    const value = new Decimal(amount);
    return t(value.lt("0") ? "less" : "more", {
      amount: formatAmount(value.abs()),
    });
  };
}

export function PayLines({
  answer,
  worker,
  corrections,
  onCorrection,
  voice = "worker",
}: {
  /** The month the pay is of. */
  answer: Counted;
  worker: PaidLine;
  /** The corrections that count, in the order typed: each its own line, with its reason (WAGE-10). */
  corrections: CorrectionLine[];
  /** A correction's line tapped: the page opens its sheet, with Batilisha (WAGE-10). With none, the lines are only
   * read, as on a month whose pay is approved, or for whoever may not cross one out. */
  onCorrection?: (line: CorrectionLine) => void;
  /** Spoken of the worker, or to them on their own page (WAGE-4). */
  voice?: Voice;
}) {
  const t = useTranslations("pay");
  const mine = useTranslations("mine");
  const monthWords = useTranslations("attendanceMonth");
  const reasonWords = useReasonWords();
  const signed = useSignedAmount();
  const { pay, today } = worker;
  const plus = (amount: string) => formatAmount(new Decimal(amount));
  // Money taken off, with its minus: "− 2,000".
  const less = (amount: string) => t("less", { amount: plus(amount) });

  const rows: Row[] = pay.lines.map((line) => ({
    // One line per kind and amount: the server groups the days that pay the same.
    key: `${line.paid_as} ${line.each}`,
    what: t(`line.${line.paid_as}`),
    many: t("times", { days: line.days, each: plus(line.each) }),
    amount: plus(line.amount),
  }));
  if (pay.fined_days > 0)
    rows.push({
      key: "fines",
      what: t("fines"),
      many: String(pay.fined_days),
      amount: less(pay.fines),
    });
  if (pay.meal_days > 0)
    rows.push({
      key: "meals",
      what: t("meals"),
      many: t("mealDays", { count: pay.meal_days }),
      amount: less(pay.meals),
    });
  // Today, one day: its own line, and its own fine and meals under it. One that waits pays nothing, and says so below.
  for (const line of today?.lines ?? [])
    rows.push({
      key: "today",
      what: t(`todayLine.${line.paid_as}`),
      many: "",
      amount: plus(line.amount),
    });
  if (today && today.fined_days > 0)
    rows.push({
      key: "today fines",
      what: t("todayLine.fines"),
      many: "",
      amount: less(today.fines),
    });
  if (today && today.meal_days > 0)
    rows.push({
      key: "today meals",
      what: t("todayLine.meals"),
      many: "",
      amount: less(today.meals),
    });
  // After the days, as the money was given, and is no part of a day (WAGE-8). "0" as text: the shared Decimal refuses a
  // plain number (rule 3).
  if (new Decimal(pay.advances).gt("0"))
    rows.push({
      key: "advances",
      what: t("advances"),
      many: "",
      amount: less(pay.advances),
    });
  // The last line before the total: what an earlier month's pay left owed, with its month (WAGE-3, Jack: A).
  if (worker.carried_from !== null)
    rows.push({
      key: "carried",
      what: t("carried", {
        month: monthWords(
          `monthNames.${worker.carried_from.slice(5) as MonthNumber}`,
        ),
      }),
      many: "",
      amount: less(pay.carried),
    });
  // Last, the corrections of an earlier month's mistakes (WAGE-10): one line each, its reason said, plus or minus. The
  // pay's own sum of them is in its total; each line is the server's too, so the page adds nothing up.
  for (const line of corrections)
    rows.push({
      key: `correction ${line.id}`,
      what: t("correction.line", { reason: reasonWords(line.reason) }),
      many: "",
      amount: signed(line.amount),
      open: onCorrection === undefined ? undefined : () => onCorrection(line),
    });

  return (
    <div className="grid gap-3">
      <table className="w-full tabular-nums">
        {/* The table's name, for a screen reader: whose pay and which month are said by the headings above it. */}
        <caption className="sr-only">{t("linesCaption")}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="py-1 text-left font-normal">
                {/* A button where the page lets it open: its sheet says who typed it, and offers Batilisha. Still the
                    row's name, so the table reads the same. */}
                {row.open === undefined ? (
                  row.what
                ) : (
                  <button
                    type="button"
                    onClick={row.open}
                    className="text-left underline underline-offset-4 outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {row.what}
                  </button>
                )}
              </th>
              {/* Kept on one line: "14 × 10,000" cut in two reads as two numbers. */}
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
          <tr className="border-t border-border text-lg">
            <th
              scope="row"
              colSpan={2}
              className="pt-2 text-left font-semibold"
            >
              {/* Today, what Baba hands over, or what the worker is paid, on their own page; of a month gone by, or once
                  it is approved, what it came to. */}
              {isThisMonth(answer) && worker.approval === null
                ? voice === "own"
                  ? mine("totalToday")
                  : t("totalToday")
                : t("totalMonth")}
            </th>
            <td className="pt-2 text-right font-semibold whitespace-nowrap">
              {formatMoney(new Decimal(worker.total))}
            </td>
          </tr>
        </tfoot>
      </table>
      <NotPaid worker={worker} />
      <Owes answer={answer} worker={worker} voice={voice} />
      {/* The day they left: of no use on their own page, as one who left logs in no more. */}
      {voice === "own" ? null : <Left worker={worker} />}
    </div>
  );
}

/** "Analipwa 0. Anadaiwa TSh 18,000…", of a total below 0 of a month that is over (Jack: A): nothing is handed over, and
 * their next pay takes it off; or, of one who left by its end, with no pay to come, stays owed. Once approved, what it
 * was: "Alilipwa 0. Alibaki anadaiwa TSh 18,000.", as a payslip is read for ever, long after the next one took it.
 * Nothing on a month still running, whose days still come. */
function Owes({
  answer,
  worker,
  voice,
}: {
  answer: Counted;
  worker: PaidLine;
  voice: Voice;
}) {
  // On their own page, said to them: "Unalipwa 0. Unadaiwa TSh 18,000…" (WAGE-4).
  const pay = useTranslations("pay");
  const mine = useTranslations("mine");
  const total = new Decimal(worker.total);
  if (!total.lt("0") || (isThisMonth(answer) && worker.approval === null))
    return null;
  // Days as text sort as days do, and so do months.
  const goneByItsEnd =
    worker.left_on !== null && monthOf(worker.left_on) <= answer.month;
  const key =
    worker.approval !== null ? "owed" : goneByItsEnd ? "owesLeft" : "owes";
  const amount = { amount: formatMoney(total.abs()) };
  return <p>{voice === "own" ? mine(key, amount) : pay(key, amount)}</p>;
}
