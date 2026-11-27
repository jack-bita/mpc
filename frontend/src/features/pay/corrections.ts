// corrections.ts — Marekebisho, a mistake found after a month's approval put right in a later month's pay (WAGE-10,
// 02 §12), as the office pages read it: who is offered Ongeza marekebisho, the address word that opens its sheet, and a
// reason's words.
//
// The worker's pay answer (pay.ts) carries the month's corrections, crossed out ones too, in the order typed; why the
// month takes none, as its code (`no_correction`), or null when it takes one; and, on the demo alone, the ready reasons
// a correction is typed and crossed out with. Only whoever approves pay types or crosses one out (Jack: A): pay.approve
// with the two keys of pay (mayApprovePay), never on their own pay. The server asks all three again, and refuses one's
// own; the page only offers no button where it would.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import type { components } from "@/api/schema";

import { type WorkerPayMonth, workerPayPage } from "./pay";

export type CorrectionLine = components["schemas"]["CorrectionLine"];

/** The address's word that opens the sheet as the page opens, as the flag of a late tap sends Baba here (WAGE-10):
 * /pay/worker/?staff=…&month=2026-12&marekebisho=ongeza. */
export const CORRECTION_PARAM = "marekebisho";
export const OPEN_THE_SHEET = "ongeza";

/** A worker's pay page of `month` with Ongeza marekebisho's sheet open as it opens: where a late tap's flag sends whoever
 * approves pay (WAGE-10). */
export function correctionPage(staff: string, month: string): string {
  return `${workerPayPage(staff, month)}&${new URLSearchParams({ [CORRECTION_PARAM]: OPEN_THE_SHEET }).toString()}`;
}

/** The corrections that count, in the order typed: what the pay adds up, and its lines. */
export function correctionsThatCount(answer: WorkerPayMonth): CorrectionLine[] {
  return answer.corrections.filter((line) => line.voided === null);
}

/** Whether this person is offered Ongeza marekebisho on a worker's month: they approve pay, the month takes one for the
 * worker, as the server says, and it is not their own pay (Jack: A). */
export function offersCorrection(
  answer: WorkerPayMonth,
  may: boolean,
): boolean {
  return may && !answer.worker.own && answer.no_correction === null;
}

/** Why a month's pay is closed for a worker, of the server's reasons it takes no correction: its own approval, or one
 * who left whose pay is approved. Every other reason is about typing a new one: a month the job no longer runs in, its
 * first day moved since (PPL-10), still lets one typed before be crossed out, as void_correction asks only that its month
 * is open and it isn't one's own (the review). */
const CLOSED = new Set(["pay.day_approved", "correction.left_paid"]);

/** Whether this person is offered Batilisha on a worker's corrections: they approve pay, the month is still open, and it
 * is not their own pay (Jack: A). */
export function offersCrossingOut(
  answer: WorkerPayMonth,
  may: boolean,
): boolean {
  return (
    may &&
    !answer.worker.own &&
    (answer.no_correction === null || !CLOSED.has(answer.no_correction))
  );
}

/** The demo's ready reasons (DEMO_CORRECTION_REASONS, apps/staffpay/services/correction.py), each a code, with the words
 * it is said in; and crossing one out's, Advansi's own. */
const READY_REASONS = {
  day_not_counted: "dayNotCounted",
  paid_too_much: "paidTooMuch",
  wrong_amount: "wrongAmount",
} as const;

/** A reason's words: the person's own as typed, or, on the demo, a ready one's; one newer than this app, its code, which
 * a person can still read out. */
export function useReasonWords(): (reason: string) => string {
  const t = useTranslations("pay.correction.readyReason");
  return (reason) =>
    reason in READY_REASONS
      ? t(READY_REASONS[reason as keyof typeof READY_REASONS])
      : reason;
}
