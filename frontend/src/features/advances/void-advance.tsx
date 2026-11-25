// void-advance.tsx — Batilisha: an advance typed wrong, crossed out in a sheet over its own page (WAGE-8):
//
//   ┌──────────────────────────────────┐
//   │ Batilisha TSh 300,000            │
//   │ Juma · Jumatatu 16/11/2026       │
//   │ Sababu    [ Sifuri moja zaidi  ] │
//   │ [ Ghairi ]         [ Batilisha ] │
//   └──────────────────────────────────┘
//
// It stays on the pages, struck through, with who, when and why, and counts for nothing (A2, T2). It is never brought
// back: the right amount is typed again. Anyone who holds the key may, but never on their own (Jack: A): the page offers
// no button there, and the server refuses it all the same (advance.own). On the demo, the reason is the ready one to tap
// (the answer's ready_void_reasons), as a typed one would show to every visitor after them; elsewhere it is typed. The
// server's refusals show beside the reason, or above the buttons. Once done, it waits for the page to be read again
// before it closes, so it is never struck through beside a pay that still counts it.
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
import type { Weekday } from "@/features/attendance/attendance-month";
import { PAY } from "@/features/pay/pay";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney, weekdayOf } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { type AdvanceLine, ADVANCES } from "./advances";

/** The server's longest reason (VoidAdvanceSerializer, 200 characters). */
const REASON_LONGEST = 200;

export function VoidAdvance({
  advance,
  readyReasons,
  onDone,
  onClose,
  finalFocus,
}: {
  advance: AdvanceLine;
  /** On the demo, the ready reason's code; elsewhere none. */
  readyReasons: readonly "wrong_amount"[];
  /** Crossed out, and the page read again. */
  onDone: () => void;
  /** Ghairi or Esc. */
  onClose: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("advances");
  const monthWords = useTranslations("attendanceMonth");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [reason, setReason] = useState("");
  // The form's own check, as the server would refuse it, shown once the person has tried to send.
  const [tried, setTried] = useState(false);

  const crossOut = useMutation({
    mutationFn: (sent: { reason: string }) =>
      answerOf(
        api.POST("/api/v1/staffpay/advances/{id}/void/", {
          params: { path: { id: advance.id } },
          body: sent,
        }),
      ),
    onSuccess: async () => {
      // The pay it came off too (WAGE-2); not waited for, as it isn't on this page.
      void store.invalidateQueries({ queryKey: PAY });
      // The page read again before the sheet goes: the mutation stays on its way until then (TanStack waits for what this
      // returns). A read that fails ends the wait too, and the page shows why.
      await store.invalidateQueries({ queryKey: ADVANCES });
      onDone();
    },
    onError: () => {
      // Asked again too: with no answer, it may have been crossed out all the same, and the page behind the sheet must
      // not go on counting it.
      void store.invalidateQueries({ queryKey: PAY });
      void store.invalidateQueries({ queryKey: ADVANCES });
    },
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    crossOut.reset();
    setTried(true);
    if (reason.trim() === "") return;
    crossOut.mutate({ reason });
  }

  const about = {
    name: advance.display_name,
    day: t("day", {
      weekday: monthWords(
        `weekdays.${String(weekdayOf(advance.date)) as Weekday}`,
      ),
      date: formatDay(advance.date),
    }),
  };
  // The form's own check first, then the server's, beside the box; the rest above the buttons.
  const reasonError =
    tried && reason.trim() === ""
      ? codeMessage(codes, "advance.reason_missing")
      : fieldMessages(crossOut.error).reason;

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("void.title", {
        amount: formatMoney(new Decimal(advance.amount)),
      })}
      description={
        advance.note === ""
          ? t("void.about", about)
          : t("void.aboutWithNote", { ...about, note: advance.note })
      }
      actionLabel={t("void.action")}
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
            label: t(`readyReason.${code}`),
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
      {/* What no box names: one's own, the key taken away a moment ago, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(crossOut.error)} />
    </Sheet>
  );
}
