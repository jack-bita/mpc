// pay-sheet.tsx — Lipa: a payslip handed out, in a sheet over Mishahara or the worker's own pay page (WAGE-9), as Jack
// pictured it (26 Nov 2026):
//
//   ┌──────────────────────────────────┐        ┌──────────────────────────────────┐
//   │ Lipa Asha                        │        │ Lipa Asha                        │
//   │ Novemba 2026 · TSh 152,000       │        │ Novemba 2026 · TSh 152,000       │
//   │ Amelipwa kwa:                    │        │ Amelipwa kwa:                    │
//   │ (•) Taslimu                      │        │ ( ) Taslimu                      │
//   │ ( ) M-Pesa                       │        │ (•) M-Pesa                       │
//   │ ( ) Benki                        │        │ ( ) Benki                        │
//   │ Sahihi ya Asha                   │        │ Namba ya muamala                 │
//   │ ┌──────────────────────────────┐ │        │ [ QK7H2M9XPL                   ] │
//   │ │     (Asha draws here)        │ │        │                                  │
//   │ └──────────────────────────────┘ │        │                                  │
//   │                 [ Futa sahihi ]  │        │                                  │
//   │ [ Ghairi ]        [ Nimemlipa ]  │        │ [ Ghairi ]        [ Nimemlipa ]  │
//   └──────────────────────────────────┘        └──────────────────────────────────┘
//
// The whole amount, always (Jack: A). Nimemlipa stays off until Asha has drawn her signature, or the number is typed
// (Jack: A). In cash the drawing is the request's body, as a worker's photo is (PPL-9); on the demo, which keeps no
// signature (`keeps_signatures`), the visitor draws all the same, and the payment goes with none, as the sheet says.
//
// The request's ids are made once, as the sheet opens: the same try sent again, its answer lost, is the same payment and
// the same signature (ADR-0007). Once paid, the pay is read again before the sheet closes, so it never closes onto a line
// that still says Hajalipwa. The server's refusals show beside the number's box, or above the buttons.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import {
  SignaturePad,
  type SignaturePadHandle,
} from "@/components/design/signature-pad";
import { newId } from "@/lib/ids";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { useMonthTitle } from "./approve-sheet";
import { PAY, type WorkerPay } from "./pay";
import {
  LONGEST_REFERENCE,
  METHODS,
  type PaymentLine,
  type PaymentMethod,
} from "./payments";

export function PaySheet({
  worker,
  month,
  keepsSignatures,
  onDone,
  onClose,
  finalFocus,
}: {
  /** The worker's line, with its payslip. */
  worker: WorkerPay;
  /** The month it pays, "2026-11". */
  month: string;
  /** Whether cash goes with its signature: false on the demo, which keeps none. */
  keepsSignatures: boolean;
  /** Paid, and the pay read again. */
  onDone: () => void;
  /** Ghairi or Esc. */
  onClose: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.payment");
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const monthTitle = useMonthTitle();
  // Made once, as the sheet opens (ADR-0007).
  const [paymentId] = useState(newId);
  const [signatureId] = useState(newId);
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [reference, setReference] = useState("");
  const [drawn, setDrawn] = useState(false);
  const pad = useRef<SignaturePadHandle>(null);
  // Which payslip, kept as the sheet opened: the page asks itself again meanwhile, and the line it shows may move.
  const [payslip] = useState(worker.payslip ?? "");

  const pay = useMutation({
    mutationFn: async (): Promise<PaymentLine> => {
      if (method === "cash" && keepsSignatures) {
        const drawing = await pad.current?.picture();
        // Nimemlipa is off until something is drawn, so there is always one here; said plainly if the browser lost it.
        if (!drawing) throw new Error("The signature could not be read.");
        return answerOf(
          api.PUT("/api/v1/staffpay/payslips/{id}/pay-cash/", {
            params: {
              path: { id: payslip },
              query: { id: paymentId, signature: signatureId },
            },
            // The drawing's bytes alone, past the client's JSON, as a worker's photo goes (photo-sheet.tsx): fetch gives
            // an ArrayBuffer its length, so the route never answers 411 for want of one.
            body: (await drawing.arrayBuffer()) as unknown as string,
            bodySerializer: (body) => body,
            headers: { "Content-Type": drawing.type },
          }),
        );
      }
      return answerOf(
        api.POST("/api/v1/staffpay/payslips/{id}/pay/", {
          params: { path: { id: payslip } },
          body: {
            id: paymentId,
            method,
            reference: method === "cash" ? "" : reference,
          },
        }),
      );
    },
    // Nothing of the signature outlives the sheet in the store, which everyone on this phone shares (UI-4).
    gcTime: 0,
    onSuccess: async () => {
      // The mutation stays on its way until the pay is read again (TanStack waits for what this returns), so the sheet
      // stays held, and closes onto Amelipwa.
      await store.invalidateQueries({ queryKey: PAY });
      onDone();
    },
    // Asked again too: with no answer, it may have been paid all the same, and the page must not go on offering Lipa.
    onError: () => void store.invalidateQueries({ queryKey: PAY }),
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    pay.reset();
    pay.mutate();
  }

  const ready = method === "cash" ? drawn : reference.trim() !== "";
  return (
    <Sheet
      open
      onClose={onClose}
      title={t("title", { name: worker.display_name })}
      description={t("about", {
        month: monthTitle(month),
        total: formatMoney(new Decimal(worker.to_hand_out)),
      })}
      actionLabel={t("action")}
      onAction={send}
      busy={pay.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done; and nothing is ready to send until she
      // has signed, or the number is typed (Jack: A).
      actionDisabled={!online || !ready}
      finalFocus={finalFocus}
    >
      <Choice
        label={t("method")}
        options={METHODS.map((way) => ({
          value: way,
          label: t(`methods.${way}`),
        }))}
        value={method}
        onValueChange={(way) => setMethod(way as PaymentMethod)}
        disabled={pay.isPending}
      />
      {method === "cash" ? (
        <>
          <SignaturePad
            ref={pad}
            label={t("signature", { name: worker.display_name })}
            hint={t("signatureHint", { name: worker.display_name })}
            onDrawnChange={setDrawn}
            disabled={pay.isPending}
          />
          {keepsSignatures ? null : (
            <p className="text-muted-foreground">{t("demoSignature")}</p>
          )}
        </>
      ) : (
        <Field
          label={t("reference")}
          value={reference}
          onChange={(event) => setReference(event.target.value)}
          maxLength={LONGEST_REFERENCE}
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          error={fieldMessages(pay.error).reference}
          disabled={pay.isPending}
        />
      )}
      {/* What the server refused of the whole payment: paid already, one's own, a key taken away, no network. */}
      <ApiErrorAlert error={aboutTheWholeRequest(pay.error)} />
    </Sheet>
  );
}
