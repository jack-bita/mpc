// confirm-device.tsx — Sajili kifaa: the manager says yes to a waiting device, from their own phone
// (UI-3, 03 §5.9, step 2).
//
// The manager types the code the new laptop shows, gives the laptop a name for the list, and picks its
// home side. POST /api/v1/people/devices/ makes the device in the manager's shop, with the shop's next
// device number, and switches its key on (AUTH-1, AUTH-5).
//
// The new device's id is made here, on the phone, once per form (ADR-0007). A tap sent twice, or sent
// again after an answer lost on a weak network, carries the same id, so the server finds the device the
// first one made and answers with it: the shop gets one laptop on its list, never two (AUTH-5,
// CreateOnceMixin). The form keeps the id until it is done; the next form gets a new one.
//
// Only the sides where the person holds device.manage are offered (sidesWhere); the server checks the
// key again on the side sent (PPL-5).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import type { SideKeys } from "@/features/people/who-is-here";
import { newId } from "@/lib/ids";

export type Device = components["schemas"]["Device"];

// Refusals of the whole form that are really about one box: the server names no field for them (a
// service's refusal, or a rule on the table, apps/core/api/errors.py), but the person fixes one box, so
// the sentence sits above it, as Field shows an error (GOV.UK's order).
const ABOUT_THE_CODE = /^pairing\./;
const ABOUT_THE_NAME = /^device\.name_/;

export function ConfirmDevice({
  sides,
  onDone,
  onCancel,
}: {
  /** The sides the person may register a device on. */
  sides: SideKeys[];
  onDone: (device: Device) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("device.office");
  const { fieldMessages, message } = useApiErrorWords();

  // Made once, as the form opens, and kept through every send of it (see the top of this file).
  const [id] = useState(newId);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  // A manager of one side has nothing to pick: it is picked for them.
  const [side, setSide] = useState<string | null>(
    sides.length === 1 ? (sides[0]?.id ?? null) : null,
  );
  const [noSide, setNoSide] = useState(false);

  const confirm = useMutation({
    mutationFn: (homeSide: string) =>
      answerOf(
        api.POST("/api/v1/people/devices/", {
          // The code as typed: the server takes any case, a dash or spaces (clean_typed_code).
          body: { id, pairing_code: code, name, home_side: homeSide },
        }),
      ),
    onSuccess: onDone,
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // No side yet: said at once, as the server would only say "required". The code and the name are
    // the server's to check, as their rules live there (ADR-0015).
    if (side === null) {
      setNoSide(true);
      return;
    }
    setNoSide(false);
    confirm.mutate(side);
  }

  // Where each refusal shows: beside its box, or on the alert under the form.
  const byField = fieldMessages(confirm.error);
  const refusedCode =
    confirm.error instanceof ApiRefusal ? confirm.error.body.code : null;
  const codeError =
    byField.pairing_code ??
    (refusedCode && ABOUT_THE_CODE.test(refusedCode)
      ? message(confirm.error)
      : undefined);
  const nameError =
    byField.name ??
    (refusedCode && ABOUT_THE_NAME.test(refusedCode)
      ? message(confirm.error)
      : undefined);
  const onABox =
    refusedCode !== null &&
    (ABOUT_THE_CODE.test(refusedCode) || ABOUT_THE_NAME.test(refusedCode));

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's; the server's
    // answers say what is wrong, in the open book.
    <form noValidate onSubmit={send} className="grid max-w-md gap-6">
      <Field
        label={t("code")}
        hint={t("codeHint")}
        error={codeError}
        value={code}
        onChange={(event) => setCode(event.target.value)}
        // A code, not a word: no capital letter added, no spelling fixed, nothing remembered from before.
        autoCapitalize="characters"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        maxLength={20}
      />
      <Field
        label={t("name")}
        hint={t("nameHint")}
        error={nameError}
        value={name}
        onChange={(event) => setName(event.target.value)}
        autoComplete="off"
        maxLength={40}
      />
      <Choice
        label={t("side")}
        hint={t("sideHint")}
        error={noSide ? t("pickSide") : (byField.home_side ?? undefined)}
        options={sides.map((option) => ({
          value: option.id,
          label: option.name,
        }))}
        value={side}
        onValueChange={setSide}
      />
      {/* What no box can show: no network, no key on that side, the server's own problem. */}
      <ApiErrorAlert error={onABox ? null : confirm.error} />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing; the id would save it anyway. */}
        <Button type="submit" disabled={confirm.isPending}>
          {t("confirm")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
