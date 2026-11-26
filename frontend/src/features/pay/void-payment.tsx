// void-payment.tsx — Batilisha: a payment marked by mistake, crossed out in a sheet over the payslip (WAGE-9), as Jack
// pictured it (26 Nov 2026):
//
//   ┌──────────────────────────────────┐
//   │ Batilisha malipo ya Juma         │
//   │ Novemba 2026 · TSh 132,000       │
//   │ Sababu  [ Nilibonyeza mfanyakazi │
//   │           mwingine             ] │
//   │ [ Ghairi ]         [ Batilisha ] │
//   └──────────────────────────────────┘
//
// It stays on the payslip, struck through, with who, when and why, and its signature with it (T2); the payslip then waits
// for Lipa again. Never brought back. Whoever may hand out pay may, but never on their own (02 A5): the page offers no
// button there, and the server refuses it all the same (payment.own). On the demo, the reason is the ready one to tap
// (the answer's void_reasons), as typed words would show to every visitor after; elsewhere it is typed. Once done, the
// pay is read again before the sheet closes, so it never closes onto a payslip that still says Amelipwa.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { useMonthTitle } from "./approve-sheet";
import { PAY } from "./pay";
import type { PaymentLine } from "./payments";

/** The server's longest reason (VoidPaymentSerializer, 200 characters). */
const REASON_LONGEST = 200;

/** The demo's ready reasons, by their codes (DEMO_PAYMENT_VOID_REASONS, apps/staffpay/services/payment.py). */
export type ReadyReason = "marked_by_mistake";

export function VoidPayment({
  payment,
  name,
  month,
  readyReasons,
  onDone,
  onClose,
  finalFocus,
}: {
  payment: PaymentLine;
  /** Whose pay it was. */
  name: string;
  /** The month it paid, "2026-11". */
  month: string;
  /** On the demo, the ready reasons' codes; elsewhere none. */
  readyReasons: readonly string[];
  /** Crossed out, and the pay read again. */
  onDone: () => void;
  /** Ghairi or Esc. */
  onClose: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.payment");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const monthTitle = useMonthTitle();
  const [reason, setReason] = useState("");
  // The form's own check, as the server would refuse it, shown once the person has tried to send.
  const [tried, setTried] = useState(false);

  const crossOut = useMutation({
    mutationFn: (sent: { reason: string }) =>
      answerOf(
        api.POST("/api/v1/staffpay/payslip-payments/{id}/void/", {
          params: { path: { id: payment.id } },
          body: sent,
        }),
      ),
    onSuccess: async () => {
      // The pay read again before the sheet goes: the mutation stays on its way until then (TanStack waits for what
      // this returns), so it closes onto Hajalipwa and Lipa.
      await store.invalidateQueries({ queryKey: PAY });
      onDone();
    },
    // Asked again too: with no answer, it may have been crossed out all the same.
    onError: () => void store.invalidateQueries({ queryKey: PAY }),
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    crossOut.reset();
    setTried(true);
    if (reason.trim() === "") return;
    crossOut.mutate({ reason });
  }

  // The form's own check first, then the server's, beside the box; the rest above the buttons.
  const reasonError =
    tried && reason.trim() === ""
      ? codeMessage(codes, "payment.reason_missing")
      : fieldMessages(crossOut.error).reason;

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("void.title", { name })}
      description={t("about", {
        month: monthTitle(month),
        total: formatMoney(new Decimal(payment.amount)),
      })}
      actionLabel={t("void.action")}
      // Red: what is crossed out is never brought back (sheet.tsx).
      actionKind="danger"
      onAction={send}
      busy={crossOut.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (closure-cancel.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      {readyReasons.length > 0 ? (
        // On the demo: the ready reason to tap, kept as its code, said in words wherever it shows.
        <Choice
          label={t("void.reason")}
          error={reasonError}
          options={readyReasons.map((code) => ({
            value: code,
            label: t(`readyReason.${code as ReadyReason}`),
          }))}
          value={reason === "" ? null : reason}
          onValueChange={setReason}
        />
      ) : (
        <Field
          label={t("void.reason")}
          error={reasonError}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          autoComplete="off"
          maxLength={REASON_LONGEST}
        />
      )}
      {/* What no box names: one's own, a key taken away a moment ago, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(crossOut.error)} />
    </Sheet>
  );
}
