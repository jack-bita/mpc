// my-pay.tsx — Malipo, a worker's own pay of the month on Siku na malipo yangu (WAGE-4), as Jack pictured it (27 Nov
// 2026):
//
//   Hadi jana, Alhamisi 26/11                     (a month still open)
//   Bado hayajaidhinishwa, yanaweza kubadilika.
//   Siku kamili   20 × 9,000      180,000
//   Nusu siku      1 × 4,500        4,500
//   Faini          2              − 1,000
//   Chakula        siku 21       − 31,500
//   Advansi                      − 20,000
//   Jumla ya kulipwa leo      TSh 132,000
//
//   Imeidhinishwa na Baba · 01/11/2026 09:00 asubuhi   (a month approved)
//   …its payslip's lines, as they were kept…
//   Jumla ya mwezi            TSh 159,500
//   Umelipwa taslimu na Baba · 01/11/2026 10:15 asubuhi
//
// The lines are Baba's own on the worker's pay page (pay-lines.tsx), said to the worker (voice "own": Jumla ya kulipwa
// leo, Unadaiwa), so the two read the same numbers. A correction is a line of its own; one crossed out stays under the
// lines, struck through, with who, when and why (WAGE-10). Only to read: no Lipa, no Batilisha, no Ongeza marekebisho,
// and no picture of the signature, which the answer doesn't carry; a payment by M-Pesa or a bank says its number, for
// the worker to check against their phone. A month with no daily pay says so in one sentence.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useRef } from "react";
import { useTranslations } from "use-intl";

import { Card, CardContent } from "@/components/design/card";
import { ApprovedLine } from "@/features/pay/approved-line";
import { PayLines } from "@/features/pay/pay-lines";
import { useCountedTo } from "@/features/pay/pay-notes";
import { CrossedOutCorrections } from "@/features/pay/void-correction";
import type { ReadyReason } from "@/features/pay/void-payment";
import { Decimal } from "@/lib/decimal";
import { dayPart, formatDate, formatTime } from "@/lib/format";

import type { OwnPay, OwnPayment } from "./mine";

export function MyPay({
  answer,
  timezone,
}: {
  answer: OwnPay;
  /** The shop's zone, for when the pay was approved and handed out. */
  timezone: string;
}) {
  const t = useTranslations("mine");
  const counted = useCountedTo(answer);
  // CrossedOutCorrections keeps a place the manager's page sends the keyboard to after Batilisha; here nothing does.
  const crossedOut = useRef<HTMLDivElement>(null);
  const { line } = answer;
  if (!answer.paid_by_day)
    // No line of theirs: no daily rate this month, and no money given. On a month whose first working day is still to
    // come, nothing at all, as the Siku tab shows that month.
    return answer.no_day_yet ? null : <p>{t("noRate")}</p>;
  return (
    <div className="grid gap-4">
      {line.approval !== null ? (
        <ApprovedLine approval={line.approval} timezone={timezone} />
      ) : (
        <>
          {counted !== null ? <p>{counted}</p> : null}
          <p className="font-semibold">{t("notApproved")}</p>
        </>
      )}
      <Card>
        <CardContent>
          <PayLines
            answer={answer}
            worker={line}
            corrections={answer.corrections.filter(
              (correction) => correction.voided === null,
            )}
            voice="own"
          />
        </CardContent>
      </Card>
      <CrossedOutCorrections
        corrections={answer.corrections}
        timezone={timezone}
        place={crossedOut}
      />
      {line.approval !== null ? (
        <HandedOut answer={answer} timezone={timezone} />
      ) : null}
    </div>
  );
}

/** How the approved pay was handed out, as its foot on Baba's page says it, to the worker: the payments crossed out
 * first, struck through, with who, when and why; then "Umelipwa taslimu na Baba · …", with the number of one by M-Pesa
 * or a bank; or, with something still to hand out and nothing paid, "Bado hujalipwa." */
function HandedOut({ answer, timezone }: { answer: OwnPay; timezone: string }) {
  const t = useTranslations("mine");
  const payment = useTranslations("pay.payment");
  const attendance = useTranslations("attendance");
  const when = (at: string) => ({
    date: formatDate(at, timezone),
    time: attendance("timeOfDay", {
      time: formatTime(at, timezone),
      part: dayPart(at, timezone),
    }),
  });
  const paid = (made: OwnPayment) =>
    t("paidBy", {
      how: payment(`how.${made.method}`),
      by: made.by,
      ...when(made.at),
    });
  const reasonWords = (reason: string) =>
    answer.void_reasons.includes(reason)
      ? payment(`readyReason.${reason as ReadyReason}`)
      : reason;
  const counted = answer.line.payments.find((made) => made.voided === null);
  return (
    <section aria-label={payment("section")} className="grid gap-3">
      {answer.line.payments
        .filter((made) => made.voided !== null)
        .map((made) => (
          <div key={made.id} className="grid gap-1">
            <p className="text-muted-foreground">
              <s>{paid(made)}</s>
            </p>
            {made.voided === null ? null : (
              <p>
                {payment("voidedBy", {
                  by: made.voided.by,
                  ...when(made.voided.at),
                  reason: reasonWords(made.voided.reason),
                })}
              </p>
            )}
          </div>
        ))}
      {counted !== undefined ? (
        <div className="grid gap-1">
          <p className="font-semibold">{paid(counted)}</p>
          {counted.reference !== "" ? (
            <p>{payment("number", { reference: counted.reference })}</p>
          ) : null}
        </div>
      ) : new Decimal(answer.line.to_hand_out).gt("0") ? (
        <p>{t("notPaid")}</p>
      ) : null}
    </section>
  );
}
