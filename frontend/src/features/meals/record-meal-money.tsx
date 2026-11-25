// record-meal-money.tsx — Andika hela ya chakula: the button, and the sheet that types what the meals of a day cost
// (WAGE-7), as Jack pictured it (24 Nov 2026), on the list and on one day's own page:
//
//   ┌──────────────────────────────────┐
//   │ Andika hela ya chakula           │
//   │ Siku                [ 24/11/2026 ]│
//   │ Kiasi (TSh)         [ 9000       ]│
//   │ Maelezo (si lazima) [ Unga       ]│
//   │ [ Ghairi ]           [ Hifadhi ] │
//   └──────────────────────────────────┘
//
// It starts on the day it is opened for: today on the list, the day itself on a day's page. Several a day add up, so it
// never asks what is there already. Who may, and what a day takes, are the server's (record_meal_money,
// apps/staffpay/services.py); what the sheet can see itself is said at once, beside its box, in the server's own
// sentences: an empty day, one to come, a Sunday, an amount that isn't whole shillings above 0. On the demo a note isn't
// kept (demo.no_note), said beside its box.
//
// The id is made here and sent again with every try of the same money (ADR-0007): a save whose answer the network lost,
// tried again, gets the row the first made, never a second. Anything changed is another row, under a new id, as the
// server answers an old id with the row it kept, whatever the new try carries: the list, read again, shows both, for the
// person to cross out the one they didn't mean. Once saved, the sheet closes and a line says what was written, with the
// keyboard on it, as the day may be in a month the list doesn't show.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import type { Weekday } from "@/features/attendance/attendance-month";
import { WORKER_MONTHS } from "@/features/attendance/worker-month";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney, weekdayOf } from "@/lib/format";
import { newId } from "@/lib/ids";
import { typedAmount } from "@/lib/typed-amount";
import { useOnline } from "@/offline/network";

import { MEAL_MONEY } from "./meal-money";

/** The server's longest note (MealMoney.note, 200 characters). */
const NOTE_LONGEST = 200;

/** Sunday, as JavaScript numbers the days of the week. */
const SUNDAY = 0;

// The fields with a box, beside which their refusals show. A refusal of any other field, a clashing id, shows above the
// buttons.
const ON_A_BOX = new Set(["date", "amount", "note"]);

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { date?: string; amount?: string };

export function RecordMealMoney({
  day,
  today,
}: {
  /** The day the sheet starts on. */
  day: string;
  /** The shop's today, as the server said it: no day after it has any meals yet. */
  today: string;
}) {
  const t = useTranslations("mealMoney.record");
  const [open, setOpen] = useState(false);
  // The line that says what the last save wrote.
  const [news, setNews] = useState<string | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const newsLine = useRef<HTMLDivElement>(null);
  // Whether the last close was a save, for the sheet to give the keyboard to the line: read as the sheet goes, after the
  // draw that took it away, so a ref, not the state (worker-pay.tsx).
  const afterSave = useRef(false);

  return (
    <div className="grid gap-3">
      <Button
        ref={button}
        onClick={() => {
          afterSave.current = false;
          setNews(null);
          setOpen(true);
        }}
      >
        {t("title")}
      </Button>
      {/* Always on the page, empty and hidden until something happens: a status box is read when its words change, and
          one that appears with its words already in it may not be read at all (worker-roles.tsx). */}
      <div
        ref={newsLine}
        tabIndex={-1}
        className={news ? "outline-none" : "sr-only"}
      >
        <Alert kind="info">
          {news ? <AlertDescription>{news}</AlertDescription> : null}
        </Alert>
      </div>
      {open ? (
        <RecordSheet
          startingDay={day}
          today={today}
          onSaved={(sentence) => {
            afterSave.current = true;
            setOpen(false);
            setNews(sentence);
          }}
          onClose={() => setOpen(false)}
          finalFocus={() =>
            afterSave.current ? newsLine.current : button.current
          }
        />
      ) : null}
    </div>
  );
}

function RecordSheet({
  startingDay,
  today,
  onSaved,
  onClose,
  finalFocus,
}: {
  startingDay: string;
  today: string;
  /** Saved: the line that says what, in the person's words. */
  onSaved: (sentence: string) => void;
  onClose: () => void;
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("mealMoney.record");
  const monthWords = useTranslations("attendanceMonth");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [date, setDate] = useState(startingDay);
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const [own, setOwn] = useState<Checks>({});
  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);

  const save = useMutation({
    mutationFn: (body: {
      id: string;
      date: string;
      amount: string;
      note: string;
    }) => answerOf(api.POST("/api/v1/staffpay/meal-money/", { body })),
    onSuccess: (row) =>
      onSaved(
        t("saved", {
          amount: formatMoney(new Decimal(row.amount)),
          weekday: monthWords(
            `weekdays.${String(weekdayOf(row.date)) as Weekday}`,
          ),
          date: formatDay(row.date),
        }),
      ),
    onSettled: () => {
      // The days asked again, whatever the answer: with none, the row may have been made all the same, and the list then
      // shows it. And the workers' months, whose days' shares move with the money.
      void store.invalidateQueries({ queryKey: MEAL_MONEY });
      void store.invalidateQueries({ queryKey: WORKER_MONTHS });
    },
  });

  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    const amount = typedAmount(typed);
    // Days as text sort as days do. The box offers no day to come; one typed by hand is said here, as the server would.
    const checks: Checks = {
      date:
        date === ""
          ? "required"
          : date > today
            ? "meal_money.in_future"
            : weekdayOf(date) === SUNDAY
              ? "meal_money.not_working_day"
              : undefined,
      amount: amount === null ? "meal_money.amount_invalid" : undefined,
    };
    setOwn(checks);
    if (amount === null || checks.date !== undefined) return;
    const body = { date, amount, note };
    const carried = JSON.stringify(body);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({ id: lastSend.current.id, ...body });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's; a field with no box above the
  // buttons, in its own sentence; a refusal of the whole request is ApiErrorAlert's (pay-rate-form.tsx).
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const noBox = Object.entries(byField)
    .filter(([field]) => !ON_A_BOX.has(field))
    .map(([, sentence]) => sentence);

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("title")}
      actionLabel={t("save")}
      onAction={send}
      busy={save.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      <Field
        label={t("date")}
        error={said(own.date) ?? byField.date}
        type="date"
        max={today}
        value={date}
        onChange={(event) => setDate(event.target.value)}
      />
      <Field
        label={t("amount")}
        error={said(own.amount) ?? byField.amount}
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        // Digits only on a phone's keypad: the shop's money is whole shillings.
        inputMode="numeric"
        autoComplete="off"
      />
      <Field
        label={t("note")}
        error={byField.note}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        autoComplete="off"
        maxLength={NOTE_LONGEST}
      />
      {noBox.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{noBox.join(" ")}</AlertDescription>
        </Alert>
      ) : (
        // What no field names: who may, no network, the server's own problem.
        <ApiErrorAlert error={aboutTheWholeRequest(save.error)} />
      )}
    </Sheet>
  );
}
