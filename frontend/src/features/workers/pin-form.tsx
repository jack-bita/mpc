// pin-form.tsx — Weka PIN (PPL-12): a worker's own PIN, typed by the worker on the owner's phone, sent through
// POST /api/v1/people/staff/{id}/pin/, so a new worker gets a tile on the shop's laptops. Opens on the Kuingia card
// (worker-logins.tsx).
//
// Face to face (the card, v1.35): the owner hands his phone over and the worker types their own PIN, as whoever types
// it knows it, and nothing makes them change it later. Two boxes, PIN mpya and Andika tena, each hidden, with the
// phone's number pad. No Sababu: the worker types it himself, and the edit history keeps who set it and when
// (pin_changed_at; it never keeps the hash, ADR-0036).
//
// What the form sees, it says at once, beside its box, and sends nothing: an empty first box (blank), two that differ.
// Whether the PIN is four digits and not too easy is the server's alone (set_pin), so the shop hears one rule from one
// place; its two codes show beside PIN mpya. Who may (pin.own, pin.superuser_only, pin.more_keys), staff.left and
// demo.logins_fixed show above the buttons, with no network and the server's own problems.
//
// The PIN is a secret: the change keeps nothing in the store once it is done (gcTime: 0, UI-5), as the store is shared
// by everyone who uses the phone; and the boxes go with the form when it closes, either way.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Field } from "@/components/design/field";
import { aboutTheWholeRequest } from "@/features/settings/closures";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { useOnline } from "@/offline/network";

import { keepWorker, type Worker, WORKERS } from "./workers";

/** set_pin's strength codes, which come with no field: about the PIN typed, so they show beside PIN mpya. */
const ABOUT_THE_PIN = new Set(["pin.not_four_digits", "pin.too_easy"]);

/** The form's own checks, by box: a server code ("blank"), or "differ", said in this form's own words. */
type Checks = { pin?: "blank"; again?: "differ" };

export function PinForm({
  worker,
  onDone,
  onCancel,
}: {
  worker: Worker;
  /** Set: the worker as the server answered, has_pin and all. */
  onDone: (worker: Worker) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("workers.logins");
  const actions = useTranslations("workers.actions");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [pin, setPin] = useState("");
  const [pinAgain, setPinAgain] = useState("");
  const [own, setOwn] = useState<Checks>({});

  // The title takes the keyboard as the form opens, so a screen reader says what opened where the button was; the
  // worker, handed the phone, then taps the first box.
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => title.current?.focus(), []);

  const change = useMutation({
    mutationFn: (typed: string) =>
      answerOf(
        api.POST("/api/v1/people/staff/{id}/pin/", {
          params: { path: { id: worker.id } },
          body: { pin: typed },
        }),
      ),
    // Nothing of the PIN outlives the change in the store, which everyone on this phone shares (UI-5).
    gcTime: 0,
    onSuccess: (changed) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      onDone(changed);
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    change.reset();
    const checks: Checks = {};
    if (pin === "") checks.pin = "blank";
    else if (pin !== pinAgain) checks.again = "differ";
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    change.mutate(pin);
  }

  // Where each refusal shows: beside PIN mpya, the form's own first, then a strength code or the field's (a PIN too
  // long for the route, `pin`); beside Andika tena, two that differ; everything else above the buttons.
  const code =
    change.error instanceof ApiRefusal ? change.error.body.code : undefined;
  const aboutThePin = code !== undefined && ABOUT_THE_PIN.has(code);
  const byField = fieldMessages(change.error);
  const above = aboutThePin ? null : aboutTheWholeRequest(change.error);

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <div className="grid gap-2">
        <h2
          ref={title}
          tabIndex={-1}
          className="text-lg font-semibold outline-none"
        >
          {t("pinTitle", { name: worker.display_name })}
        </h2>
        <p>{t("handOver", { name: worker.display_name })}</p>
      </div>
      <Field
        label={t("newPin")}
        hint={t("newPinHint")}
        error={
          (own.pin ? codeMessage(codes, own.pin) : undefined) ??
          (aboutThePin ? codeMessage(codes, code) : undefined) ??
          byField.pin
        }
        // Hidden as it is typed: the owner stands beside the worker. Not a PasswordField: a PIN has no eye to show it,
        // as the PIN pad has none (features/login/pin-pad.tsx).
        type="password"
        // The phone's number pad.
        inputMode="numeric"
        // "new-password", never "off", which phones ignore on a hidden box: a box for a new secret is never filled
        // with a saved one, so the owner's own saved password can't be offered to the worker holding his phone
        // (PPL-12's review). A browser may still offer to save what is typed; the owner says no.
        autoComplete="new-password"
        maxLength={4}
        value={pin}
        onChange={(event) => setPin(event.target.value)}
      />
      <Field
        label={t("again")}
        error={own.again ? t("differ") : undefined}
        type="password"
        inputMode="numeric"
        autoComplete="new-password"
        maxLength={4}
        value={pinAgain}
        onChange={(event) => setPinAgain(event.target.value)}
      />
      {/* Who may (pin.own, pin.superuser_only, pin.more_keys), staff.left, the demo, no network, the server's own
          problem. */}
      <ApiErrorAlert error={above} />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx). */}
        <Button type="submit" disabled={change.isPending || !online}>
          {actions("save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {actions("cancel")}
        </Button>
      </div>
    </form>
  );
}
