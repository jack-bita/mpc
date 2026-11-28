// payslip-payments.tsx — the foot of a payslip, under its lines: how it was handed out (WAGE-9), as Jack pictured it
// (26 Nov 2026):
//
//   Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi
//   ┌──────────────────────────┐
//   │   (Asha's signature)     │
//   └──────────────────────────┘
//                         [ Batilisha ]
//
// or, not paid yet, "Hajalipwa" with Lipa (pay-sheet.tsx). A payment crossed out stays, struck through, with who, when
// and why under it, and its signature, kept for good; the payslip then shows Hajalipwa and Lipa again under it:
//
//   ~~Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi~~
//   Imebatilishwa na Baba · 02/12/2026 09:00 asubuhi: Nilibonyeza mfanyakazi mwingine
//   (the signature)
//   Hajalipwa                  [ Lipa ]
//
// By M-Pesa or a bank, the transaction number in place of the signature; on the demo, that none is kept. Lipa and
// Batilisha only for whoever may hand out pay (mayPay), never on their own pay (02 A5). One who left, approved alone, is
// paid from here the evening they go.
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps which sheet is open.
"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { dayPart, formatDate, formatTime } from "@/lib/format";
import { photoAddress } from "@/lib/photo-address";

import type { WorkerPay } from "./pay";
import { PaySheet } from "./pay-sheet";
import {
  offersLipa,
  type PaymentLine,
  paymentOf,
  waitsForLipa,
} from "./payments";
import { type ReadyReason, VoidPayment } from "./void-payment";

export function PayslipPayments({
  worker,
  month,
  timezone,
  mayPay,
  keepsSignatures,
  readyReasons,
}: {
  /** The worker's line, kept by a payslip. */
  worker: WorkerPay;
  /** The month it pays, "2026-11". */
  month: string;
  /** The shop's, for when each was done. */
  timezone: string;
  /** Whether the person may hand out pay. */
  mayPay: boolean;
  /** Whether cash is sent with its signature: false on the demo. */
  keepsSignatures: boolean;
  /** On the demo, the ready reasons a payment is crossed out with. */
  readyReasons: readonly string[];
}) {
  const t = useTranslations("pay.payment");
  const said = useSaid(timezone);
  const counted = paymentOf(worker);
  const [paying, setPaying] = useState(false);
  const [crossing, setCrossing] = useState<PaymentLine | null>(null);
  // What is true now, Amelipwa or Hajalipwa: always on the page, the same line whichever it says, so the keyboard goes to
  // it as a sheet closes, a moment before the page has drawn what the sheet changed (pay-screen.tsx's approval line).
  // The words alone, never the row with its button: the sheet hands the keyboard to the first button inside what it is
  // given (frontend rules).
  const now = useRef<HTMLParagraphElement>(null);
  const afterChange = useRef(false);
  if (worker.payslip === null) return null;
  const mayChange = mayPay && !worker.own;
  return (
    <section aria-label={t("section")} className="grid gap-4">
      {/* The ones crossed out first, in the order made, as what happened before what is true now. */}
      {worker.payments
        .filter((made) => made.voided !== null)
        .map((made) => (
          <div key={made.id} className="grid gap-2">
            <p className="text-muted-foreground">
              <s>{said.paid(made)}</s>
            </p>
            <Proof payment={made} name={worker.display_name} />
            <p>{said.voided(made, readyReasons)}</p>
          </div>
        ))}
      <div className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p
            ref={now}
            tabIndex={-1}
            className={
              counted === null ? "outline-none" : "font-semibold outline-none"
            }
          >
            {counted !== null
              ? said.paid(counted)
              : waitsForLipa(worker)
                ? t("notPaid")
                : null}
          </p>
          {offersLipa(worker, mayPay) ? (
            <Button
              kind="main"
              size="normal"
              onClick={() => {
                afterChange.current = false;
                setPaying(true);
              }}
            >
              {t("lipa")}
            </Button>
          ) : null}
        </div>
        {counted === null ? null : (
          <>
            <Proof payment={counted} name={worker.display_name} />
            {/* Batilisha, for whoever may hand out pay, never on one's own. */}
            {mayChange ? (
              <Button
                kind="second"
                size="normal"
                className="justify-self-start"
                onClick={() => {
                  afterChange.current = false;
                  setCrossing(counted);
                }}
              >
                {t("batilisha")}
              </Button>
            ) : null}
          </>
        )}
      </div>
      {paying ? (
        <PaySheet
          worker={worker}
          month={month}
          keepsSignatures={keepsSignatures}
          onDone={() => {
            afterChange.current = true;
            setPaying(false);
          }}
          onClose={() => setPaying(false)}
          finalFocus={() => (afterChange.current ? now.current : null)}
        />
      ) : null}
      {crossing === null ? null : (
        <VoidPayment
          payment={crossing}
          name={worker.display_name}
          month={month}
          readyReasons={readyReasons}
          onDone={() => {
            afterChange.current = true;
            setCrossing(null);
          }}
          onClose={() => setCrossing(null)}
          finalFocus={() => (afterChange.current ? now.current : null)}
        />
      )}
    </section>
  );
}

/** How a payment and its crossing out are said, on the shop's own clock and calendar; the printed payslip says them
 * the same (WAGE-5). */
export function useSaid(timezone: string) {
  const t = useTranslations("pay.payment");
  const attendance = useTranslations("attendance");
  const when = (at: string) => ({
    date: formatDate(at, timezone),
    time: attendance("timeOfDay", {
      time: formatTime(at, timezone),
      part: dayPart(at, timezone),
    }),
  });
  return {
    /** "Amelipwa taslimu na Baba · 02/12/2026 08:10 asubuhi". */
    paid: (made: PaymentLine) =>
      t("paidBy", {
        how: t(`how.${made.method}`),
        by: made.by,
        ...when(made.at),
      }),
    /** "Imebatilishwa na Baba · 02/12/2026 09:00 asubuhi: Nilibonyeza mfanyakazi mwingine". */
    voided: (made: PaymentLine, readyReasons: readonly string[]) =>
      made.voided === null
        ? ""
        : t("voidedBy", {
            by: made.voided.by,
            ...when(made.voided.at),
            // On the demo a ready reason's code, said in words; elsewhere the words typed.
            reason: readyReasons.includes(made.voided.reason)
              ? t(`readyReason.${made.voided.reason as ReadyReason}`)
              : made.voided.reason,
          }),
  };
}

/** What proves a payment: its transaction number; its signature, kept for good; or, on the demo, that none is kept. The
 * printed payslip shows the same (WAGE-5). */
export function Proof({
  payment,
  name,
  loading = "lazy",
}: {
  payment: PaymentLine;
  name: string;
  /** When the signature is fetched: as it nears the screen (lazy, Next's own), on a page that is read; at once (eager)
   * on a paper, whose Chapisha waits for every picture, and the browser fetches a lazy one far down the page only
   * once someone scrolls to it (WAGE-5's review). */
  loading?: "lazy" | "eager";
}) {
  const t = useTranslations("pay.payment");
  const [failed, setFailed] = useState(false);
  return (
    <>
      {payment.reference === "" ? null : (
        <p>{t("number", { reference: payment.reference })}</p>
      )}
      {payment.signature !== null && failed ? (
        <p className="text-muted-foreground">{t("signatureFailed")}</p>
      ) : payment.signature !== null ? (
        // Opened from the photos' own route, as the browser sends the office's login with it, and only with the two
        // keys of pay (CTRL-3). Not shrunk by Next.js, which a static app can't (images.unoptimized).
        <Image
          unoptimized
          src={photoAddress(payment.signature)}
          alt={t("signature", { name })}
          width={600}
          height={160}
          loading={loading}
          className="h-auto w-64 rounded-lg border border-border bg-white"
          onError={() => setFailed(true)}
        />
      ) : payment.no_signature === "demo" ? (
        <p className="text-muted-foreground">{t("demoSignature")}</p>
      ) : null}
    </>
  );
}
