// pin-form.tsx — Weka PIN (PPL-12): a worker's own PIN, typed by the worker on the owner's phone, sent through
// POST /api/v1/people/staff/{id}/pin/, so a new worker gets a tile on the shop's laptops. Opens from the Kuingia card
// (worker-logins.tsx), in a sheet over the worker's page (UI-10, sheet.tsx): "Weka PIN ya Asha", the line that says to
// hand the phone over, the two boxes, Ghairi and Weka PIN. On a phone the sheet itself takes the keyboard as it opens,
// so no number pad springs up before the worker holds the phone, and a screen reader says its title; on a laptop, the
// first box does (Base UI's own way).
//
// Face to face (the card, v1.35): the owner hands his phone over and the worker types their own PIN, as whoever types
// it knows it, and nothing makes them change it later. Two boxes, PIN mpya and Andika tena, each hidden, with the
// phone's number pad. No Sababu: the worker types it himself, and the edit history keeps who set it and when
// (pin_changed_at; it never keeps the hash, ADR-0036).
//
// What the form sees, it says at once, beside its box, and sends nothing: an empty first box (blank), two that differ.
// Whether the PIN is four digits and not too easy is the server's alone (set_pin), so the shop hears one rule from one
// place; its two codes show beside PIN mpya. Who may (pin.own, pin.superuser_only, pin.more_keys), staff.left and
// demo.logins_fixed show above the sheet's buttons, with no network and the server's own problems.
//
// The PIN is a secret: the change keeps nothing in the store once it is done (gcTime: 0, UI-5), as the store is shared
// by everyone who uses the phone; and the boxes go with the sheet when it closes, either way, as it is drawn only while
// open (worker-logins.tsx).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
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
  finalFocus,
}: {
  worker: Worker;
  /** Set: the worker as the server answered, has_pin and all. */
  onDone: (worker: Worker) => void;
  /** Ghairi or Esc. */
  onCancel: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("workers.logins");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [pin, setPin] = useState("");
  const [pinAgain, setPinAgain] = useState("");
  const [own, setOwn] = useState<Checks>({});

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

  /** The sheet's Weka PIN, or Enter in a box: the sheet's own form stops the browser's send (sheet.tsx). */
  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    change.reset();
    const checks: Checks = {};
    if (pin === "") checks.pin = "blank";
    else if (pin !== pinAgain) checks.again = "differ";
    setOwn(checks);
    if (Object.keys(checks).length > 0) return;
    change.mutate(pin);
  }

  // Where each refusal shows: beside PIN mpya, the form's own first, then a strength code, then the field's own code
  // on `pin`, a safety net this form never meets, as its boxes take four characters and the route takes sixteen;
  // beside Andika tena, two that differ; everything else above the sheet's buttons.
  const code =
    change.error instanceof ApiRefusal ? change.error.body.code : undefined;
  const aboutThePin = code !== undefined && ABOUT_THE_PIN.has(code);
  const byField = fieldMessages(change.error);
  const above = aboutThePin ? null : aboutTheWholeRequest(change.error);

  return (
    <Sheet
      open
      onClose={onCancel}
      title={t("pinTitle", { name: worker.display_name })}
      description={t("handOver", { name: worker.display_name })}
      actionLabel={t("pinSave")}
      onAction={send}
      // Held while it is sent, so a second tap sends nothing, and the sheet stays until its answer comes.
      busy={change.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
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
    </Sheet>
  );
}
