// decide-day.tsx — Amua siku hii: a manager or the owner decides a worker's day in a sheet over the day (ATT-6), as
// Jack pictured it (20 Nov 2026):
//
//   ┌──────────────────────────────────┐
//   │ Amua siku ya Juma                │
//   │ Alhamisi 12/11/2026 · Ingia 07:50 asubuhi
//   │ Siku hii ilikuwa                 │
//   │ ( ) Siku kamili                  │
//   │ ( ) Amechelewa · faini TSh 500   │
//   │ ( ) Nusu siku · faini TSh 500    │
//   │ ( ) Kazi ya ofisi · analipwa siku kamili
//   │ ( ) Ruhusa · halipwi             │
//   │ ( ) Hakuja bila taarifa · halipwi│
//   │ Sababu [ Alisahau kubonyeza Toka ]│
//   │ [ Ghairi ]     [ Hifadhi uamuzi ]│
//   └──────────────────────────────────┘
//
// The choices, and each one's fine, are the server's (day_choices, apps/staffpay/calculations.py): the page shows them
// as they come, so Amechelewa never shows on a day it can't take, and no fine is worked out here (rule 4). On the demo,
// the reason is one of three ready ones to tap (the answer's ready_reasons, Jack: A), as a typed one would show to
// every visitor after them; elsewhere it is typed. Deciding again (Badilisha uamuzi) opens with the decision picked, and asks
// for a new reason, as each decision says its own why.
//
// The decision is sent with when the decision on the screen as the sheet opened was made, or none (`replaces`), read
// once as it opens: if someone else decided the day meanwhile, the server refuses it (409 version_conflict), the sheet
// says so, and the month is read again, so the day behind shows what they decided once the sheet is closed. Its other
// refusals show beside their box, or above the buttons.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { MEAL_MONEY } from "@/features/meals/meal-money";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { clockPart, formatDay, formatMoney, weekdayOf } from "@/lib/format";
import { useOnline } from "@/offline/network";

import { ATTENDANCE_MONTHS, type Weekday } from "./attendance-month";
import {
  WORKER_MONTHS,
  type WorkerAttendance,
  type WorkerDay,
} from "./worker-month";

type DayOption = components["schemas"]["DayOption"];
type DayDecision = components["schemas"]["DayDecision"];
type DayChoice = DayOption["choice"];

/** The server's longest reason (DecideDaySerializer, 200 characters). */
const REASON_LONGEST = 200;

/** The sheet's choice a decision was made with: its absence's kind, or its status (DECISION_OF, the server's). */
export function choiceOf(decision: DayDecision | null): DayChoice | null {
  if (decision === null) return null;
  if (decision.absence_type !== null) return decision.absence_type;
  // An absent decision always has its kind (the table's own rule, decision_fits_its_status): none picked otherwise.
  return decision.status === "absent" ? null : decision.status;
}

export function DecideDay({
  day,
  answer,
  open,
  onClose,
}: {
  day: WorkerDay;
  answer: WorkerAttendance;
  open: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  // The decision on the screen, picked again when it is changed; none for a first one.
  const [choice, setChoice] = useState<DayChoice | null>(
    choiceOf(day.decision),
  );
  const [reason, setReason] = useState("");
  // The decision on the screen as the sheet opened, or none, read once, never again: the month is asked again each
  // minute while the page is open (worker-month.ts), and hands this sheet a newer day. Read at the save instead, a
  // decision someone else made meanwhile would be sent as the one this person saw, and written over without a word
  // (ATT-6's review). Sent as `replaces`, it is refused (409) instead: the person closes the sheet and sees it.
  const [replaces] = useState(() => day.decision?.at ?? null);
  // The form's own checks, as the server would refuse them, shown once the person has tried to send.
  const [tried, setTried] = useState(false);
  const ready = answer.ready_reasons;

  const decide = useMutation({
    mutationFn: (sent: { choice: DayChoice; reason: string }) =>
      answerOf(
        api.POST("/api/v1/staffpay/attendance-days/{id}/decide/", {
          params: { path: { id: day.id } },
          body: { ...sent, replaces },
        }),
      ),
    onSuccess: (decision) => {
      // The decision on the day at once, from the server's own answer, then the months read again: this worker's,
      // whose counts change, and the month page's, whose Zinahitaji uamuzi loses the day.
      store.setQueryData<WorkerAttendance>(
        [...WORKER_MONTHS, answer.worker.staff, answer.month],
        (kept) =>
          kept && {
            ...kept,
            days: kept.days.map((each) =>
              each.id === day.id ? { ...each, decision } : each,
            ),
          },
      );
      void store.invalidateQueries({ queryKey: WORKER_MONTHS });
      void store.invalidateQueries({ queryKey: ATTENDANCE_MONTHS });
      // And the meal money: who came shares it, so the date is split again (WAGE-7).
      void store.invalidateQueries({ queryKey: MEAL_MONEY });
      onClose();
    },
    onError: (error) => {
      // Someone decided it meanwhile: the month read again, so the day behind the sheet shows what they decided.
      if (error instanceof ApiRefusal && error.status === 409)
        void store.invalidateQueries({ queryKey: WORKER_MONTHS });
    },
  });

  function send() {
    // Each try shows only what it finds, never the last one's refusal (setting-form.tsx).
    decide.reset();
    setTried(true);
    if (choice === null || reason.trim() === "") return;
    decide.mutate({ choice, reason });
  }

  // Whose and which day, as the sheet's title and the line under it say: "Alhamisi 12/11/2026 · Ingia 07:50 asubuhi".
  const date = {
    weekday: monthWords(`weekdays.${String(weekdayOf(day.date)) as Weekday}`),
    date: formatDay(day.date),
  };
  const about =
    day.first_in === null
      ? t("sheetAbout", date)
      : t("sheetAboutIn", {
          ...date,
          time: attendance("timeOfDay", {
            time: day.first_in,
            part: clockPart(day.first_in),
          }),
        });

  // The server's refusals beside their boxes, the form's own first; the rest above the buttons (closure-cancel.tsx).
  const byField = fieldMessages(decide.error);
  const choiceError = tried && choice === null ? t("pickOne") : byField.choice;
  const reasonError =
    tried && reason.trim() === ""
      ? codeMessage(codes, "day.reason_missing")
      : byField.reason;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={t("sheetTitle", { name: answer.worker.display_name })}
      description={about}
      actionLabel={t("save")}
      onAction={send}
      busy={decide.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (closure-cancel.tsx).
      actionDisabled={!online}
    >
      <Choice
        label={t("choiceLabel")}
        error={choiceError}
        options={day.choices.map((option) => ({
          value: option.choice,
          label: optionWords(option, t),
        }))}
        value={choice}
        onValueChange={(value) => setChoice(value as DayChoice)}
      />
      {ready.length > 0 ? (
        // On the demo: three ready reasons to tap, kept as their codes, said in words wherever they show.
        <Choice
          label={t("reasonLabel")}
          hint={t("readyHint")}
          error={reasonError}
          options={ready.map((code) => ({
            value: code,
            label: t(`readyReason.${code}`),
          }))}
          value={reason === "" ? null : reason}
          onValueChange={setReason}
        />
      ) : (
        <Field
          label={t("reasonLabel")}
          hint={t("reasonHint")}
          error={reasonError}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          autoComplete="off"
          maxLength={REASON_LONGEST}
        />
      )}
      {/* What no box names: someone decided it meanwhile, the person's own day, no network, the server's problem. */}
      <ApiErrorAlert error={aboutTheWholeRequest(decide.error)} />
    </Sheet>
  );
}

/** A line of the sheet, its fine said where it has one: "Amechelewa · faini TSh 500", "Ruhusa · halipwi". */
function optionWords(
  option: DayOption,
  t: ReturnType<typeof useTranslations<"attendanceWorker">>,
): string {
  const fine = new Decimal(option.fine);
  switch (option.choice) {
    case "office_duty":
    case "permission":
    case "no_show":
      return t(`option.${option.choice}`);
    default:
      return fine.gt(new Decimal("0"))
        ? t("option.withFine", {
            decision: t(`decision.${option.choice}`),
            amount: formatMoney(fine),
          })
        : t(`decision.${option.choice}`);
  }
}
