// add-tap.tsx — Ongeza Ingia au Toka: a manager or the owner adds a tap a worker forgot, in a sheet over the day
// (ATT-13), as Jack pictured it (21 Nov 2026):
//
//   ┌──────────────────────────────────────────┐
//   │ Ongeza Ingia au Toka ya Juma             │
//   │ Alhamisi 19/11/2026                      │
//   │ ( ) Ingia    (•) Toka                    │
//   │ Saa    [ 18:45 ]                         │
//   │ Sababu [ Alisahau kubonyeza Toka       ] │
//   │ [ Ghairi ]                   [ Ongeza ]  │
//   └──────────────────────────────────────────┘
//
// The tap is the attendance book's like a laptop's, with no laptop: the minute typed is on the shop's clock, trusted,
// so an Ingia added at 07:50 takes the late fine, as a real tap would, and the day is worked out again with it (add_tap,
// apps/staffpay/services.py). Toka is picked when the day has an Ingia, Ingia when it has none, as the one most
// likely forgotten. The tap's id is made as the sheet opens, once, so a second tap on Ongeza after an answer lost on
// the way adds one tap, not two (ADR-0007). On the demo, the reason is the ready one to tap (the answer's
// ready_add_reasons, as ATT-6's ready reasons, Jack: A). The server's refusals show beside their box, a minute still to
// come beside the time, or above the buttons: one's own tap, a day that isn't one of the job's, no network.
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
import { clockPart, formatDay, weekdayOf } from "@/lib/format";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import { ATTENDANCE_MONTHS, type Weekday } from "./attendance-month";
import {
  type AttendanceTap,
  WORKER_MONTHS,
  type WorkerAttendance,
} from "./worker-month";

/** The server's longest reason (AddTapSerializer, 200 characters). */
const REASON_LONGEST = 200;

type Kind = AttendanceTap["kind"];

export function AddTap({
  day,
  answer,
  onClose,
}: {
  /** The day, as the shop's date: "2026-11-19". */
  day: string;
  answer: WorkerAttendance;
  onClose: () => void;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  // The one most likely forgotten: a Toka on a day with an Ingia that counts, else an Ingia.
  const [kind, setKind] = useState<Kind>(() =>
    answer.taps.some(
      (tap) => tap.date === day && tap.kind === "in" && tap.voided === null,
    )
      ? "out"
      : "in",
  );
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  // Made once, as the sheet opens: the same id on every try, so a repeat after a lost answer adds one tap (ADR-0007).
  // So a repeat answers the tap the first try made, whatever was changed in the sheet between the two: a time changed
  // after an answer lost is not saved, and the day, read again, shows the time kept, for the manager to fix again.
  const [id] = useState(newId);
  // The form's own checks, as the server would refuse them, shown once the person has tried to send.
  const [tried, setTried] = useState(false);
  const ready = answer.ready_add_reasons;

  const add = useMutation({
    mutationFn: (sent: { kind: Kind; time: string; reason: string }) =>
      answerOf(
        api.POST("/api/v1/staffpay/attendance-taps/", {
          body: { id, staff: answer.worker.staff, date: day, ...sent },
        }),
      ),
    onSuccess: (added) => {
      // The tap on the day at once, from the server's own answer, then the months read again: this worker's, whose day
      // is worked out again with it, in the taps' own order, and the month page's, whose counts and list may change.
      store.setQueryData<WorkerAttendance>(
        [...WORKER_MONTHS, answer.worker.staff, answer.month],
        (kept) =>
          kept && {
            ...kept,
            taps: [...kept.taps.filter((each) => each.id !== added.id), added],
          },
      );
      void store.invalidateQueries({ queryKey: WORKER_MONTHS });
      void store.invalidateQueries({ queryKey: ATTENDANCE_MONTHS });
      onClose();
    },
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    add.reset();
    setTried(true);
    if (time === "" || reason.trim() === "") return;
    add.mutate({ kind, time, reason });
  }

  // The form's own checks first, then the server's, beside their boxes; the rest above the buttons (decide-day.tsx).
  const byField = fieldMessages(add.error);
  const timeError = tried && time === "" ? t("timeMissing") : byField.time;
  const reasonError =
    tried && reason.trim() === ""
      ? codeMessage(codes, "tap.reason_missing")
      : byField.reason;

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("addSheetTitle", { name: answer.worker.display_name })}
      description={t("sheetAbout", {
        weekday: monthWords(`weekdays.${String(weekdayOf(day)) as Weekday}`),
        date: formatDay(day),
      })}
      actionLabel={t("addTapSave")}
      onAction={send}
      busy={add.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (closure-cancel.tsx).
      actionDisabled={!online}
    >
      <Choice
        label={t("addKindLabel")}
        error={byField.kind}
        options={(["in", "out"] as const).map((each) => ({
          value: each,
          label: t(`tapKind.${each}`),
        }))}
        value={kind}
        onValueChange={(value) => setKind(value as Kind)}
      />
      {/* The phone's own time box, which shows the time as the phone is set, often with AM/PM: so 06:45 could be
          picked for the evening. Its hint says the tap back as the day will show it, 24 hours with its part of the day,
          "Toka 18:45 jioni", before Ongeza (ATT-13's review); the box always hands the page 24 hours, "18:45". */}
      <Field
        label={t("timeLabel")}
        hint={
          time === ""
            ? t("timeHint")
            : t("timeSaid", {
                tap: t("tapLineNoLaptop", {
                  kind: t(`tapKind.${kind}`),
                  time: attendance("timeOfDay", {
                    time,
                    part: clockPart(time),
                  }),
                }),
              })
        }
        error={timeError}
        type="time"
        value={time}
        onChange={(event) => setTime(event.target.value)}
      />
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
      {/* What no box names: one's own tap, a day that isn't one of the job's, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(add.error)} />
    </Sheet>
  );
}
