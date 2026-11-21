// pay-rate-form.tsx — Weka malipo and Badilisha malipo (WAGE-1): give a worker a daily pay rate from a day on, through
// POST /api/v1/staffpay/pay-rates/. Opens from Malipo kwa siku's button (worker-pay.tsx), in a sheet over the worker's
// page (UI-10, sheet.tsx), titled "Malipo mapya ya Juma".
//
// As Jack pictured it (19 Nov 2026): Kiasi kwa siku, Kuanzia, Anachangia chakula? (Ndiyo, or Hapana, ni mpishi: the cook
// pays no share of the meals, WAGE-7), Sababu (si lazima), then Ghairi and Hifadhi malipo, which names what it saves
// (UI-10). A first rate starts on the worker's
// first day, as Juma, hired on the 10th, is paid from the 10th though Baba types it on the 19th; a change starts today,
// or on the first day for a worker who hasn't started yet, with the amount and the meals of the rate in force, so a
// raise to 12,000 is a change of one digit (WAGE-1's defaults). The date box offers nothing before the worker's first day: a day gone by is fine, as the days before
// today are paid at the rate their own day had (rates_between), but no day before the job.
//
// A rate is never changed: a mistake is mended by a new rate for the same day, which counts, as the newest (rule 2).
// So the form always adds one.
//
// What the form can see itself is said at once, in the server's own sentences, and nothing is sent: an amount that is
// empty, 0, or has cents (pay_rate.amount_invalid), an empty day (required), a day before the first
// (pay_rate.before_first_day). The server says the rest: who may (staff.own, staff.superuser_only, staff.more_keys,
// staff.left, on the demo demo.people_fixed, and a bare permission_denied), above the sheet's buttons, as they are
// about the person, not a box; and on the demo, a note (demo.no_note), beside its box.
//
// The id is sent again with every try of the same amount, day, meals and note (ADR-0007): a send whose answer the
// network lost, tried again, gets the stored rate back, never a second one. A changed try gets a new id, as the server
// answers a repeated id with the rate it stored, whatever the new send carries (setting-form.tsx).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney } from "@/lib/format";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import {
  PAY_RATES,
  type PayRates,
  startingAmount,
  typedAmount,
} from "./pay-rates";
import type { Worker } from "./workers";

type Sent = components["schemas"]["PayRateCreateRequest"];

// The fields with a box, beside which their refusals show. A refusal of any other field shows above the sheet's
// buttons.
const ON_A_BOX = new Set([
  "daily_rate",
  "effective_from",
  "shares_meals",
  "note",
]);

// Anachangia chakula?'s two answers: a Choice's values are text.
const YES = "yes";
const NO = "no";

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { daily_rate?: string; effective_from?: string };

export function PayRateForm({
  worker,
  rates,
  onDone,
  onCancel,
  finalFocus,
}: {
  worker: Worker;
  /** The worker's rates as the page read them: the one in force, if any, and the shop's today. */
  rates: PayRates;
  /** Saved: the line that says what, in the person's words. */
  onDone: (sentence: string) => void;
  /** Ghairi or Esc. */
  onCancel: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("workers.pay");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The rate in force today, which a change starts from (see the top).
  const inForce = rates.rates.find((rate) => rate.id === rates.in_force);
  const [typed, setTyped] = useState(() => startingAmount(inForce));
  // A first rate on the first day; a later one today, unless the worker hasn't started yet, as a rate never starts
  // before the first day (pay_rate.before_first_day): Zawadi, starting on the 25th, gets her second rate from the 25th
  // too, never a day the server would refuse. Days as text sort as days do.
  const [day, setDay] = useState(() =>
    rates.rates.length === 0 || rates.today < worker.started_on
      ? worker.started_on
      : rates.today,
  );
  const [meals, setMeals] = useState(
    inForce?.shares_meals === false ? NO : YES,
  );
  const [note, setNote] = useState("");
  const [own, setOwn] = useState<Checks>({});
  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);

  const save = useMutation({
    mutationFn: (body: Sent) =>
      answerOf(api.POST("/api/v1/staffpay/pay-rates/", { body })),
    onSuccess: (rate) => {
      // Every worker's rates asked again: this worker's history and today's rate show the new one where it belongs.
      void store.invalidateQueries({ queryKey: PAY_RATES });
      onDone(
        t("saved", {
          name: worker.display_name,
          amount: formatMoney(new Decimal(rate.daily_rate)),
          day: formatDay(rate.effective_from),
        }),
      );
    },
  });

  /** The sheet's Hifadhi malipo, or Enter in a box: the sheet's own form stops the browser's send (sheet.tsx). */
  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    const amount = typedAmount(typed);
    // Days as text sort as days do ("2026-11-10"). The box offers nothing before the first day; one typed by hand
    // is said here, as the server would.
    const checks: Checks = {
      daily_rate: amount === null ? "pay_rate.amount_invalid" : undefined,
      effective_from:
        day === ""
          ? "required"
          : day < worker.started_on
            ? "pay_rate.before_first_day"
            : undefined,
    };
    setOwn(checks);
    if (amount === null || checks.effective_from) return;
    const body = {
      staff: worker.id,
      daily_rate: amount,
      effective_from: day,
      shares_meals: meals === YES,
      note,
    };
    // The same id for a try of the same rate; a new one once anything in it changed.
    const carried = JSON.stringify(body);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({ id: lastSend.current.id, ...body });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's; a field with no box above the
  // sheet's buttons, in its own sentence; a refusal of the whole request, with no field, as who may, is ApiErrorAlert's
  // (setting-form.tsx says why).
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const noBox = Object.entries(byField)
    .filter(([field]) => !ON_A_BOX.has(field))
    .map(([, sentence]) => sentence);
  const aboutAField = Object.keys(byField).length > 0;

  return (
    <Sheet
      open
      onClose={onCancel}
      title={t("form.title", { name: worker.display_name })}
      actionLabel={t("form.save")}
      onAction={send}
      // Held while it is sent, so a second tap sends nothing, and the sheet stays until its answer comes; the id would
      // save it once anyway.
      busy={save.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      <Field
        label={t("form.amount")}
        hint={t("form.amountHint")}
        error={said(own.daily_rate) ?? byField.daily_rate}
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        // Digits only on a phone's keypad: a day's pay is whole shillings.
        inputMode="numeric"
        autoComplete="off"
      />
      <Field
        label={t("form.from")}
        hint={t("form.fromHint")}
        error={said(own.effective_from) ?? byField.effective_from}
        type="date"
        // The phone's calendar offers nothing before the worker's first day.
        min={worker.started_on}
        value={day}
        onChange={(event) => setDay(event.target.value)}
      />
      <Choice
        label={t("form.meals")}
        error={byField.shares_meals}
        options={[
          { value: YES, label: t("form.mealsYes") },
          { value: NO, label: t("form.mealsNo") },
        ]}
        value={meals}
        onValueChange={setMeals}
      />
      <Field
        label={t("form.note")}
        hint={t("form.noteHint")}
        error={byField.note}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        autoComplete="off"
        // As the server keeps it (PayRate.note, 200 characters).
        maxLength={200}
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
        <ApiErrorAlert error={aboutAField ? null : save.error} />
      )}
    </Sheet>
  );
}
