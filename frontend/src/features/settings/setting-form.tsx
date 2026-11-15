// setting-form.tsx — Badilisha: a rule's new value from a day on (SHOP-5, 03 §5.8). Opens under the rule's line
// on Mipangilio ya duka, for someone holding settings.manage there: on the whole shop for a shop's rule, on the
// side for a side's.
//
// A new value never changes the old one: POST /api/v1/shops/settings/ writes a new row, which counts from its own
// day on (ADR-0013), so the pay worked out for a day already passed never moves. That day is the shop's today or
// later: the date box starts at today and offers nothing earlier, and the server refuses an earlier one anyway
// (setting.date_past, Jack, SHOP-3).
//
// The box fits the rule's kind (setting-words.ts): an amount or a percent with the keypad's point, a whole number
// with digits only, the phone's own clock for a time, and Ndiyo or Hapana for a yes or no. What is typed goes as
// text, never through a JavaScript number (ADR-0024): "1,000" is sent as "1000", the commas people write taken
// out, and the server reads it into a Decimal. A box left empty, or one that isn't a number at all, is said at
// once, in the server's own sentences; the server checks the rest, a value too big or too small for its rule, and
// its sentence then shows beside the same box (useApiErrorWords().fieldMessages).
//
// The id is sent again with every try of the same value (ADR-0007): a send whose answer the network lost, tried
// again, gets the stored row back, not a second row. A changed value, day or note gets a new id: the server answers a
// repeated id with the row it stored, whatever the new send carries, so the old id would have the page say
// Imehifadhiwa for a value it never saved. Two rows are safe: on one day the one written last is in force (T2), and
// the history shows both (SHOP-5's review).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import type { RuleLine, RuleRow } from "./rules";
import type { SettingKey, SettingKind } from "./setting-words";
import { SHOP_RULES } from "./shop-rules";

// A whole number as people write it: plain digits ("1000"), or groups of three after the first, each after a comma or
// a space ("1,000", "1 000", "1,440"). A comma anywhere else is refused, not taken out: "2,5" is someone writing two
// and a half the way much of the world does, and as 25 it would be ten times what they meant (SHOP-5's review).
const WHOLE = /^(\d+|\d{1,3}([, ]\d{3})+)$/;
// An amount or a percent: a whole number so written, and at most two places after a point, as the server keeps them
// (numeric(14,2)).
const DECIMAL = /^(\d+|\d{1,3}([, ]\d{3})+)(\.\d{1,2})?$/;
// The phone's clock box answers "07:35"; one typed by hand on a laptop's plain box, the same.
const CLOCK = /^\d{2}:\d{2}$/;

/** What was typed, as the server takes it: "1,000" → "1000". Null when it isn't a value of its kind at all,
 * which the form says at once; whether it is too big or too small for its rule is the server's to say. */
export function typedValue(kind: SettingKind, typed: string): string | null {
  switch (kind) {
    case "money":
    case "percent": {
      // The commas and spaces between thousands, out once the pattern has placed them: "1,000" and "1 000" are 1000.
      const trimmed = typed.trim();
      return DECIMAL.test(trimmed) ? trimmed.replace(/[, ]/g, "") : null;
    }
    case "whole": {
      const trimmed = typed.trim();
      return WHOLE.test(trimmed) ? trimmed.replace(/[, ]/g, "") : null;
    }
    case "time":
      return CLOCK.test(typed) ? typed : null;
    case "yes_no":
      return typed === "true" || typed === "false" ? typed : null;
  }
}

/** A value as the box starts with it: today's, as the server writes it, with the zeros at the end of an amount
 * left off ("1000.00" → "1000"), so changing 1,000 to 1,500 is a change of one digit. */
export function startingText(kind: SettingKind, value: string): string {
  return kind === "money" || kind === "percent"
    ? new Decimal(value).toString()
    : value;
}

export function SettingForm({
  ruleKey,
  line,
  today,
  onSaved,
  onCancel,
}: {
  ruleKey: SettingKey;
  line: RuleLine;
  /** The shop's today, from the server's answer: the first day a new value may start. */
  today: string;
  onSaved: (row: RuleRow) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("shopSettings");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();

  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top of this file).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);
  const [typed, setTyped] = useState(() => startingText(line.kind, line.value));
  const [day, setDay] = useState(today);
  const [note, setNote] = useState("");
  // The form's own checks, by box, as codes the server would send: their sentences are the server's.
  const [own, setOwn] = useState<{ value?: string; effective_from?: string }>(
    {},
  );

  const save = useMutation({
    mutationFn: (sent: {
      id: string;
      value: string;
      day: string;
      note: string;
    }) =>
      answerOf(
        api.POST("/api/v1/shops/settings/", {
          body: {
            id: sent.id,
            key: ruleKey,
            value: sent.value,
            effective_from: sent.day,
            note: sent.note,
            // A side's rule names its side; a shop's names none (the server refuses one, side_not_allowed).
            ...(line.side === null ? {} : { side: line.side }),
          },
        }),
      ),
    onSuccess: (row) => {
      // The page asks again, so the new value shows where it belongs: in force today, or to come.
      void store.invalidateQueries({ queryKey: SHOP_RULES });
      onSaved(row);
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    const value = typed.trim() === "" ? null : typedValue(line.kind, typed);
    const checks = {
      value:
        typed.trim() === ""
          ? "setting.value_blank"
          : value === null
            ? "setting.value_invalid"
            : undefined,
      // Days as text sort as days do ("2026-12-01"). The box offers nothing before today; one typed by hand is
      // said here, as the server would.
      effective_from:
        day === "" || day < today ? "setting.date_past" : undefined,
    };
    setOwn(checks);
    if (value === null || checks.effective_from) return;
    // The same id for a try of the same value, day and note; a new one once any of them changed.
    const carried = JSON.stringify([value, day, note]);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({ id: lastSend.current.id, value, day, note });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's. A refusal about the
  // rule itself, its side or its key, has no box: the page sends both, so it means the app and the server
  // disagree (a newer server, or a bug), and it shows above the buttons in the server's sentence.
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const valueError = said(own.value) ?? byField.value;
  const dayError = said(own.effective_from) ?? byField.effective_from;
  const noteError = byField.note;
  const aboutTheRule = [byField.side, byField.key].filter(
    (sentence): sentence is string => sentence !== undefined,
  );
  const onABox = Object.keys(byField).length > 0;

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      {line.kind === "yes_no" ? (
        <Choice
          label={t("form.newValue.yes_no")}
          error={valueError}
          options={[
            { value: "true", label: t("yes") },
            { value: "false", label: t("no") },
          ]}
          value={typed}
          onValueChange={setTyped}
        />
      ) : (
        <Field
          label={t(`form.newValue.${line.kind}`)}
          error={valueError}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          // The person just asked for this form: the keyboard starts in its box, where the button that
          // opened it was (settings-screen.tsx sends it back there when the form closes).
          autoFocus
          autoComplete="off"
          {...boxFor(line.kind)}
        />
      )}
      <Field
        label={t("form.from")}
        hint={t("form.fromHint")}
        error={dayError}
        type="date"
        // The phone's calendar offers nothing before the shop's today.
        min={today}
        value={day}
        onChange={(event) => setDay(event.target.value)}
      />
      <Field
        label={t("form.note")}
        hint={t("form.noteHint")}
        error={noteError}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        autoComplete="off"
        // As the server keeps it (Setting.note, 200 characters).
        maxLength={200}
      />
      {aboutTheRule.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{aboutTheRule.join(" ")}</AlertDescription>
        </Alert>
      ) : (
        // What no box can show: no network, no key here, the server's own problem.
        <ApiErrorAlert error={onABox ? null : save.error} />
      )}
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits
            unsent while it looks done (my-settings.tsx); the id would save it once anyway. */}
        <Button type="submit" disabled={save.isPending || !online}>
          {t("form.save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("form.cancel")}
        </Button>
      </div>
    </form>
  );
}

/** The box's keypad for each kind: a point for an amount or a percent, digits only for a whole number, the
 * phone's clock for a time. */
function boxFor(kind: Exclude<SettingKind, "yes_no">) {
  switch (kind) {
    case "money":
    case "percent":
      return { inputMode: "decimal" as const };
    case "whole":
      return { inputMode: "numeric" as const };
    case "time":
      return { type: "time" };
  }
}
