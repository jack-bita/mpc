// pay-excel.ts — an approved month's pay as an Excel file (WAGE-5), for whoever keeps the owner's books, as Jack
// pictured it (28 Nov 2026): one sheet, a row per payslip, and the total.
//
//   Mishahara ya Novemba 2026 · Imeidhinishwa na Baba · 01/12/2026
//
//   Jina    Kwa siku  Siku kamili  Nusu siku  Faini   Chakula  Advansi  Deni     Marekebisho  Jumla    Analipwa  Tarehe      Njia      Namba ya muamala
//   Asha     9,000    20           2          -1,000  -16,000  -20,000        0       0      152,000  152,000   02/12/2026  Taslimu
//   Baraka   9,000    15           0          -2,000  -16,000        0        0       0      117,000  117,000   02/12/2026  M-Pesa    QJK7A2B9XC
//   Juma    10,000    17           1          -1,000  -20,000        0        0   9,000      163,000  163,000   03/12/2026  Taslimu
//   Neema    8,000     3           0               0   -4,000  -20,000  -18,000       0      -18,000        0              Hakulipwa
//   Jumla                                                                                              432,000
//
// The amounts are numbers in the file, so they can be added up and sorted there; the signatures are on the paper alone
// (month-sheet.tsx), as a picture in a cell is awkward to work with. Made in the browser, not on the server: its words
// are the person's own language, from the same books as the screens (ADR-0040), and a shop's month is a few dozen rows,
// so no background job (03 §5.15). The library that writes it is loaded only when the file is asked for (savePayExcel),
// so no page carries it until then.
//
// Every amount is the server's, as kept: the line's sums (pay) and its total. Nothing is added up here: money is a
// string all the way, until the very edge, a cell of the file, which holds a number (asCellNumber). Excel keeps every
// number as a binary fraction, which holds a whole number of shillings exactly; one that isn't whole is refused, never
// rounded on the way (rule 3).
"use client";

import type {
  Cell,
  CellObject,
  Row,
  SheetData,
} from "write-excel-file/browser";
import { useTranslations } from "use-intl";

import { Decimal } from "@/lib/decimal";
import { formatAmount, formatDate, wholeShillings } from "@/lib/format";

import { useMonthTitle } from "./approve-sheet";
import type { Approval, PayMonth, WorkerPay } from "./pay";
import { paymentOf, type PaymentMethod, waitsForLipa } from "./payments";

/** The words the file is written in, in the person's own language. */
export type ExcelWords = {
  /** The top line: the month, and who approved it, when. */
  title: string;
  /** The fourteen columns' headings, in Jack's order. */
  headings: readonly string[];
  /** The last row's name. */
  total: string;
  /** A way of paying: Taslimu, M-Pesa, Benki. */
  method: (method: PaymentMethod) => string;
  /** Not paid yet, and one who owes, handed nothing. */
  notPaid: string;
  owes: string;
  /** The sheet's own name, on its tab. */
  sheet: string;
};

/** The file's name: the month, so a year of files sorts by itself. */
export function excelFileName(month: string): string {
  return `mishahara-${month}.xlsx`;
}

/** How Excel shows the money: whole shillings with a comma between thousands, "-1,000" below 0. */
const MONEY = "#,##0";

/** A money string of the server's as a number for a cell of the file: only a whole number of shillings, by the one
 * check the screens' money goes through (wholeShillings, which refuses a part of one, never rounding it away, as it is
 * a bug in what the server sent), and small enough for its number to be exact (Number.isSafeInteger). */
export function asCellNumber(amount: string): number {
  const whole = Number(wholeShillings(new Decimal(amount)));
  if (!Number.isSafeInteger(whole))
    throw new RangeError(`Too big to be exact in a cell: ${amount}`);
  return whole;
}

/** A cell of money, plus or minus as given. */
function money(amount: string): CellObject {
  return { value: asCellNumber(amount), type: Number, format: MONEY };
}

/** A cell of money taken off, which the line's sums say above 0: written below 0, as it takes off (Faini -1,000). */
function less(amount: string): CellObject {
  return money(new Decimal(amount).neg().toFixed(2));
}

/** A cell of text, kept as text: Excel never reads "02/12/2026" as a date of its own guessing, nor a number's look. */
function text(value: string): CellObject {
  return { value, type: String, format: "@" };
}

/** A day count, a number of days, never money. */
function days(count: number): CellObject {
  return { value: count, type: Number };
}

/** The daily rate: one full-day line's, as a number; two or more, a rate changed mid-month, all of them as text; none,
 * as for one who came only half days, an empty cell. */
function dailyRate(worker: WorkerPay): Cell {
  const rates = worker.pay.lines
    .filter((line) => line.paid_as === "full")
    .map((line) => line.each);
  if (rates.length === 0) return null;
  if (rates.length === 1) return money(rates[0] ?? "0");
  return text(rates.map((rate) => formatAmount(new Decimal(rate))).join(" / "));
}

/** The days of a kind, added up: a count of days, never money. */
function daysOf(worker: WorkerPay, kind: "full" | "half"): number {
  return worker.pay.lines
    .filter((line) => line.paid_as === kind)
    .reduce((count, line) => count + line.days, 0);
}

/** One payslip's row, its cells in the headings' order. */
function rowOf(worker: WorkerPay, words: ExcelWords, timezone: string): Row {
  const paid = paymentOf(worker);
  // As on the month's sheet: not paid yet (waitsForLipa), one who owes, or, of exactly 0, neither, an empty cell.
  const waits = waitsForLipa(worker);
  const owes = new Decimal(worker.total).lt("0");
  return [
    text(worker.display_name),
    dailyRate(worker),
    days(daysOf(worker, "full")),
    days(daysOf(worker, "half")),
    less(worker.pay.fines),
    less(worker.pay.meals),
    less(worker.pay.advances),
    less(worker.pay.carried),
    // As it stands, plus or minus (WAGE-10).
    money(worker.pay.corrections),
    money(worker.total),
    // What was handed over, or is still to hand over: the payment's own amount, or what the payslip pays, 0 for one
    // who owes, as on the month's sheet.
    money(paid === null ? worker.to_hand_out : paid.amount),
    paid === null ? null : text(formatDate(paid.at, timezone)),
    paid !== null
      ? text(words.method(paid.method))
      : waits
        ? text(words.notPaid)
        : owes
          ? text(words.owes)
          : null,
    paid === null || paid.reference === "" ? null : text(paid.reference),
  ];
}

/** The file's rows: the title, an empty row, the headings, a row per payslip, and the month's total under Analipwa, what
 * the month pays (the server's own, which counts one who owes as 0). */
export function payRows(
  answer: PayMonth,
  words: ExcelWords,
  timezone: string,
): SheetData {
  const headings = words.headings.map((heading) => ({
    value: heading,
    type: String,
    fontWeight: "bold" as const,
  }));
  const totalRow: Row = Array.from(
    { length: words.headings.length },
    () => null,
  );
  totalRow[0] = { value: words.total, type: String, fontWeight: "bold" };
  // Under Analipwa, the eleventh column.
  totalRow[10] = { ...money(answer.total), fontWeight: "bold" };
  return [
    [{ value: words.title, type: String, fontWeight: "bold" }],
    [],
    headings,
    ...answer.workers
      .filter((worker) => worker.payslip !== null)
      .map((worker) => rowOf(worker, words, timezone)),
    totalRow,
  ];
}

/** Each column's width, in characters: the names and the way wide enough to read, the numbers as wide as their headings. */
const WIDTHS = [16, 10, 12, 10, 10, 10, 10, 10, 12, 12, 12, 12, 12, 18];

/** Writes the file and hands it to the browser to save. The library is loaded here, the first time it is asked for. */
export async function savePayExcel(
  answer: PayMonth,
  words: ExcelWords,
  timezone: string,
): Promise<void> {
  const { default: writeExcelFile } = await import("write-excel-file/browser");
  await writeExcelFile(payRows(answer, words, timezone), {
    sheet: words.sheet,
    columns: WIDTHS.map((width) => ({ width })),
  }).toFile(excelFileName(answer.month));
}

/** The file's words, in the person's own language, of a month approved by someone, on a day. */
export function useExcelWords(
  month: string,
  approval: Approval,
  timezone: string,
): ExcelWords {
  const t = useTranslations("pay.excel");
  const payment = useTranslations("pay.payment");
  const monthTitle = useMonthTitle();
  return {
    title: t("title", {
      month: monthTitle(month),
      by: approval.by,
      date: formatDate(approval.at, timezone),
    }),
    headings: [
      t("name"),
      t("rate"),
      t("fullDays"),
      t("halfDays"),
      t("fines"),
      t("meals"),
      t("advances"),
      t("carried"),
      t("corrections"),
      t("total"),
      t("handedOver"),
      t("date"),
      t("way"),
      t("reference"),
    ],
    total: t("total"),
    method: (method) => payment(`methods.${method}`),
    notPaid: payment("notPaid"),
    owes: t("owes"),
    sheet: t("sheet"),
  };
}
