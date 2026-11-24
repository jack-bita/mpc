// void-meal-money.tsx — Batilisha: meal money typed wrong, crossed out in a sheet over the day's page (WAGE-7), as Jack
// pictured it (24 Nov 2026):
//
//   ┌──────────────────────────────────┐
//   │ Batilisha TSh 30,000             │
//   │ Jumatatu 23/11/2026 · Nyama      │
//   │ Sababu    [ Sifuri moja zaidi  ] │
//   │ [ Ghairi ]         [ Batilisha ] │
//   └──────────────────────────────────┘
//
// The row stays on the day, struck through, with who, when and why, and counts for nothing (A2, T2). It is never brought
// back: the right amount is typed again. Anyone who holds the key may, on any row. On the demo, the reason is the ready
// one to tap (the answer's ready_void_reasons), as a typed one would show to every visitor after them; elsewhere it is
// typed. The server's refusals show beside the reason, or above the buttons. Once done, it waits for the day to be read
// again before it closes, so the row is never struck through beside a total that still counts it.
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
import { WORKER_MONTHS } from "@/features/attendance/worker-month";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney, weekdayOf } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { MEAL_MONEY, type MealMoneyLine } from "./meal-money";

/** The server's longest reason (VoidMealMoneySerializer, 200 characters). */
const REASON_LONGEST = 200;

export function VoidMealMoney({
  row,
  readyReasons,
  onDone,
  onClose,
  finalFocus,
}: {
  row: MealMoneyLine;
  /** On the demo, the ready reason's code; elsewhere none. */
  readyReasons: readonly "wrong_amount"[];
  /** Crossed out, and the day read again. */
  onDone: () => void;
  /** Ghairi or Esc. */
  onClose: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("mealMoney");
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
        api.POST("/api/v1/staffpay/meal-money/{id}/void/", {
          params: { path: { id: row.id } },
          body: sent,
        }),
      ),
    onSuccess: async () => {
      // The workers' months too, whose days' shares move with the money; not waited for, as none is on this page.
      void store.invalidateQueries({ queryKey: WORKER_MONTHS });
      // The day read again before the sheet goes: the mutation stays on its way until then (TanStack waits for what
      // this returns). A read that fails ends the wait too, and the page shows why.
      await store.invalidateQueries({ queryKey: MEAL_MONEY });
      onDone();
    },
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    crossOut.reset();
    setTried(true);
    if (reason.trim() === "") return;
    crossOut.mutate({ reason });
  }

  const amount = formatMoney(new Decimal(row.amount));
  const day = t("day", {
    weekday: monthWords(`weekdays.${String(weekdayOf(row.date)) as Weekday}`),
    date: formatDay(row.date),
  });
  // The form's own check first, then the server's, beside the box; the rest above the buttons.
  const reasonError =
    tried && reason.trim() === ""
      ? codeMessage(codes, "meal_money.reason_missing")
      : fieldMessages(crossOut.error).reason;

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("void.title", { amount })}
      description={
        row.note === "" ? day : t("void.about", { day, note: row.note })
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
      {/* What no box names: the key taken away a moment ago, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(crossOut.error)} />
    </Sheet>
  );
}
