// payments.ts — a payslip handed out, as the office pages read it (WAGE-9, 02 §12): who may tap Lipa, whether a worker's
// line offers it, and the payment that counts.
//
// The pay's answers (pay.ts) carry each payslip's payments, crossed out ones too, what is still to hand each worker
// (`to_hand_out`), and whether a line is the person's own pay (`own`). Lipa asks pay.run, every manager's, beside the two
// keys of pay, never the approval's key: approving and handing out are two jobs, and the signature is the proof. The
// server asks all three again, and refuses one's own; the page only offers no button where it would.
import type { components } from "@/api/schema";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { maySeePay } from "@/features/workers/pay-rates";
import { Decimal } from "@/lib/decimal";

import type { WorkerPay } from "./pay";

export type PaymentLine = components["schemas"]["PaymentLine"];
export type PaymentMethod = components["schemas"]["PaymentMethodEnum"];

/** The three ways of paying, in the sheet's order (Jack, 26 Nov 2026): Taslimu, M-Pesa, Benki. */
export const METHODS: readonly PaymentMethod[] = [
  "cash",
  "mobile_money",
  "bank",
];

/** The key of handing out pay (02 §5). */
export const HANDS_OUT_PAY = "pay.run";

/** The server's longest transaction number (LONGEST_REFERENCE, apps/staffpay/models.py). */
export const LONGEST_REFERENCE = 30;

/** Whether the person may hand out pay: pay.run on the whole shop, and the two keys of pay, as nobody hands out what they
 * may not read. */
export function mayPay(me: WhoIsHere): boolean {
  return maySeePay(me) && me.permissions.whole_shop.includes(HANDS_OUT_PAY);
}

/** The payment that counts, or null: at most one, as the server holds. */
export function paymentOf(worker: WorkerPay): PaymentLine | null {
  return worker.payments.find((made) => made.voided === null) ?? null;
}

/** Whether a worker's line waits for Lipa: a payslip keeps it, it pays something, and nobody has paid it yet. */
export function waitsForLipa(worker: WorkerPay): boolean {
  return (
    worker.payslip !== null &&
    paymentOf(worker) === null &&
    new Decimal(worker.to_hand_out).gt("0")
  );
}

/** Whether this person is offered Lipa on a worker's line: it waits for one, they hold the keys, and it is not their own
 * pay (02 A5). */
export function offersLipa(worker: WorkerPay, may: boolean): boolean {
  return may && !worker.own && waitsForLipa(worker);
}
