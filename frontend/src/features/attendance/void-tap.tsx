// void-tap.tsx — Batilisha: a manager or the owner crosses out a tap made by mistake, in a sheet over the day (ATT-13),
// as Jack pictured it (21 Nov 2026):
//
//   ┌──────────────────────────────────────────┐
//   │ Batilisha Toka ya Juma                   │
//   │ Alhamisi 19/11/2026 · Toka 10:00 asubuhi │
//   │ Sababu [ Alibonyeza kwa makosa         ] │
//   │ [ Ghairi ]                [ Batilisha ]  │
//   └──────────────────────────────────────────┘
//
// The tap stays on the day, struck through, with who, when and why, and counts for nothing (A2, T2). It is never
// brought back: a mistake is mended by adding a tap (add-tap.tsx). Who may, and on which taps, is the server's
// (void_tap, apps/staffpay/services/attendance.py): the page offers the button only where it would be taken, and the
// server checks again. On the demo, the reason is the ready one to tap (the answer's ready_void_reasons), as a typed one
// would show to every visitor after them (as ATT-6's ready reasons, Jack: A); elsewhere it is typed. The server's
// refusals show beside the reason, or above the buttons: one's own tap, no network, the server's problem.
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
import { MEAL_MONEY } from "@/features/meals/meal-money";
import { PAY } from "@/features/pay/pay";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { formatDay, weekdayOf } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { ATTENDANCE_MONTHS, type Weekday } from "./attendance-month";
import {
  type AttendanceTap,
  WORKER_MONTHS,
  type WorkerAttendance,
} from "./worker-month";

/** The server's longest reason (VoidTapSerializer, 200 characters). */
const REASON_LONGEST = 200;

export function VoidTap({
  tap,
  said,
  answer,
  onClose,
}: {
  tap: AttendanceTap;
  /** The tap as the day says it: "Toka 10:00 asubuhi" (worker-day.tsx's Tap). */
  said: { kind: string; time: string };
  answer: WorkerAttendance;
  onClose: () => void;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [reason, setReason] = useState("");
  // The form's own check, as the server would refuse it, shown once the person has tried to send.
  const [tried, setTried] = useState(false);
  const ready = answer.ready_void_reasons;

  const crossOut = useMutation({
    mutationFn: (sent: { reason: string }) =>
      answerOf(
        api.POST("/api/v1/staffpay/attendance-taps/{id}/void/", {
          params: { path: { id: tap.id } },
          body: sent,
        }),
      ),
    onSuccess: (crossed) => {
      // The tap crossed out on the day at once, from the server's own answer, then the months read again: this
      // worker's, whose day is worked out again without it, and the month page's, whose counts and list may change.
      store.setQueryData<WorkerAttendance>(
        [...WORKER_MONTHS, answer.worker.staff, answer.month],
        (kept) =>
          kept && {
            ...kept,
            taps: kept.taps.map((each) =>
              each.id === tap.id ? crossed : each,
            ),
          },
      );
      void store.invalidateQueries({ queryKey: WORKER_MONTHS });
      void store.invalidateQueries({ queryKey: ATTENDANCE_MONTHS });
      // And the meal money: who came shares it, so the date is split again (WAGE-7).
      void store.invalidateQueries({ queryKey: MEAL_MONEY });
      onClose();
    },
    onSettled: () => {
      // The pay, whatever the answer (WAGE-2): with none, or one the server failed at, it may have been saved all the
      // same, and an old total on the screen is money paid wrong (the review).
      void store.invalidateQueries({ queryKey: PAY });
    },
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    crossOut.reset();
    setTried(true);
    if (reason.trim() === "") return;
    crossOut.mutate({ reason });
  }

  // The day and the tap, as the line under the title says them: "Alhamisi 19/11/2026 · Toka 10:00 asubuhi".
  const about = t("voidSheetAbout", {
    weekday: monthWords(`weekdays.${String(weekdayOf(tap.date)) as Weekday}`),
    date: formatDay(tap.date),
    tap: t("tapLineNoLaptop", said),
  });
  // The form's own check first, then the server's, beside the box; the rest above the buttons (decide-day.tsx).
  const reasonError =
    tried && reason.trim() === ""
      ? codeMessage(codes, "tap.reason_missing")
      : fieldMessages(crossOut.error).reason;

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("voidSheetTitle", {
        kind: said.kind,
        name: answer.worker.display_name,
      })}
      description={about}
      actionLabel={t("voidTap")}
      onAction={send}
      busy={crossOut.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (closure-cancel.tsx).
      actionDisabled={!online}
    >
      {ready.length > 0 ? (
        // On the demo: the ready reason to tap, kept as its code, said in words wherever it shows.
        <Choice
          label={t("reasonLabel")}
          hint={t("readyHint")}
          error={reasonError}
          options={ready.map((code) => ({
            value: code,
            label: t(`readyTapReason.${code}`),
          }))}
          value={reason === "" ? null : reason}
          onValueChange={setReason}
        />
      ) : (
        <Field
          label={t("reasonLabel")}
          hint={t("fixHint")}
          error={reasonError}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          autoComplete="off"
          maxLength={REASON_LONGEST}
        />
      )}
      {/* What no box names: one's own tap, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(crossOut.error)} />
    </Sheet>
  );
}
