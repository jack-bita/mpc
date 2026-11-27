// void-correction.tsx — Batilisha of a correction typed wrong (WAGE-10), in a sheet its line on the pay opens, and the
// corrections crossed out, struck through under the lines, as Jack pictured them (27 Nov 2026):
//
//   ┌────────────────────────────────────────────┐
//   │ Marekebisho ya Juma · + 90,000             │
//   │ Desemba 2026                               │
//   │ Sababu: Novemba: siku ya 12/11 haikuhesabiwa│
//   │ Imeandikwa na Baba · 03/12/2026 10:05 asubuhi│
//   │ Sababu ya kubatilisha [ Kiasi kimekosewa  ] │
//   │ [ Ghairi ]                  [ Batilisha ]  │
//   └────────────────────────────────────────────┘
//
//   Marekebisho yaliyobatilishwa
//   ~~Marekebisho: Novemba: siku ya 12/11 haikuhesabiwa   + 90,000~~
//   Imebatilishwa na Baba · 03/12/2026 10:20 asubuhi: Kiasi kimekosewa
//
// It stays, struck through, with who, when and why, and counts for nothing (T2); the right one is then typed again.
// Never brought back. Whoever approves pay may, but never on their own (Jack: A), and only while its month is open: the
// page opens the sheet only then (offersCorrection), and the server refuses it all the same. On the demo, the reason is
// the ready one to tap (the answer's correction_void_reasons), as typed words would show to every visitor after. Once
// done, the pay is read again before the sheet closes, so it never closes onto a line that still counts.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type RefObject, useId, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { dayPart, formatDate, formatTime } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { useMonthTitle } from "./approve-sheet";
import { type CorrectionLine, useReasonWords } from "./corrections";
import { PAY } from "./pay";
import { useSignedAmount } from "./pay-lines";

/** The server's longest reason (VoidCorrectionSerializer, 200 characters). */
const REASON_LONGEST = 200;

/** A moment as the pay pages say it, on the shop's clock: "03/12/2026", "10:05 asubuhi". */
function useWhen(timezone: string): (at: string) => {
  date: string;
  time: string;
} {
  const attendance = useTranslations("attendance");
  return (at) => ({
    date: formatDate(at, timezone),
    time: attendance("timeOfDay", {
      time: formatTime(at, timezone),
      part: dayPart(at, timezone),
    }),
  });
}

export function VoidCorrection({
  line,
  name,
  month,
  timezone,
  readyReasons,
  onDone,
  onClose,
  finalFocus,
}: {
  line: CorrectionLine;
  /** Whose pay it corrects. */
  name: string;
  /** The month whose pay it is in, "2026-12". */
  month: string;
  /** The shop's, for when it was typed. */
  timezone: string;
  /** On the demo, the ready reasons' codes; elsewhere none. */
  readyReasons: readonly string[];
  /** Crossed out, and the pay read again. */
  onDone: () => void;
  /** Ghairi or Esc. */
  onClose: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.correction");
  const codes = useCodeWords();
  const reasonWords = useReasonWords();
  const signed = useSignedAmount();
  const when = useWhen(timezone);
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
        api.POST("/api/v1/staffpay/pay-corrections/{id}/void/", {
          params: { path: { id: line.id } },
          body: sent,
        }),
      ),
    onSuccess: async () => {
      // The pay read again before the sheet goes: the mutation stays on its way until then (TanStack waits for what
      // this returns), so it closes onto the total without it, and the line struck through below (void-payment.tsx).
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
      ? codeMessage(codes, "correction.reason_missing")
      : fieldMessages(crossOut.error).reason;

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("void.title", { name, amount: signed(line.amount) })}
      description={monthTitle(month)}
      actionLabel={t("void.action")}
      // Red: what is crossed out is never brought back (sheet.tsx).
      actionKind="danger"
      onAction={send}
      busy={crossOut.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (closure-cancel.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      <p>{t("reasonSaid", { reason: reasonWords(line.reason) })}</p>
      <p className="text-muted-foreground">
        {t("typedBy", { by: line.by, ...when(line.at) })}
      </p>
      {readyReasons.length > 0 ? (
        // On the demo: the ready reason to tap, kept as its code, said in words wherever it shows.
        <Choice
          label={t("void.reason")}
          error={reasonError}
          options={readyReasons.map((code) => ({
            value: code,
            label: reasonWords(code),
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
      {/* What no box names: one's own, a month approved meanwhile, a key taken away, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(crossOut.error)} />
    </Sheet>
  );
}

/** The corrections crossed out, struck through, each with who, when and why, under the lines, in the order typed. Always
 * on the page, empty and hidden while there is none: the keyboard goes to it as a Batilisha's sheet closes, which may be
 * a moment before the page has drawn the line in it (payslip-payments.tsx's "now" line). */
export function CrossedOutCorrections({
  corrections,
  timezone,
  place,
}: {
  corrections: CorrectionLine[];
  timezone: string;
  place: RefObject<HTMLDivElement | null>;
}) {
  const t = useTranslations("pay.correction");
  const reasonWords = useReasonWords();
  const signed = useSignedAmount();
  const when = useWhen(timezone);
  const id = useId();
  const crossed = corrections.filter((line) => line.voided !== null);
  return (
    <div
      ref={place}
      tabIndex={-1}
      className={crossed.length === 0 ? "sr-only" : "outline-none"}
    >
      {crossed.length === 0 ? null : (
        <section className="grid gap-3" aria-labelledby={id}>
          <h3 id={id} className="font-semibold">
            {t("crossedOut")}
          </h3>
          {crossed.map((line) => (
            <div key={line.id} className="grid gap-1">
              <p className="flex justify-between gap-3 text-muted-foreground tabular-nums">
                <s>{t("line", { reason: reasonWords(line.reason) })}</s>
                <s className="whitespace-nowrap">{signed(line.amount)}</s>
              </p>
              {line.voided === null ? null : (
                <p>
                  {t("voidedBy", {
                    by: line.voided.by,
                    ...when(line.voided.at),
                    reason: reasonWords(line.voided.reason),
                  })}
                </p>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
