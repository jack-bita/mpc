// payment-note.tsx — under a worker's name on Mishahara, whether their payslip is handed out (WAGE-9), as Jack pictured
// it (26 Nov 2026): "Amelipwa 2/12/2026", or "Hajalipwa" with Lipa beside it, on the line itself.
//
// Only once a payslip keeps the line: a draft has nothing to hand out yet. A payslip that pays nothing, as one who owes,
// says neither, as there is nothing to hand over (Analipwa 0 says it, pay-notes.tsx). Lipa only for whoever may hand out
// pay, never on their own (offersLipa); it sits over the line's link, which opens the worker's own pay, so a finger on it
// pays and a finger anywhere else on the line opens their payslip.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { formatDate } from "@/lib/format";

import type { WorkerPay } from "./pay";
import { offersLipa, paymentOf, waitsForLipa } from "./payments";

export function PaymentNote({
  worker,
  timezone,
  mayPay,
  onPay,
  lineRef,
}: {
  worker: WorkerPay;
  /** The shop's, for the day it was paid. */
  timezone: string;
  /** Whether the person may hand out pay. */
  mayPay: boolean;
  /** Lipa tapped: the screen opens the sheet. */
  onPay: () => void;
  /** The line's words, where the keyboard goes once it is paid: its Lipa is gone by then. */
  lineRef: (element: HTMLElement | null) => void;
}) {
  const t = useTranslations("pay.payment");
  const paid = paymentOf(worker);
  // Nothing on a draft, which no payslip keeps, nor on a payslip that pays nothing: neither is paid, nor waits.
  if (paid === null && !waitsForLipa(worker)) return null;
  return (
    <div className="col-span-full flex flex-wrap items-center justify-between gap-2 text-muted-foreground">
      {/* The words alone take the keyboard once paid, never the line around them: the sheet hands the keyboard to the
          first button inside what it is given, which would be this Lipa, gone a moment later (sheet.tsx). */}
      <p ref={lineRef} tabIndex={-1} className="outline-none">
        {paid === null
          ? t("notPaid")
          : t("paidOn", { date: formatDate(paid.at, timezone) })}
      </p>
      {paid === null && offersLipa(worker, mayPay) ? (
        // relative z-10: above the line's link, laid over the whole line (pay-screen.tsx). Its name says whose, as every
        // line has one: "Lipa Asha".
        <Button
          kind="second"
          size="normal"
          className="relative z-10"
          aria-label={t("lipaFor", { name: worker.display_name })}
          onClick={onPay}
        >
          {t("lipa")}
        </Button>
      ) : null}
    </div>
  );
}
