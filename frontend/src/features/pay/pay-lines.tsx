// pay-lines.tsx — one worker's pay, line by line, as Jack drew it (25 Nov 2026), so whoever pays it can check each line
// with a calculator (WAGE-2):
//
//   Siku kamili      14 × 10,000     140,000
//   Nusu siku         2 ×  5,000      10,000
//   Faini             2              − 2,000
//   Chakula          siku 16        − 16,000
//   Leo: siku kamili                  10,000
//   ------------------------------------------
//   Jumla ya kumlipa leo         TSh 142,000
//   ! Siku 1 inasubiri uamuzi
//
// On the worker's pay page (worker-pay-screen.tsx) and in the card of their own page (worker-month-pay.tsx), so both show
// the same. Today's lines, once they tapped Toka, are apart, as today isn't over: its meals are split so far (Jack: A).
// Every amount is the server's; the page multiplies and adds up nothing.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { Decimal } from "@/lib/decimal";
import { formatAmount, formatMoney } from "@/lib/format";

import type { WorkerPay } from "./pay";
import { type Counted, isThisMonth, Left, NotPaid } from "./pay-notes";

/** One row: what, how many, and how much. */
type Row = { key: string; what: string; many: string; amount: string };

export function PayLines({
  answer,
  worker,
}: {
  /** The month the pay is of. */
  answer: Counted;
  worker: WorkerPay;
}) {
  const t = useTranslations("pay");
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

  return (
    <div className="grid gap-3">
      <table className="w-full tabular-nums">
        {/* The table's name, for a screen reader: whose pay and which month are said by the headings above it. */}
        <caption className="sr-only">{t("linesCaption")}</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="py-1 text-left font-normal">
                {row.what}
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
              {/* Today, what Baba hands over; of a month gone by, what it came to. */}
              {t(isThisMonth(answer) ? "totalToday" : "totalMonth")}
            </th>
            <td className="pt-2 text-right font-semibold whitespace-nowrap">
              {formatMoney(new Decimal(worker.total))}
            </td>
          </tr>
        </tfoot>
      </table>
      <NotPaid worker={worker} />
      <Left worker={worker} />
    </div>
  );
}
